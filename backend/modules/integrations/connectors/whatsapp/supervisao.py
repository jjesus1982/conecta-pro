"""Quem supervisiona, e o que acontece com pedido que MEXE NA ESCALA.

Duas decisões que o Jordan deu em 23/09/2026, e que moram juntas porque são a mesma
pergunta vista de dois lados:

1. **"Orlailson enxerga toda a operação."** Ele é o único supervisor hoje. A tentação era
   derivar isso de `employees.cargo ILIKE '%supervis%'` — e seria a trava observando a
   coisa errada de novo: `cargo` é texto que o Jordan edita na tela, e um "Supervisor de
   Portaria" cadastrado amanhã ganharia, **em silêncio**, visão sobre a vida de 61 pessoas.
   Autorização não se infere de rótulo.

   A autoridade já existia: `users.role = 'gerente_operacional'`, ligado ao colaborador por
   `users.employee_id`. Reuso ela. **Duas condições independentes**, e as duas precisam
   valer: o telefone resolve a um funcionário com VÍNCULO VIVO (`identidade.quem_e`, que
   recusa `inativo`/`candidato`/`pj_pendente`) **e** a conta dele tem o papel.

   ⚠️ E é por isso que as duas condições não são redundância: há HOJE um segundo
   `gerente_operacional` ativo — Eliziel Gonzaga — cujo colaborador está `inativo`. A conta
   viva com papel de gerente é um furo do RBAC do ERP (reportado ao Jordan, não consertado
   aqui: perfis são dele). Do lado do José Luís ele cai na primeira condição.

2. **"Pedido que muda escala — ele registra para ser aprovado por mim ou orlailson."**
   O operacional é curado à mão pelo Jordano e READ-ONLY para agentes. Então este módulo
   **não mexe em escala** — nem quando aprovado. Ele grava um pedido inerte na Central de
   Rascunhos e avisa quem decide. `ROLES_KIT_OP = ("admin", "gerente_operacional")` já é,
   literalmente, "eu ou o Orlailson".

   A aprovação autoriza a troca; **aplicar** segue sendo clique humano na tela de escala.
   O título diz isso em voz alta, porque um rascunho aprovado que parecesse "escala
   trocada" seria pior que não ter rascunho nenhum.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from core.logging import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Papéis de conta que enxergam a operação inteira. `admin` = Jordan e diretoria.
PAPEIS_SUPERVISAO = ("admin", "gerente_operacional")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


#: Sinais de pedido que MEXE NA ESCALA. Só isto vira rascunho — "bom dia" e "tá chovendo"
#: não. Cada tupla é (rótulo, regex). O rótulo entra no título do rascunho para o Jordan
#: saber do que se trata sem abrir.
#:
#: ⚠️ A régua observa o PEDIDO, não a palavra. "Cobri o posto do Eduardo ontem" é relato e
#: não pede nada; "preciso que alguém cubra amanhã" pede. Daí os verbos de pedido/futuro
#: junto do objeto — e daí o `_RELATO` abaixo, que desarma o passado.
_PEDIDOS: tuple[tuple[str, str], ...] = (
    ("troca de plantão", r"\b(troca[r]?|permut[ae]r?|invert[er])\b.{0,30}\b(plantao|turno|escala|folga|dia)\b"),
    ("cobertura de posto", r"\b(cobr[ie]r?|substitu[ií]r?|repor|render)\b.{0,30}\b(posto|turno|plantao|vaga|ele|ela)\b"),
    ("falta anunciada", r"\b(nao vou|nao posso|nao consigo|vou faltar|faltarei|nao dou conta)\b.{0,40}\b(trabalhar|ir|comparecer|plantao|posto|amanha|hoje)\b"),
    ("atestado", r"\batestado\b|\b(passei|fui) no medico\b|\bmedico me afastou\b"),
    ("folga", r"\b(pedir|preciso de|queria|posso tirar|me d[aá])\b.{0,20}\bfolga\b"),
    ("férias", r"\bferias\b.{0,30}\b(quero|queria|posso|marcar|antecipar|adiar)\b|\b(quero|queria|posso|marcar)\b.{0,20}\bferias\b"),
    ("saída antecipada", r"\b(sair|liberar|liberacao)\b.{0,25}\b(mais cedo|antes|antecipad)"),
)

#: Relato do passado não é pedido. Sem isto, todo "ontem o Fulano cobriu" abriria rascunho.
_RELATO = re.compile(r"\b(ontem|anteontem|semana passada|mes passado|cobri|cobriu|cobrimos|ja foi|ja resolvi|resolvido)\b")


def classificar_pedido(texto: str | None) -> str | None:
    """Rótulo do pedido de escala, ou None quando a fala não pede nada.

    Determinístico e sem LLM, pelo mesmo motivo de `_papel_por_texto`: o que vira
    solicitação formal para o Jordan aprovar não pode depender de juízo do modelo.
    """
    t = _sem_acento(texto)
    if not t.strip():
        return None
    if _RELATO.search(t):
        return None
    for rotulo, padrao in _PEDIDOS:
        if re.search(padrao, t):
            return rotulo
    return None


async def papel_de_supervisao(db: AsyncSession, ident: Any) -> str | None:
    """`admin`/`gerente_operacional` quando a pessoa supervisiona; None caso contrário.

    Fail-closed em tudo: sem `employee_id` (telefone não resolveu a colaborador com vínculo
    vivo), sem conta, conta desativada ou papel fora da lista → None, e o José Luís trata a
    pessoa como funcionário comum, que é o comportamento de hoje.
    """
    emp = getattr(ident, "employee_id", None)
    if not emp or getattr(ident, "tipo", None) != "funcionario":
        return None
    try:
        row = (await db.execute(text(
            "SELECT role FROM users WHERE employee_id = :e AND is_active "
            "AND role = ANY(:papeis) LIMIT 1"),
            {"e": str(emp), "papeis": list(PAPEIS_SUPERVISAO)})).first()
    except Exception as e:  # noqa: BLE001
        logger.error("supervisao: papel não resolvido (%s) — tratando como funcionário", e)
        return None
    return row[0] if row else None


async def registrar_pedido_de_escala(
    db: AsyncSession,
    *,
    rotulo: str,
    texto: str,
    autor_nome: str | None,
    autor_fone: str | None,
    ident: Any = None,
    origem: str,
) -> dict[str, Any]:
    """Grava o pedido como rascunho inerte. NUNCA toca em escala, nem aqui nem na aprovação.

    `origem` é onde a pessoa falou (jid do grupo ou "privado") — entra no payload porque a
    mesma troca pedida em dois grupos é o mesmo pedido, e o Jordan precisa saber onde
    responder.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    from modules.ai.conversation.services.orquestrador.acoes.base import ROLES_KIT_OP  # noqa: PLC0415
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho  # noqa: PLC0415

    # `solicitado_por` é trilha, não autoridade: quem pede não aprova (os aprovadores vêm de
    # ROLES_KIT_OP). Uso a conta do solicitante quando existe só para o histórico ficar
    # navegável; sem conta, fica só o nome.
    user_id = None
    emp = getattr(ident, "employee_id", None)
    if emp:
        try:
            user_id = (await db.execute(text(
                "SELECT id FROM users WHERE employee_id = :e LIMIT 1"), {"e": str(emp)})).scalar()
        except Exception:  # noqa: BLE001
            user_id = None

    nome = autor_nome or getattr(ident, "nome", None) or autor_fone or "desconhecido"
    quem = SimpleNamespace(id=user_id, nome=nome, name=nome)

    # ⚠️ O título diz "AUTORIZAR", não "trocar". Aprovar aqui autoriza a mudança; aplicar na
    # escala continua sendo o Jordan na tela. Um rascunho que se lesse "plantão trocado"
    # faria o aprovador acreditar num efeito que este módulo não produz.
    # ⭐ QUEM PODE COBRIR JÁ VEM NO RASCUNHO (24/09/2026, pedido do Jordan: "o José Luís tem de
    # ser o braço direito do Orlailson"). O gargalo dele não é DECIDIR a troca — é PESQUISAR
    # quem está livre, e isso são 4 a 9 rateios por dia. A lista sai da MESMA consulta que a
    # tela de substituição usa (`cobertura_service.livres_para_cobrir`), incluindo a
    # interjornada do art. 66: se o WhatsApp sugerisse por régua própria, ele e o sistema
    # recomendariam pessoas diferentes e ninguém saberia qual vale.
    #
    # ⚠️ Best-effort de propósito: falha aqui NÃO pode impedir o pedido de ser registrado. O
    # rascunho sem sugestão continua útil; pedido perdido, não.
    sugestoes: list[dict] = []
    if rotulo in ("troca de plantão", "cobertura de posto", "falta anunciada", "atestado"):
        try:
            from datetime import date as _date  # noqa: PLC0415

            from modules.operacional.services import cobertura_service as _cob  # noqa: PLC0415

            _cargo = (getattr(ident, "cargo", None) or "").upper()
            _post_id = None
            if emp:
                _post_id = (await db.execute(text(
                    "SELECT post_id::text FROM allocations WHERE employee_id = CAST(:e AS uuid) "
                    "  AND status='active' AND is_active LIMIT 1"), {"e": str(emp)})).scalar()
            # ⚠️ O MAPA DE COMPATIBILIDADE É O DA TELA, não o meu. Minha primeira versão passou
            # só o cargo da pessoa e devolveu ZERO na primeira execução real: quem pediu era o
            # Orlailson (`Supervisor Operacional`) e ninguém mais tem esse cargo. A tela resolve
            # isso com `CARGOS_COMPATIVEIS` — líder cobre agente e vice-versa — e usar régua
            # própria aqui é o mesmo erro de duas cópias, só que no vocabulário em vez da
            # consulta. Ele e o sistema recomendariam gente diferente.
            from modules.operacional.controllers.falta_substituto_controller import (  # noqa: PLC0415
                CARGOS_COMPATIVEIS as _COMPAT,
            )

            _cargos = _COMPAT.get(_cargo, [_cargo] if _cargo else [])
            if _cargos:
                sugestoes = await _cob.livres_para_cobrir(
                    db, cargos=_cargos, dia=_date.today(), post_id=_post_id,
                    excluir_employee_id=str(emp) if emp else None)
        except Exception as e:  # noqa: BLE001
            logger.warning("supervisao: não sugeri substituto para %s (%s)", nome, e)

    titulo = f"Autorizar {rotulo} — {nome}"
    _quem = ""
    if sugestoes:
        _mesmo = [s["nome"] for s in sugestoes if s["mesmo_posto"]][:3]
        _outros = [s["nome"] for s in sugestoes if not s["mesmo_posto"]][:3]
        _quem = (f" Podem cobrir hoje: {len(sugestoes)} livres"
                 + (f", do MESMO posto: {', '.join(_mesmo)}" if _mesmo else "")
                 + (f"; de outros postos: {', '.join(_outros)}" if _outros else "") + ".")
    resumo = (f'{nome} pediu em {origem}: "{texto.strip()[:220]}".{_quem} '
              f"Aprovar AUTORIZA a mudança; a escala continua sendo aplicada à mão.")

    # Idempotência pela pessoa + rótulo + dia: a mesma pessoa repetindo o pedido três vezes
    # no grupo (o que acontece) não pode virar três rascunhos. O dia entra porque o pedido
    # de amanhã é outro pedido.
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415
    dia = (datetime.now(UTC) - timedelta(hours=4)).strftime("%Y-%m-%d")
    idem = f"escala:{emp or autor_fone or nome}:{rotulo}:{dia}"

    return await criar_rascunho(
        db, quem,
        tipo="escala_pedido",
        modulo="operacional",
        titulo=titulo,
        resumo=resumo,
        payload={
            "rotulo": rotulo,
            "texto": texto[:1000],
            "autor_nome": nome,
            "autor_fone": autor_fone,
            "employee_id": str(emp) if emp else None,
            "posto": getattr(ident, "posto", None),
            "origem": origem,
            # Declarado no payload para quem lê o rascunho não precisar confiar na prosa:
            # não há executor que escreva em escala, de propósito.
            "aplica_automaticamente": False,
            # Quem pode cobrir, para o Orlailson decidir sem pesquisar. Guardo os 10 primeiros:
            # a lista inteira (18 hoje) não cabe numa decisão, e o que importa é o topo — a
            # ordenação já põe o mesmo posto primeiro.
            "podem_cobrir": sugestoes[:10],
            "podem_cobrir_total": len(sugestoes),
        },
        gate="🟡",
        requires_otp=False,
        roles_aprovador=ROLES_KIT_OP,
        idempotency_key=idem,
    )


async def visao_operacao(db: AsyncSession) -> dict[str, Any]:
    """A operação inteira, em NÚMEROS — leitura pura, para quem supervisiona.

    "Orlailson enxerga toda a operação" (Jordan, 23/09/2026). Até aqui ele enxergava só os
    grupos; isto é a operação de verdade: quantos estão de pé hoje, quantos faltaram, quem
    está sem escala, quantas inconsistências de ponto no período.

    ⭐ Reusa `dashboard_service.get_dashboard`, que é a MESMA função que monta a tela de ponto.
    Não reescrevi as consultas: a casa já pagou por família de código duplicada que divergiu
    na primeira mudança, e um número que o WhatsApp mostra diferente da tela é pior que número
    nenhum — quem lê não sabe em qual acreditar.

    ⚠️ O serviço é SÍNCRONO (`Session`, não `AsyncSession`), daí o `run_in_threadpool`: chamar
    sync de dentro do loop travaria o webhook inteiro enquanto a consulta roda.

    ⚠️ FRESCOR MEDIDO NA BATIDA, não em `ultima_sync_solides`. Minha primeira versão media a
    carga do Sólides e teria disparado aviso de defasagem em TODA chamada: ela está 7 dias
    velha (17/09) e as batidas continuam entrando normalmente — 83 de 34 pessoas em 23/09,
    porque o relógio é nosso (`gp_clock_punches`), não o Sólides. Alarme que soa sempre é
    alarme que ninguém lê, e eu quase entreguei exatamente isso dentro do campo criado para
    proteger de dado velho — o mesmo erro do hash sobre bytes de PDF.

    ⚠️ E `presentes`/`ausentes` são contados DESDE 00:00, então às 00:07 são naturalmente
    0 e 63. Vai rotulado, senão o supervisor lê "63 ausentes" de madrugada e acha que a
    empresa não foi trabalhar. Número sem a janela que o gerou não é dado, é susto.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

    from core.database.session import SyncSessionLocal  # noqa: PLC0415
    from modules.people_management.ponto.services import dashboard_service as _ds  # noqa: PLC0415

    def _ler() -> dict[str, Any]:
        with SyncSessionLocal() as s:
            return {"dash": _ds.get_dashboard(s), "sem_escala": _ds.get_colaboradores_sem_escala(s)}

    try:
        lido = await run_in_threadpool(_ler)
    except Exception as e:  # noqa: BLE001
        logger.error("visao_operacao falhou (%s)", e)
        return {"erro": "não consegui ler a operação agora", "detalhe": str(e)[:160]}

    d = lido["dash"] or {}
    sem = lido["sem_escala"] or []

    # Frescor pela ÚLTIMA BATIDA — é de onde os números vêm. `punch_timestamp` é hora de
    # Manaus nesta tabela (não UTC), então comparo com a hora de Manaus.
    horas_sem_batida = None
    try:
        horas_sem_batida = (await db.execute(text(
            "SELECT round(EXTRACT(EPOCH FROM (now() - interval '4 hours' - "
            "  max(punch_timestamp))) / 3600.0, 1) FROM gp_clock_punches"))).scalar()
    except Exception as e:  # noqa: BLE001
        logger.warning("visao_operacao: frescor da batida não medido (%s)", e)

    return {
        "hoje_desde_meia_noite": {
            "colaboradores": d.get("total_colaboradores"),
            "presentes": d.get("presentes_hoje"),
            "ausentes": d.get("ausentes_hoje"),
            "afastados": d.get("afastados"),
            "leia_assim": ("contado desde 00:00 de hoje — de madrugada 'ausentes' é o turno "
                           "que ainda não bateu, não gente faltando"),
        },
        "a_resolver": {
            "inconsistencias_no_periodo": d.get("inconsistencias_periodo"),
            "pontos_em_aberto": d.get("pontos_em_aberto"),
            "sem_escala": len(sem),
            "quem_esta_sem_escala": [x.get("nome") or x.get("employee_nome") for x in sem[:15]],
        },
        "por_escala": d.get("por_escala"),
        "banco_de_horas": d.get("banco_horas"),
        "horas_desde_a_ultima_batida": horas_sem_batida,
        # 12h é a régua porque o turno mais longo da casa é 12x36: passar disso sem NENHUMA
        # batida de ninguém significa relógio calado, e aí sim o número não vale.
        "aviso_defasagem": ("nenhuma batida há mais de 12h — o relógio pode estar calado e "
                            "estes números não valem; confira antes de decidir")
                           if (horas_sem_batida or 0) > 12 else None,
        # Informativo, não alarme: a carga do Sólides está velha de propósito ou não, e isso é
        # decisão do Jordan — não é o que alimenta os números acima.
        "ultima_carga_solides": d.get("ultima_sync_solides"),
        "escala_e_read_only": "eu não mudo escala; pedido de troca vira aprovação sua ou do Orlailson",
    }


# ═════════ ESCALA DO DIA: ele POSTA, o sistema CONFERE ═════════
#
# O Jordan escolheu isto como item 2 (24/09/2026), e a razão está na medição da primeira
# mensagem real: o Orlailson digita a escala no grupo à mão, e ela JÁ ESTÁ CERTA no ERP.
# Conferi as três linhas daquele dia — 3 postos existem, 2 funcionários ativos, 1 diarista com
# diária lançada. Ou seja: o trabalho dele ali não é DECIDIR, é transcrever e conferir. Conferir
# é o que a máquina faz melhor, e é onde ele perde o dia.
#
# ⚠️ Isto NÃO escreve nada. Divergência vira RELATÓRIO para ele, nunca correção — o operacional
# é curado à mão pelo Jordan, e essa regra não muda porque ficou conveniente.

#: `*Prime Arena 06h às 18h*` — o cabeçalho do posto traz nome e faixa de horário.
_CAB_POSTO = re.compile(r"^\*?\s*(?P<posto>.+?)\s+(?P<ini>\d{1,2})\s*h\s*(?:às|as|a)\s*(?P<fim>\d{1,2})\s*h\s*\*?$", re.I)
#: `Jair Rocha - P1` — a pessoa e a posição no posto.
_LINHA_PESSOA = re.compile(r"^(?P<nome>[^-]{3,60}?)\s*-\s*P\s*(?P<pos>\d+)\s*$", re.I)


def ler_escala_postada(texto: str) -> list[dict]:
    """Interpreta a escala que o Orlailson posta. [] quando o texto não é uma escala.

    ⚠️ Deliberadamente tolerante com a FORMA e rígida com a ESTRUTURA: ele escreve à mão, no
    celular, e vai variar asterisco, acento e espaço. O que não varia é a sequência
    "cabeçalho de posto com horário" → "pessoa - P<n>". Exigir formato exato faria a
    conferência falhar justamente nos dias em que ele estiver com pressa, que são os dias em
    que ela mais importa.
    """
    itens: list[dict] = []
    posto = ini = fim = None
    for linha in str(texto or "").splitlines():
        t = linha.strip()
        if not t:
            continue
        if (m := _CAB_POSTO.match(t)):
            posto, ini, fim = m.group("posto").strip(" *"), m.group("ini"), m.group("fim")
            continue
        if posto and (m := _LINHA_PESSOA.match(t)):
            itens.append({"posto_texto": posto, "pessoa_texto": m.group("nome").strip(),
                          "posicao": f"P{m.group('pos')}", "inicio": f"{int(ini):02d}:00",
                          "fim": f"{int(fim):02d}:00"})
    return itens


async def conferir_escala(db: AsyncSession, texto: str, *, dia=None) -> dict:
    """Confere a escala postada contra o ERP. Devolve o que DIVERGE, não o que bate.

    Para cada linha da escala pergunta três coisas ao sistema, na ordem em que doem:

      1. o POSTO existe? (nome do grupo é abreviado: "Prime Arena" × "Condomínio Prime Arena")
      2. a PESSOA existe — como funcionário ativo OU como diarista?
      3. o ERP CONCORDA que ela está nesse posto hoje? (turno em `shifts`, ou diária lançada)

    ⚠️ O relatório é feito para ser LIDO no WhatsApp: se tudo bate, a resposta é uma linha. Um
    relatório que repete as 12 linhas certas para esconder a única errada é pior que nenhum —
    é como o alarme que soa sempre.
    """
    from datetime import date as _date  # noqa: PLC0415

    dia = dia or _date.today()
    itens = ler_escala_postada(texto)
    if not itens:
        return {"e_escala": False}

    divergencias: list[dict] = []
    conferidos = 0

    for it in itens:
        alvo = it["posto_texto"]
        # Nome abreviado no grupo × nome cadastrado. Casa pelos tokens significativos, e se
        # casar com MAIS DE UM posto eu não escolho — ambiguidade é achado, não detalhe.
        postos = (await db.execute(text(
            "SELECT id::text, name FROM posts WHERE unaccent(lower(name)) LIKE '%'||unaccent(lower(:a))||'%'"),
            {"a": alvo})).all()
        if not postos:
            divergencias.append({"linha": it, "problema": f"posto {alvo!r} não existe no sistema"})
            continue
        if len(postos) > 1:
            divergencias.append({"linha": it, "problema":
                f"{alvo!r} casa com {len(postos)} postos ({', '.join(p[1] for p in postos)}) — não escolho"})
            continue
        post_id, post_nome = postos[0]

        pessoa = it["pessoa_texto"]
        # Funcionário: casa por TODOS os tokens do nome (nome do grupo costuma ser curto).
        emps = (await db.execute(text(
            "SELECT id::text, nome, status FROM employees WHERE unaccent(lower(nome)) LIKE ALL ("
            "  SELECT '%'||unaccent(lower(x))||'%' FROM unnest(string_to_array(:p,' ')) AS x WHERE length(x)>2)"),
            {"p": pessoa})).all()
        diaristas = (await db.execute(text(
            "SELECT id, nome FROM diaria_diaristas WHERE unaccent(lower(nome)) LIKE ALL ("
            "  SELECT '%'||unaccent(lower(x))||'%' FROM unnest(string_to_array(:p,' ')) AS x WHERE length(x)>2)"),
            {"p": pessoa})).all()

        if not emps and not diaristas:
            divergencias.append({"linha": it, "problema":
                f"{pessoa!r} não está no cadastro — nem funcionário, nem diarista"})
            continue

        if emps:
            emp_id, emp_nome, status = emps[0]
            if status != "ativo":
                divergencias.append({"linha": it, "problema":
                    f"{emp_nome} está {status!r} no cadastro, e aparece na escala"})
                continue
            tem_turno = (await db.execute(text(
                "SELECT 1 FROM shifts WHERE employee_id=CAST(:e AS uuid) AND post_id=CAST(:p AS uuid) "
                "  AND shift_date=:d AND is_active AND NOT is_off_day LIMIT 1"),
                {"e": emp_id, "p": post_id, "d": dia})).scalar()
            if not tem_turno:
                # Pode estar escalado em OUTRO posto — e isso é mais grave que não ter turno.
                outro = (await db.execute(text(
                    "SELECT p.name FROM shifts s JOIN posts p ON p.id=s.post_id "
                    " WHERE s.employee_id=CAST(:e AS uuid) AND s.shift_date=:d AND s.is_active "
                    "   AND NOT s.is_off_day LIMIT 1"), {"e": emp_id, "d": dia})).scalar()
                divergencias.append({"linha": it, "problema": (
                    f"{emp_nome} está na escala do {post_nome}, mas o sistema o tem em {outro}"
                    if outro else
                    f"{emp_nome} está na escala do {post_nome} e NÃO tem turno no sistema hoje")})
                continue
        else:
            dia_id, dia_nome = diaristas[0]
            # ⚠️ `diaria_diaristas.id` é INTEGER, não uuid — ao contrário de `employees.id`,
            # `posts.id` e tudo mais nesta função. Eu castei para uuid por hábito e a consulta
            # estourou. Tipo se confere no `information_schema`, não na memória.
            lancada = (await db.execute(text(
                "SELECT status FROM diaria_lancamentos WHERE diarista_id = :i AND data = :d LIMIT 1"),
                {"i": int(dia_id), "d": dia})).scalar()
            if not lancada:
                # ⭐ Esta é a divergência que custa DINHEIRO: diarista trabalhando sem diária
                # lançada não entra no pagamento, e (memória do projeto) não recebe o VT+VR
                # automático de R$32 que só nasce do lançamento.
                divergencias.append({"linha": it, "problema": (
                    f"{dia_nome} é DIARISTA e a diária de hoje NÃO está lançada — "
                    f"sem lançamento não há pagamento nem VT+VR")})
                continue
        conferidos += 1

    return {"e_escala": True, "linhas": len(itens), "conferidos": conferidos,
            "divergencias": divergencias, "dia": str(dia)}


def _texto_da_conferencia(r: dict) -> str:
    """O relatório como ele chega no WhatsApp. Curto quando bate, específico quando não.

    ⚠️ Divergência PRIMEIRO. Um relatório que começa listando os acertos para depois esconder
    o único erro no fim é o mesmo defeito do alarme que soa sempre: quem lê aprende a rolar
    até o fim e um dia não rola. E quando tudo bate, é UMA linha — o supervisor precisa saber
    que a conferência rodou, não receber um parágrafo por dia dizendo que está tudo bem.
    """
    div = r.get("divergencias") or []
    n, ok = r.get("linhas", 0), r.get("conferidos", 0)
    if not div:
        return f"✅ Escala conferida: {ok}/{n} batem com o sistema."
    linhas = [f"⚠️ Escala conferida: {ok}/{n} batem. {len(div)} para olhar:"]
    for d in div:
        it = d.get("linha") or {}
        linhas.append(f"• {it.get('posto_texto','?')} / {it.get('pessoa_texto','?')}: {d['problema']}")
    return "\n".join(linhas)


async def conferir_e_avisar(
    db: AsyncSession, *, texto: str, autor_fone: str | None, ident: Any = None,
    chatwoot_message_id: int | None = None,
) -> dict[str, Any]:
    """Confere a escala postada e responde a QUEM POSTOU, no privado dele. Nunca no grupo.

    ⭐ É o desenho que resolve o pedido do Jordan sem furar a parede: o grupo é onde o José Luís
    APRENDE, a conversa privada é onde ele AJUDA. A parede proíbe falar no grupo — e não precisa
    ser afrouxada para ele ser útil.

    Três guardas, e cada uma tem motivo:

      · só responde a quem SUPERVISIONA. A escala nomeia 3 a 9 pessoas e seus postos; mandar
        isso para qualquer um que colar um texto parecido no grupo é vazamento;
      · só uma vez por mensagem (`wa_grupo_falas` guarda a marca). Reentrega do Chatwoot é
        normal, e o Orlailson não pode receber a mesma conferência três vezes;
      · falha NUNCA derruba a absorção. O aprendizado de tom vale mais que o aviso.
    """
    papel = await papel_de_supervisao(db, ident)
    if not papel:
        return {"avisado": False, "motivo": "quem postou não supervisiona"}
    if not autor_fone:
        return {"avisado": False, "motivo": "sem telefone de quem postou"}

    marca = f"conferencia:{chatwoot_message_id}"
    if chatwoot_message_id is not None:
        ja = (await db.execute(text(
            "SELECT 1 FROM wa_grupo_falas WHERE motivo = :m LIMIT 1"), {"m": marca})).scalar()
        if ja:
            return {"avisado": False, "motivo": "já conferida"}

    r = await conferir_escala(db, texto)
    if not r.get("e_escala"):
        return {"avisado": False, "motivo": "não é escala"}

    msg = _texto_da_conferencia(r)
    fone = autor_fone if str(autor_fone).startswith("+") else f"+{autor_fone}"
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

        enviado = await whatsapp_service.send_custom(fone, msg)
    except Exception as e:  # noqa: BLE001
        logger.error("supervisao: conferência não entregue a %s (%s)", fone, e)
        return {"avisado": False, "motivo": f"falha no envio: {str(e)[:100]}", "conferencia": r}

    # A marca vai DEPOIS do envio: gravar antes e falhar o envio deixaria o Orlailson sem a
    # conferência e sem chance de recebê-la na reentrega.
    try:
        await db.execute(text(
            "INSERT INTO wa_grupo_falas (grupo_jid, motivo, texto) VALUES (:j, :m, :t)"),
            {"j": "privado", "m": marca, "t": msg[:2000]})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.warning("supervisao: marca da conferência não gravada (%s)", e)

    return {"avisado": bool(enviado), "para": fone, "divergencias": len(r.get("divergencias") or []),
            "conferidos": r.get("conferidos"), "linhas": r.get("linhas")}
