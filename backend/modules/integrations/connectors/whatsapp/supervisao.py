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
from datetime import datetime
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
    # ⭐ O DONO É O SUPERVISOR DE TUDO, e isso precisou ser dito em voz alta (24/09/2026).
    # `quem_e` com `e_dono=True` devolve `tipo="dono"` e NENHUM `employee_id` — ele não é
    # resolvido pelo cadastro de colaboradores, é reconhecido pelo telefone antes de tudo. Com
    # a exigência de `tipo == "funcionario"` logo abaixo, o Jordan era RECUSADO: perguntou a
    # cobertura no grupo dele e o agente respondeu "não estou conseguindo te atender".
    #
    # ⚠️ Não é atalho de permissão: `is_owner` é a régua mais estrita do sistema (telefone do
    # dono, com e sem o 9, em env). Quem chega aqui como `dono` já passou por ela.
    if getattr(ident, "tipo", None) == "dono":
        return "admin"

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

    # ⚠️ Decimal NÃO é serializável em JSON, e o retorno desta função vai para o MODELO como
    # resultado de ferramenta. `banco_horas` traz Decimal do Postgres, e o turno do agente morria
    # com "Object of type Decimal is not JSON serializable" — sintoma no grupo: resposta vazia.
    # Converter aqui, e não em quem chama, porque quem chama vai esquecer.
    def _limpar(v):
        from decimal import Decimal as _D  # noqa: PLC0415
        if isinstance(v, _D):
            return float(v)
        if isinstance(v, dict):
            return {k: _limpar(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_limpar(x) for x in v]
        return v

    # (a limpeza é aplicada no RETORNO inteiro, mais abaixo — ver o comentário lá)

    # Frescor pela ÚLTIMA BATIDA — é de onde os números vêm. `punch_timestamp` é hora de
    # Manaus nesta tabela (não UTC), então comparo com a hora de Manaus.
    horas_sem_batida = None
    try:
        horas_sem_batida = (await db.execute(text(
            "SELECT round(EXTRACT(EPOCH FROM (now() - interval '4 hours' - "
            "  max(punch_timestamp))) / 3600.0, 1) FROM gp_clock_punches"))).scalar()
    except Exception as e:  # noqa: BLE001
        logger.warning("visao_operacao: frescor da batida não medido (%s)", e)

    # ⚠️ `_limpar` no RETORNO INTEIRO, não campo por campo. Minha primeira versão limpou só o
    # dicionário do dashboard e o Decimal continuou vazando — ele vinha do `round()` do
    # Postgres em `horas_sem_batida`, que devolve `numeric`. Limpar as fontes que eu LEMBREI
    # deixou a que eu esqueci, e o sintoma (turno do agente morrendo com "Decimal is not JSON
    # serializable") é idêntico nos dois casos. Uma saída, uma limpeza.
    return _limpar({
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
        # 🔴 O CARIMBO DO SÓLIDES SAIU DAQUI, e a razão é o oposto de um conserto de máquina.
        #
        # Ele dizia "última carga: 17/09" e estava CERTO — o sync foi DESLIGADO pelo Jordan, em
        # duas decisões registradas no `celery_app.py`:
        #   · 13/09 — o pull de batidas trazia a GRADE, não batida medida (422 registros com 48
        #     horários distintos contra 763 do app; 134 das 180 anomalias do mês eram isso);
        #   · 16/09 — o sync fazia `UPDATE employees` por CPF e DESFAZIA correção feita à mão
        #     ("03:28 gravei BIANCA HELLEM; 03:57 voltou BIANCA HELEM").
        #
        # ⚠️ E foi por eu expor esse campo que o agente disse ao Jordan, hoje: *"a última carga
        # do sistema foi 17/09; se estiver desatualizada, o número tá enganoso"*. Ele ofereceu
        # uma explicação falsa para um número correto — porque eu entreguei, junto do dado, um
        # carimbo de uma fonte APOSENTADA. Frescor de fonte morta apresentado como frescor do
        # dado gera desconfiança no número certo, que é pior que não informar nada.
        #
        # O frescor que importa já está em `horas_desde_a_ultima_batida`, e ele vem do relógio
        # que está de pé: o nosso.
        "fonte_do_ponto": ("app/facial do Conecta PRO — o pull do Sólides foi desligado em "
                           "13 e 16/09/2026 por decisão do dono; a data de 17/09 que aparece em "
                           "relatórios antigos é dessa fonte aposentada e NÃO indica dado velho"),
        "escala_e_read_only": "eu não mudo escala; pedido de troca vira aprovação sua ou do Orlailson",
    })


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
    """Confere a escala postada e publica o resultado no GRUPO DE RELATÓRIO (Gestão).

    ⭐ DECISÃO DO JORDAN, 24/09/2026: *"não trata nada no privado, tudo nos grupos, com
    Orlailson no Gestão, eu quero acompanhar todas as tratativas."* Eu havia feito no privado
    dele; o dono quer a tratativa visível, e a razão é boa — decisão sobre escala que acontece
    em DM some, e ele fica fora do que o supervisor combinou.

    ⚠️ E ISSO NÃO AFROUXA A PAREDE, porque relatório não é conversa. A parede impede o **LLM**
    de improvisar resposta em grupo (`modo = observar` → `processar_incoming` recusa). Aqui o
    texto é composto por código determinístico, a partir de consulta ao banco, e publicado por
    uma chamada nossa. O Gestão continua `observar`: o José Luís não vai discutir lá, só
    publicar o que conferiu. As duas coisas convivem, e confundi-las seria abrir a porta que
    passei a noite fechando.

    Guardas, e cada uma tem motivo:

      · a escala tem de vir de quem SUPERVISIONA. Ela nomeia 3 a 9 pessoas e seus postos, e
        publicar isso porque qualquer um colou um texto parecido no grupo é vazamento;
      · o destino sai do BANCO (`recebe_relatorio`), não de constante: o Jordan muda de grupo
        sem ninguém mexer em código, e um JID fixo aqui viraria mentira no dia da mudança;
      · uma vez por mensagem (`wa_grupo_falas` guarda a marca). Reentrega do Chatwoot é normal;
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

    # Para onde vai: o grupo marcado como destino de relatório. Sem destino cadastrado eu NÃO
    # escolho um — publicar num grupo por palpite é pior que não publicar.
    destino = (await db.execute(text(
        "SELECT chatwoot_conversation_id, nome FROM wa_grupos "
        " WHERE recebe_relatorio AND chatwoot_conversation_id IS NOT NULL LIMIT 1"))).first()
    if not destino:
        return {"avisado": False, "motivo": "nenhum grupo marcado como destino de relatório "
                                            "(ou a conversa dele ainda não foi aprendida)",
                "conferencia": r}
    conv_destino, nome_destino = int(destino[0]), destino[1]

    quem = getattr(ident, "nome", None) or autor_fone or "supervisor"
    corpo = f"📋 *Escala de {r.get('dia')}* (postada por {quem})\n\n{msg}"
    try:
        enviado = await _publicar_no_grupo(conv_destino, corpo)
    except Exception as e:  # noqa: BLE001
        logger.error("supervisao: conferência não publicada no %s (%s)", nome_destino, e)
        return {"avisado": False, "motivo": f"falha ao publicar: {str(e)[:100]}", "conferencia": r}

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

    return {"avisado": bool(enviado), "para": nome_destino,
            "divergencias": len(r.get("divergencias") or []),
            "conferidos": r.get("conferidos"), "linhas": r.get("linhas")}


async def _publicar_no_grupo(conversation_id: int, texto: str) -> bool:
    """Publica texto NA CONVERSA do grupo (`private: false` — o grupo VÊ). Best-effort.

    ⚠️ Por que não `whatsapp_service.send_custom`: ele limpa e resolve TELEFONE
    (`_clean_phone` + `_resolve_jid`), e um JID de grupo (`120363…@g.us`) seria destruído no
    caminho — o envio falharia, ou pior, iria para um número inventado pela limpeza. Grupo se
    alcança pela CONVERSA que o Chatwoot já tem, e o `conversation_id` dela eu aprendo do
    tráfego (`wa_grupos.chatwoot_conversation_id`).

    ⚠️ `private: false` é a diferença entre isto e `_post_private_note`. Com `true` a mensagem
    fica só no painel do Chatwoot — foi exatamente o que aconteceu nas 5 respostas de hoje de
    madrugada, e é por isso que ninguém no grupo as viu. Aqui o dono QUER que o grupo veja.
    """
    import json as _json  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    import aiohttp  # noqa: PLC0415

    base = _os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    conta = _os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = _os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        logger.warning("supervisao: CHATWOOT_API_TOKEN ausente — relatório não publicado")
        return False
    url = f"{base}/api/v1/accounts/{conta}/conversations/{conversation_id}/messages"
    async with aiohttp.ClientSession() as s, s.post(
        url, data=_json.dumps({"content": texto, "message_type": "outgoing", "private": False}),
        headers={"api_access_token": token, "Content-Type": "application/json"},
        timeout=aiohttp.ClientTimeout(total=20),
    ) as r:
        if r.status in (200, 201):
            return True
        logger.error("supervisao: publicação no grupo falhou %s: %s", r.status, (await r.text())[:200])
        return False


async def grupo_pode_ver_nomes(db: AsyncSession, conversation_id: int | None) -> bool:
    """A conversa está num grupo com autorização EXPLÍCITA para dado nominal?

    ⚠️ Esta função existe porque eu cometi o erro de gravar a autorização e não ligá-la em nada.
    O Jordan autorizou às 16:20 ("no Gestão estão apenas José Luís, Jordan e Orlailson, pode
    expor qualquer informação ali"), eu criei `wa_grupos.dado_pessoal_ok`, e vinte minutos depois
    o agente respondeu no Gestão "nome de quem não bateu só no privado" — porque o TEXTO da
    restrição estava cravado no retorno da ferramenta e nenhuma linha consultava a coluna.

    **Autorização registrada no banco que nenhum código lê é autorização que não existe.** É a
    irmã exata do `tool_risk_manifest` que não gateia nada: o dado está lá, parece proteção (ou
    permissão), e o comportamento ignora.

    Fail-closed: na dúvida, `False` — não expor nome é o erro reversível.
    """
    if not conversation_id:
        return False
    try:
        row = (await db.execute(text(
            "SELECT jid FROM wa_grupos WHERE chatwoot_conversation_id = :c AND dado_pessoal_ok "
            "  AND modo = 'falar' LIMIT 1"), {"c": int(conversation_id)})).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("supervisao: não sei se o grupo %s pode ver nomes (%s)", conversation_id, e)
        return False
    if not row:
        return False

    # ⭐ A AUTORIZAÇÃO É CONFERIDA CONTRA QUEM ESTÁ NO GRUPO AGORA (24/09/2026). Ela repousava
    # numa frase do dono — "no Gestão estão apenas três pessoas" — e num comentário de coluna.
    # Alguém adicionado ao grupo derrubaria a premissa em SILÊNCIO, e o agente passaria a dizer
    # nome de colaborador na frente de quem entrou. Comentário não é parede; isto é.
    from modules.integrations.connectors.whatsapp import grupos as _grp  # noqa: PLC0415

    ok, novos = await _grp.grupo_ainda_e_o_autorizado(db, str(row[0]))
    if not ok:
        logger.error("supervisao: composição do grupo %s MUDOU (entrou: %s) — autorização de "
                     "dado nominal SUSPENSA até o dono reconfirmar", row[0], novos)
        return False
    return True


async def cobertura_por_escala(db: AsyncSession, *, dia=None, com_nomes: bool = False) -> dict[str, Any]:
    """Quem JÁ DEVERIA ter entrado, por escala, e quem bateu. Agregado — sem nome no grupo.

    ⭐ Nasceu de uma correção do Jordan no grupo Gestão (24/09/2026). O José Luís disse "46
    ainda não bateram, é turno que entra mais tarde" e ele respondeu: *"não vamos ter 46
    entrando mais tarde, veja as escalas, pois temos 12x36 e temos horário comercial —
    jardineiros, artífices, ASG — esses batem ponto."* Estava certo, e o agente admitiu o erro
    em vez de insistir.

    ⚠️ O ERRO DE FUNDO ERA O DENOMINADOR, e é maior do que parecia: `visao_operacao` compara
    batidas contra os **63 colaboradores ativos**, quando só **30 têm turno hoje** — os outros
    33 estão de folga. "46 ausentes" nunca foi ausência: era gente que não tinha nada a bater.
    Número certo sobre a base errada é número errado, e soa igualmente convincente.

    Aqui a base é o TURNO PREVISTO PARA HOJE, e o corte é a hora: só entra na conta quem já
    deveria ter entrado (`planned_start_time <= agora`, hora de Manaus). É isso que transforma
    "17 batidas" em "faltam 5 na 12x36 e 2 na 44h às 11:56" — a primeira frase não se age, a
    segunda sim.

    ⚠️ AGREGADO DE PROPÓSITO: devolve contagem por escala e por posto, nunca a lista de quem
    não bateu. Isso é grupo, e "quem não bateu" é dado de pessoa. Quem precisar do nome pede no
    privado, onde o papel `funcionario`/`supervisor` responde.
    """
    from datetime import date as _date  # noqa: PLC0415

    dia = dia or _date.today()
    # ⚠️ A hora de corte vem do BANCO (`now() - 4h`), não de `datetime.now()` do processo: o
    # container roda em UTC e a operação em Manaus. Pegar do banco mantém uma só fonte de
    # verdade para a hora em todas as consultas desta função.
    agora_hhmm = (await db.execute(text("SELECT (now() - interval '4 hours')::time"))).scalar()
    linhas = (await db.execute(text("""
        SELECT coalesce(e.escala_padrao, '(sem escala)') AS escala,
               count(*)                                                        AS turnos,
               count(*) FILTER (WHERE s.planned_start_time <= :agora)           AS ja_previstos,
               count(*) FILTER (WHERE s.planned_start_time <= :agora AND EXISTS (
                     SELECT 1 FROM gp_clock_punches p
                      WHERE p.employee_id = s.employee_id
                        AND p.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                                  AND (CAST(:d AS date) + s.planned_start_time) + interval '3 hours'
               ))                                                              AS bateram
          FROM shifts s JOIN employees e ON e.id = s.employee_id
         WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day AND e.status = 'ativo'
         GROUP BY 1 ORDER BY 2 DESC"""),
        {"d": dia, "agora": agora_hhmm})).mappings().all()

    # Onde o furo está, por POSTO — é a pergunta seguinte do supervisor, e sem nome de gente.
    postos = (await db.execute(text("""
        SELECT coalesce(p.name, '(sem posto)') AS posto,
               count(*) FILTER (WHERE s.planned_start_time <= :agora) AS previstos,
               count(*) FILTER (WHERE s.planned_start_time <= :agora AND NOT EXISTS (
                     SELECT 1 FROM gp_clock_punches g
                      WHERE g.employee_id = s.employee_id
                        AND g.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                                  AND (CAST(:d AS date) + s.planned_start_time) + interval '3 hours'
               ))                                                     AS sem_batida
          FROM shifts s JOIN employees e ON e.id = s.employee_id
          LEFT JOIN posts p ON p.id = s.post_id
         WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day AND e.status = 'ativo'
         GROUP BY 1 HAVING count(*) FILTER (WHERE s.planned_start_time <= :agora AND NOT EXISTS (
                     SELECT 1 FROM gp_clock_punches g
                      WHERE g.employee_id = s.employee_id
                        AND g.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                                  AND (CAST(:d AS date) + s.planned_start_time) + interval '3 hours'
               )) > 0
         ORDER BY 3 DESC"""), {"d": dia, "agora": agora_hhmm})).mappings().all()

    # ⭐ OS NOMES, quando o grupo tem autorização do dono (`dado_pessoal_ok`). O Jordan foi
    # explícito: *"manda ele dizer o nome de quem não bateu ponto no grupo, não precisa ser no
    # privado, pode ser no grupo de gestão, não haverá vazamento de informação."* No Gestão são
    # três pessoas, todas com autoridade sobre a operação.
    quem_nao_bateu: list[dict] = []
    if com_nomes:
        quem_nao_bateu = [dict(r) for r in (await db.execute(text("""
            SELECT e.nome, coalesce(p.name,'(sem posto)') AS posto,
                   to_char(s.planned_start_time,'HH24:MI') AS previsto,
                   coalesce(e.escala_padrao,'(sem)') AS escala
              FROM shifts s JOIN employees e ON e.id = s.employee_id
              LEFT JOIN posts p ON p.id = s.post_id
             WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day AND e.status = 'ativo'
               AND s.planned_start_time <= :agora
               AND NOT EXISTS (
                     SELECT 1 FROM gp_clock_punches g
                      WHERE g.employee_id = s.employee_id
                        AND g.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                                  AND (CAST(:d AS date) + s.planned_start_time) + interval '3 hours')
             ORDER BY s.planned_start_time, e.nome"""),
            {"d": dia, "agora": agora_hhmm})).mappings().all()]

    prev = sum(int(r["ja_previstos"]) for r in linhas)
    bat = sum(int(r["bateram"]) for r in linhas)
    return {
        "dia": str(dia),
        "hora_de_referencia_manaus": str(agora_hhmm)[:5],
        "por_escala": [{"escala": r["escala"], "turnos_hoje": int(r["turnos"]),
                        "ja_deveriam_ter_entrado": int(r["ja_previstos"]),
                        "bateram": int(r["bateram"]),
                        "sem_batida": int(r["ja_previstos"]) - int(r["bateram"])} for r in linhas],
        "postos_com_furo": [{"posto": r["posto"], "previstos": int(r["previstos"]),
                             "sem_batida": int(r["sem_batida"])} for r in postos],
        "total_previstos_ate_agora": prev,
        "total_bateram": bat,
        "total_sem_batida": prev - bat,
        # ⚠️ Vai explícito porque foi a confusão que gerou esta ferramenta: o total de
        # colaboradores NÃO é a base. Quem está de folga não tem o que bater.
        #
        # ⚠️ E o TEXTO muda com a autorização. Antes ele dizia sempre "nomes só no privado", e o
        # agente obedecia — inclusive no grupo onde o dono havia liberado. Instrução fixa no
        # retorno da ferramenta vira lei para o modelo; ela tem de refletir a permissão real.
        "quem_nao_bateu": quem_nao_bateu,
        "leia_assim": ("a base é TURNO PREVISTO PARA HOJE, não o total de colaboradores — "
                       "quem está de folga não entra na conta."
                       + (" Este grupo tem autorização do dono para dado nominal: DIGA os nomes "
                          "de quem não bateu, com posto e horário previsto."
                          if com_nomes else
                          " Nomes de quem não bateu só no privado, nunca neste grupo.")),
    }


async def escala_do_posto(db: AsyncSession, *, posto: str, dia=None, com_nomes: bool = False) -> dict[str, Any]:
    """QUEM está escalado num posto hoje: pessoa, cargo, escala, horário e se bateu.

    ⭐ Nasceu de um vão que apareceu no primeiro minuto de monitoramento (24/09/2026). O Jordan
    perguntou no Gestão *"qual a escala dos agentes de portaria do Ideal Flores hoje de dia?"* — a
    pergunta operacional mais básica que existe — e o agente respondeu, honestamente, que não
    tinha: *"não tenho o Ideal Flores aberto por tipo de escala; o sistema me dá o total na 12x36
    e na 44h e os furos por posto"*.

    Ele não inventou, e é por isso que o vão apareceu limpo em vez de virar resposta plausível.
    Mas `cobertura_por_escala` responde "quantos" e "quem FALTOU" — nunca "quem ESTÁ". Agregado
    responde a pergunta do supervisor sobre o conjunto; sobre UM posto, ele quer a lista.

    ⚠️ `com_nomes` vem de `grupo_pode_ver_nomes`, como nas outras. Sem autorização devolve
    contagem e horários, sem pessoa — o mesmo critério, uma decisão só.
    """
    from datetime import date as _date  # noqa: PLC0415

    dia = dia or _date.today()
    alvo = " ".join(str(posto or "").split())
    if len(alvo) < 3:
        return {"erro": "qual posto? me diz o nome (ex.: Ideal Flores, Green Hills)"}

    postos = (await db.execute(text(
        "SELECT id::text, name FROM posts "
        " WHERE unaccent(lower(name)) LIKE '%'||unaccent(lower(:a))||'%'"), {"a": alvo})).all()
    if not postos:
        return {"erro": f"não achei posto com {alvo!r} no nome"}
    if len(postos) > 1:
        # Ambiguidade é achado, não detalhe: escolher em silêncio daria a escala do posto errado.
        return {"ambiguo": True, "candidatos": [p[1] for p in postos],
                "mensagem": f"{alvo!r} casa com {len(postos)} postos — me diz qual"}
    post_id, post_nome = postos[0]

    agora = (await db.execute(text("SELECT (now() - interval '4 hours')::time"))).scalar()
    linhas = (await db.execute(text("""
        SELECT e.nome, e.cargo, coalesce(e.escala_padrao,'(sem)') AS escala,
               to_char(s.planned_start_time,'HH24:MI') AS entrada,
               to_char(s.planned_end_time,'HH24:MI')   AS saida,
               (s.planned_start_time <= :agora)        AS ja_devia,
               (SELECT to_char(min(g.punch_timestamp),'HH24:MI') FROM gp_clock_punches g
                 WHERE g.employee_id = s.employee_id
                   AND g.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                             AND (CAST(:d AS date) + s.planned_start_time) + interval '3 hours') AS bateu
          FROM shifts s JOIN employees e ON e.id = s.employee_id
         WHERE s.post_id = CAST(:p AS uuid) AND s.shift_date = :d
           AND s.is_active AND NOT s.is_off_day AND e.status = 'ativo'
         ORDER BY s.planned_start_time, e.nome"""),
        {"p": post_id, "d": dia, "agora": agora, "agora2": agora})).mappings().all()

    if not linhas:
        return {"posto": post_nome, "dia": str(dia), "turnos": 0,
                "mensagem": f"nenhum turno ativo no {post_nome} em {dia}"}

    def _item(r):
        base = {"escala": r["escala"], "entrada": r["entrada"], "saida": r["saida"],
                "bateu": r["bateu"], "ja_deveria_ter_entrado": bool(r["ja_devia"])}
        if com_nomes:
            base = {"quem": r["nome"], "cargo": r["cargo"], **base}
        return base

    faltam = [r for r in linhas if r["ja_devia"] and not r["bateu"]]
    return {
        "posto": post_nome, "dia": str(dia), "hora_de_referencia_manaus": str(agora)[:5],
        "turnos": len(linhas),
        "escalados": [_item(r) for r in linhas],
        "sem_batida_ate_agora": len(faltam),
        "leia_assim": ("`bateu` vazio em quem JÁ deveria ter entrado é o que olhar; vazio em "
                       "quem entra mais tarde é normal."
                       + ("" if com_nomes else " Este grupo não tem autorização para nome: "
                          "devolvo horário e escala, sem pessoa.")),
    }


#: Tolerância de atraso, em minutos. Abaixo disso a batida conta como pontual — ninguém bate no
#: segundo exato, e acusar 3 minutos como atraso treina o supervisor a ignorar o relatório.
TOLERANCIA_ATRASO_MIN = 10

#: Status de batida que são EXCEÇÃO. ⚠️ `pending` NÃO está aqui, e é a distinção que mais importa
#: nesta função: das 148 batidas de entrada dos últimos 7 dias, TODAS estão `pending`. É o estado
#: NORMAL da casa, não uma pendência. Tratar default de coluna como evidência de problema faria o
#: relatório acusar 100% das batidas — alarme que soa sempre.
_STATUS_EXCEÇÃO = {
    "pending_contingencia": "batida por contingência, aguardando o DP validar",
    "fora_local": "bateu FORA do local do posto (geofence)",
    "rejected": "batida recusada",
    "recusada": "batida recusada",
}


async def situacao_do_turno(db: AsyncSession, *, posto: str | None = None, dia=None,
                            hora: str | None = None, cargo: str | None = None,
                            com_nomes: bool = False) -> dict[str, Any]:
    """Por posto → turno → pessoa: QUEM, QUANDO, ONDE e POR QUÊ. O pedido do Jordan de 24/09.

    ⭐ É o item 3 do que o próprio agente listou no grupo ("status derivado"), e o que faltava
    para ele responder "por quê" em vez de "quantos". Cada turno sai com um veredito:

        COBERTO · ATRASO (com minutos) · SEM_BATIDA · FOLGA · AFASTADO

    e, quando há, o MOTIVO vindo do dado — não de suposição: contingência aguardando DP, batida
    fora do geofence, facial que não reconheceu, batida feita offline, justificativa vinculada.

    ⭐ O DADO JÁ EXISTIA E EU NÃO LIA. `gp_clock_punches` tem `punch_type`, `status`,
    `device_type`, `device_id`, `latitude/longitude`, `dentro_geofence`,
    `distancia_posto_metros`, `facial_match`, `facial_confidence`, `is_offline` e
    `justification_id`. A minha versão anterior pegava `min(punch_timestamp)` e jogava o resto
    fora — o agente respondia "1 sem batida" quando podia dizer "bateu por contingência, o DP
    não validou". Capacidade que existe e ninguém lê é capacidade que não existe.

    ⚠️ `pending` NÃO é problema: é o estado de TODAS as batidas da casa. Ver `_STATUS_EXCEÇÃO`.
    """
    from datetime import date as _date  # noqa: PLC0415

    dia = dia or _date.today()
    agora = (await db.execute(text("SELECT (now() - interval '4 hours')::time"))).scalar()

    filtro, p = "", {"d": dia, "agora": agora, "tol": TOLERANCIA_ATRASO_MIN}
    if posto and len(str(posto).strip()) >= 3:
        filtro = " AND unaccent(lower(pp.name)) LIKE '%'||unaccent(lower(:po))||'%'"
        p["po"] = " ".join(str(posto).split())
    # ⭐ FILTRO POR HORA (24/09/2026). O Jordan pediu "todos os agentes que assumem às 18:00 e
    # às 19:00, de todos os condomínios" — a pergunta de planejamento mais natural que existe —
    # e o agente respondeu que não conseguia montar. Era o meu teto que escondia.
    # ⭐ FILTRO POR CARGO (24/09/2026). O Jordan pediu "todos os AGENTES DE PORTARIA que assumem
    # às 18h e 19h" e o agente respondeu misturando o Geilson, que é JARDINEIRO. A ferramenta
    # devolvia o cargo em cada linha e nenhum filtro — então ele trouxe tudo e citou quem não
    # pertencia à pergunta. Devolver o campo e esperar que o modelo filtre é confiar juízo onde
    # cabe consulta: a operação tem agente de portaria, ASG, jardineiro e artífice no mesmo posto,
    # e misturá-los muda a conclusão de quem lê.
    if cargo and len(str(cargo).strip()) >= 3:
        filtro += " AND unaccent(lower(e.cargo)) LIKE '%'||unaccent(lower(:cg))||'%'"
        p["cg"] = " ".join(str(cargo).split())
    if hora and str(hora).strip():
        _hs = [h for h in re.findall(r"\d{1,2}", str(hora))][:4]
        if _hs:
            filtro += " AND EXTRACT(HOUR FROM s.planned_start_time) = ANY(:horas)"
            p["horas"] = [int(h) for h in _hs]

    linhas = (await db.execute(text(f"""
        SELECT pp.name AS posto, e.nome, e.cargo, coalesce(e.escala_padrao,'(sem)') AS escala,
               e.status AS situacao,
               -- ⭐ HORÁRIO VIGENTE MANDA SOBRE O DO TURNO (item 2, 24/09/2026). A Celiane bateu
               -- 09:00 e o relatório a acusou de 60min de atraso porque `shifts` diz 08:00 — e o
               -- Jordan corrigiu: 09:00–18:00 é o horário CERTO dela. Sem vigência, ela apareceria
               -- atrasada TODO DIA, e um relatório que acusa quem está certo é pior que nenhum.
               --
               -- `coalesce` e não substituição: a vigência cobre quem tem exceção registrada; o
               -- resto segue pelo turno, que é o certo para a maioria.
               coalesce(hv.entrada, s.planned_start_time) AS prev_ent,
               coalesce(hv.saida,   s.planned_end_time)   AS prev_sai,
               (hv.entrada IS NOT NULL) AS horario_por_vigencia,
               hv.intervalo_min,
               s.is_off_day,
               (s.planned_start_time <= :agora) AS ja_devia,
               g.punch_timestamp AS bateu_em, g.status AS bat_status, g.punch_type,
               g.dentro_geofence, g.distancia_posto_metros, g.facial_match, g.is_offline,
               g.device_type, g.justification_id,
               EXISTS (SELECT 1 FROM hr_vacation_requests v WHERE v.employee_id = e.id
                        AND upper(v.status) IN ('APPROVED','IN_PROGRESS','SCHEDULED')
                        AND :d BETWEEN v.start_date AND v.end_date) AS de_ferias,
               -- ⭐ ITEM 4 do pedido: o turno vem MARCADO quando há pendência ou afastamento,
               -- "senão eu repito cobrança já resolvida" (palavras do próprio agente no grupo).
               --
               -- ⚠️ `sst_afastamentos` e NÃO `time_justifications`: aquela é a tabela grande do
               -- DP e está com ZERO linhas. Se eu tivesse ligado nela, a conclusão seria "não
               -- existe justificativa nenhuma nesta casa" — verde que não prova nada porque a
               -- tabela está vazia. As que têm dado são `gp_justifications` (14, ligada à
               -- BATIDA por `punch_id`) e `sst_afastamentos` (8, afastamento de verdade).
               (SELECT af.tipo || coalesce(' — ' || af.motivo, '')
                  FROM sst_afastamentos af
                 WHERE af.employee_id = e.id
                   AND :d BETWEEN af.data_inicio
                              AND coalesce(af.data_retorno, af.data_fim_prevista, :d)
                   AND lower(coalesce(af.status,'')) NOT IN ('encerrado','cancelado')
                 LIMIT 1) AS afastamento,
               -- ⭐ A ANOMALIA QUE EXPÔS O GEILSON. Ele está `ativo`, com 26 turnos em setembro,
               -- e a última batida é de 12/09 — doze dias. O afastamento pelo INSS existe na vida
               -- real e NÃO está em `sst_afastamentos`, então o sistema o escala todo dia e conta
               -- falta. Um dia sem bater é ocorrência; doze dias é CADASTRO ERRADO, e reportar os
               -- dois do mesmo jeito faz o supervisor caçar a pessoa em vez de corrigir o
               -- registro. Os 26 turnos sem batida também entram no banco de horas.
               -- ⭐ DESVIO SISTEMÁTICO = CADASTRO ERRADO, NÃO ATRASO (24/09/2026).
               -- Medido: 8 pessoas desviam >25min do previsto de forma consistente em 5–13 dias,
               -- e DUAS delas batem exatamente 60 min antes, no minuto zero, todo dia. Ninguém
               -- chega uma hora antes por acaso sete dias seguidos — o horário do cadastro está
               -- errado e a pessoa é pontual.
               --
               -- ⚠️ E a assimetria é o que torna isso urgente: 6 das 8 batem ANTES do previsto.
               -- O relatório de atraso acusaria as 2 que chegam depois e SILENCIARIA as 6 cujo
               -- cadastro está igualmente errado — erro que não dispara alarme é o que sobrevive
               -- mais tempo. Detectar a CLASSE do erro vale mais que corrigir cada caso.
               (SELECT round(avg(EXTRACT(EPOCH FROM (p2.punch_timestamp::time - s.planned_start_time))/60))
                  FROM gp_clock_punches p2 JOIN shifts s2 ON s2.employee_id = p2.employee_id
                       AND s2.shift_date = p2.punch_timestamp::date AND s2.is_active AND NOT s2.is_off_day
                 WHERE p2.employee_id = e.id AND p2.punch_type = 'entrada'
                   AND p2.punch_timestamp::date BETWEEN CAST(:d AS date) - 21 AND CAST(:d AS date) - 1
                   AND s2.planned_start_time = s.planned_start_time) AS desvio_tipico_min,
               -- ⚠️ E O DISCRIMINADOR É O DESVIO-PADRÃO, NÃO A MÉDIA. Medido: o Antonio Carlos
               -- tem média +67min e mínimo +30 — ele VARIA, é irregularidade real de pessoa. Já o
               -- Ediwilson e o Ailton batem 60min antes no minuto ZERO, todo dia: variação ~0.
               -- Média alta prova que algo está fora do previsto; só a variação BAIXA prova que é
               -- o previsto que está errado. Sem isso eu chamaria de "cadastro errado" quem chega
               -- a hora que quer — e daria a ele um álibi que o dado não sustenta.
               (SELECT round(coalesce(stddev_pop(EXTRACT(EPOCH FROM (p4.punch_timestamp::time - s.planned_start_time))/60), 999))
                  FROM gp_clock_punches p4 JOIN shifts s4 ON s4.employee_id = p4.employee_id
                       AND s4.shift_date = p4.punch_timestamp::date AND s4.is_active AND NOT s4.is_off_day
                 WHERE p4.employee_id = e.id AND p4.punch_type = 'entrada'
                   AND p4.punch_timestamp::date BETWEEN CAST(:d AS date) - 21 AND CAST(:d AS date) - 1
                   AND s4.planned_start_time = s.planned_start_time) AS desvio_variacao,
               (SELECT count(*) FROM gp_clock_punches p3 JOIN shifts s3 ON s3.employee_id = p3.employee_id
                       AND s3.shift_date = p3.punch_timestamp::date AND s3.is_active AND NOT s3.is_off_day
                 WHERE p3.employee_id = e.id AND p3.punch_type = 'entrada'
                   AND p3.punch_timestamp::date BETWEEN CAST(:d AS date) - 21 AND CAST(:d AS date) - 1
                   AND s3.planned_start_time = s.planned_start_time) AS dias_medidos,
               (SELECT (CURRENT_DATE - max(gp.punch_timestamp)::date)
                  FROM gp_clock_punches gp WHERE gp.employee_id = e.id) AS dias_sem_bater,
               (SELECT j.justification_type || ' (' || coalesce(j.status,'?') || ')'
                  FROM gp_justifications j
                 -- ⚠️ `gp_justifications.employee_id` é VARCHAR e `employees.id` é uuid — a
                 -- comparação direta estoura. Mais um tipo divergente na mesma família de
                 -- `diaria_diaristas.id` (integer): nesta base a chave de pessoa aparece em três
                 -- tipos diferentes, e supor um deles é errar um terço das vezes.
                 WHERE j.employee_id = CAST(e.id AS text) AND j.created_at::date = :d
                 ORDER BY j.created_at DESC LIMIT 1) AS justificativa_do_dia
          FROM shifts s
          JOIN employees e ON e.id = s.employee_id
          JOIN posts pp ON pp.id = s.post_id
          LEFT JOIN ponto_horario_vigencia hv
                 ON hv.employee_id = e.id
                AND :d BETWEEN hv.vigencia_inicio AND coalesce(hv.vigencia_fim, :d)
          LEFT JOIN LATERAL (
              SELECT * FROM gp_clock_punches x
               WHERE x.employee_id = s.employee_id AND x.punch_type = 'entrada'
                 AND x.punch_timestamp BETWEEN (CAST(:d AS date) + s.planned_start_time) - interval '3 hours'
                                           AND (CAST(:d AS date) + s.planned_start_time) + interval '4 hours'
               ORDER BY x.punch_timestamp LIMIT 1) g ON TRUE
         -- ⚠️ NÃO filtro mais por `status = 'ativo'`, e isso VIROU um achado. Com o filtro, quem
         -- está escalado sem estar ativo ficava INVISÍVEL no relatório — e existe: KEYSON DA
         -- SILVA PINTO está `demitido` e tem turno hoje. O posto conta com alguém que não vem, e
         -- o relatório não dizia nada porque a linha era descartada antes de ser avaliada.
         --
         -- Filtro que esconde o caso anômalo é pior que filtro nenhum: ele produz um relatório
         -- limpo sobre uma operação furada. Agora essas linhas ENTRAM e ganham veredito próprio.
         WHERE s.shift_date = :d AND s.is_active {filtro}
         ORDER BY pp.name, s.planned_start_time, e.nome"""), p)).mappings().all()

    if not linhas:
        return {"dia": str(dia), "posto_filtrado": posto, "turnos": 0,
                "mensagem": "nenhum turno ativo com esse filtro"}

    por_posto: dict[str, list] = {}
    resumo_status: dict[str, int] = {}
    for r in linhas:
        # ── o veredito ──
        _st = str(r["situacao"] or "").lower()
        if _st in ("demitido", "desligado", "inativo", "candidato"):
            # O turno existe e a pessoa não. Isto é buraco de COBERTURA disfarçado de escala
            # cheia — e é o que o filtro antigo escondia.
            veredito = "ESCALADO_SEM_VINCULO"
            motivo = (f"a pessoa está {_st!r} no cadastro e tem turno hoje — o posto conta com "
                      f"quem não vem. Corrigir a escala ou o cadastro.")
            atraso = None
        elif _st in ("afastado_inss", "afastado", "suspenso", "ferias", "férias"):
            veredito, motivo, atraso = "AFASTADO", f"cadastro: {_st}", None
        elif r["is_off_day"]:
            veredito, motivo, atraso = "FOLGA", None, None
        elif r["afastamento"]:
            # Afastamento vem ANTES de férias e de tudo: quem está afastado não deve ser
            # cobrado por não bater, e o motivo é o que o SST registrou, não suposição minha.
            veredito, motivo, atraso = "AFASTADO", str(r["afastamento"])[:120], None
        elif r["de_ferias"]:
            veredito, motivo, atraso = "AFASTADO", "férias aprovada no período", None
        elif r["bateu_em"]:
            prev = datetime.combine(dia, r["prev_ent"])
            atraso = int((r["bateu_em"] - prev).total_seconds() // 60)
            # Desvio típico ≥25min com ≥4 dias medidos, e o atraso de hoje dentro de 20min
            # desse padrão → não é atraso, é o horário do cadastro que está errado.
            _dt, _nd = r["desvio_tipico_min"], int(r["dias_medidos"] or 0)
            _var = float(r["desvio_variacao"] or 999)
            # Consistente = média fora do previsto E variação baixa. 15min de variação tolera o
            # trânsito de quem é pontual, e exclui quem chega a hora que quer.
            _padrao = (_dt is not None and _nd >= 4 and abs(float(_dt)) >= 25 and _var <= 15)
            if _padrao:
                veredito = "HORARIO_SUSPEITO"
            elif atraso > TOLERANCIA_ATRASO_MIN:
                veredito = "ATRASO"
            else:
                veredito = "COBERTO"
            motivo = _STATUS_EXCEÇÃO.get(str(r["bat_status"] or ""))
            # Motivos que se somam ao status, e cada um vem do DADO, não de suposição.
            extras = []
            if r["dentro_geofence"] is False:
                d = r["distancia_posto_metros"]
                extras.append(f"fora do geofence{f' ({int(d)}m do posto)' if d else ''}")
            if r["facial_match"] is False:
                extras.append("facial não reconheceu")
            if r["is_offline"]:
                extras.append("batida offline, sincronizada depois")
            if r["justification_id"] or r["justificativa_do_dia"]:
                extras.append(f"justificativa: {r['justificativa_do_dia'] or 'vinculada à batida'}")
            motivo = "; ".join(x for x in ([motivo] if motivo else []) + extras) or None
            if _padrao:
                motivo = (f"bate {abs(int(float(_dt)))}min {'depois' if float(_dt) > 0 else 'antes'} "
                          f"do previsto em {_nd} dias, com variação de só {int(_var)}min — o "
                          f"horário do CADASTRO está errado e a pessoa é pontual. "
                          f"Registrar a vigência corrige.")
            elif atraso is not None and atraso < 0:
                veredito, atraso = "COBERTO", 0  # bateu antes da hora, sem padrão: pontual
        elif r["ja_devia"]:
            # ⭐ SEM_BATIDA COM JUSTIFICATIVA NÃO É COBRANÇA — é fila do DP. Sem esta distinção o
            # relatório manda o supervisor atrás de quem já abriu justificativa, e ele aprende a
            # desconfiar do relatório inteiro.
            dias = r["dias_sem_bater"]
            if r["justificativa_do_dia"]:
                veredito = "SEM_BATIDA_JUSTIFICADA"
                motivo = f"já tem justificativa aberta: {r['justificativa_do_dia']}"
            elif dias is not None and dias >= 3:
                # Não chamo de falta: chamo de cadastro suspeito, que é o que o dado sustenta.
                veredito = "AUSENTE_PROLONGADO"
                motivo = (f"{dias} dias sem bater e ainda ativo/escalado — provável afastamento, "
                          f"férias ou desligamento NÃO lançado. Isto é cadastro, não falta.")
            else:
                veredito, motivo = "SEM_BATIDA", None
            atraso = None
        else:
            veredito, motivo, atraso = "AGUARDANDO", "turno ainda não começou", None

        resumo_status[veredito] = resumo_status.get(veredito, 0) + 1
        item = {"escala": r["escala"],
                **({"horario_corrigido_por_vigencia": True} if r["horario_por_vigencia"] else {}),
                "previsto": f"{r['prev_ent'].strftime('%H:%M')}–{r['prev_sai'].strftime('%H:%M')}",
                "bateu": r["bateu_em"].strftime("%H:%M:%S") if r["bateu_em"] else None,
                "status": veredito}
        if atraso:
            item["atraso_min"] = atraso
        if motivo:
            item["por_que"] = motivo
        if r["device_type"]:
            item["onde"] = r["device_type"]
        if com_nomes:
            item = {"quem": r["nome"], "cargo": r["cargo"], **item}
        por_posto.setdefault(r["posto"], []).append(item)

    return {
        "dia": str(dia), "hora_de_referencia_manaus": str(agora)[:5],
        "posto_filtrado": posto, "cargo_filtrado": cargo, "hora_filtrada": hora,
        "turnos": len(linhas),
        "por_status": resumo_status,
        # ⚠️ TETO. Hoje são 29 turnos em 8 postos; com os condomínios entrando isso cresce e vira
        # o mesmo problema do `resumo_grupos`, que eu já cortei de 17.648 para 1.759 tokens. Sem
        # filtro de posto, devolvo o RESUMO por status e só os postos com exceção — quem quer a
        # lista de um posto pede o posto.
        # ⚠️ AGUARDANDO FICA. Minha primeira versão do teto cortava COBERTO **e** AGUARDANDO
        # sem filtro — e AGUARDANDO é justamente "quem vai assumir". O Jordan perguntou quem
        # assume às 18h e 19h em todos os condomínios e o agente disse que não conseguia: eu
        # havia otimizado para o caso que IMAGINEI (o supervisor só quer problema) e quebrado a
        # pergunta de planejamento. Corto só COBERTO, que é o volume (14 de 29 hoje).
        "postos": (por_posto if (posto or hora) else
                   {k: [x for x in v if x["status"] != "COBERTO"]
                    for k, v in por_posto.items()
                    if any(x["status"] != "COBERTO" for x in v)}),
        "sem_filtro_omito_os_cobertos": not bool(posto or hora),
        "tolerancia_atraso_min": TOLERANCIA_ATRASO_MIN,
        "leia_assim": ("veredito por turno: COBERTO · ATRASO (com minutos) · SEM_BATIDA · FOLGA · "
                       "AFASTADO · AGUARDANDO (turno não começou). `por_que` só aparece quando o "
                       "DADO traz o motivo — status `pending` é o normal da casa e NÃO é problema. "
                       "SEM_BATIDA_JUSTIFICADA já está com o DP: NÃO cobre de novo. "
                       "AUSENTE_PROLONGADO é CADASTRO a corrigir (afastamento/férias/desligamento "
                       "não lançado), NÃO é falta da pessoa — não cobre quem está nesse estado. "
                       "`horario_corrigido_por_vigencia` significa que usei o horário real da "
                       "pessoa, não o do turno. ESCALADO_SEM_VINCULO é grave e urgente: há turno "
                       "para quem está demitido/inativo, então o posto acha que está coberto."
                       + (" Este grupo está autorizado a dado nominal: DIGA os nomes aqui."
                          if com_nomes else
                          " Sem autorização nominal neste grupo: respondo sem pessoa.")),
    }


async def auditoria_cadastro_vs_gov(db: AsyncSession) -> dict[str, Any]:
    """Onde o cadastro, a operação e o GOVERNO discordam. Só leitura, nunca transmite.

    ⭐ Nasceu de um pedido do Jordan (24/09/2026): *"nosso sistema precisa estar 100% online e
    sincronizado com o eSocial, ter ele como fonte da verdade, assim nunca fica defasado."*

    ⚠️ E aqui eu divirjo com medição, porque a direção importa: **o eSocial é DESTINO, não
    fonte.** Ele recebe o que nós enviamos (S-2200 admissão, S-2230 afastamento, S-2299
    desligamento); não existe lista canônica de colaborador que ele devolva. Fazer dele fonte da
    verdade inverte o fluxo — nada apareceria lá que não tivesse saído daqui primeiro.

    O caso do Geilson prova: ele não está afastado no nosso cadastro, então NADA foi transmitido.
    Nenhum sync o traria, porque não há o que trazer.

    ⭐ Mas a necessidade por trás do pedido está certa, e o uso certo do eSocial é ser AUDITOR, não
    fonte: o que foi transmitido é prova de que existe, e a DIVERGÊNCIA entre o que registramos e
    o que transmitimos é o sinal mais forte de dado defasado que existe nesta casa.

    🔴 Medido ao escrever isto: os 8 afastamentos de `sst_afastamentos` estão TODOS
    `nao_transmitida` — inclusive o acidente de trajeto da Cintia, de 21/05, que tem prazo legal
    mais curto. Não é atraso de sistema: é exposição.

    ⚠️ ESTA FUNÇÃO NÃO TRANSMITE NADA. Transmitir gera evento real no governo e é ação do dono,
    com OTP, pela tela. Aqui só se mede e se relata.
    """
    afast = (await db.execute(text("""
        SELECT coalesce(a.employee_nome, e.nome, '(sem nome)') AS quem, a.tipo, a.data_inicio,
               a.status, coalesce(a.esocial_status,'(sem status)') AS gov,
               (CURRENT_DATE - a.data_inicio) AS dias
          FROM sst_afastamentos a LEFT JOIN employees e ON e.id = a.employee_id
         ORDER BY a.data_inicio DESC"""))).mappings().all()

    # Quem a OPERAÇÃO trata como afastado (não bate há dias, segue escalado) e o cadastro não.
    sem_lancamento = (await db.execute(text("""
        SELECT e.nome, e.status,
               (CURRENT_DATE - (SELECT max(g.punch_timestamp)::date FROM gp_clock_punches g
                                 WHERE g.employee_id = e.id)) AS dias_sem_bater,
               (SELECT count(*) FROM shifts s WHERE s.employee_id = e.id
                 AND s.shift_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                 AND s.is_active AND NOT s.is_off_day) AS turnos_no_mes
          FROM employees e
         WHERE e.status = 'ativo'
           AND (SELECT max(g.punch_timestamp)::date FROM gp_clock_punches g
                 WHERE g.employee_id = e.id) < CURRENT_DATE - 3
           AND EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id
                        AND s.shift_date = CURRENT_DATE AND s.is_active AND NOT s.is_off_day)
         ORDER BY 3 DESC"""))).mappings().all()

    # Escalado hoje sem vínculo — buraco de cobertura que a escala esconde.
    sem_vinculo = (await db.execute(text("""
        SELECT e.nome, e.status, p.name AS posto
          FROM shifts s JOIN employees e ON e.id = s.employee_id
          LEFT JOIN posts p ON p.id = s.post_id
         WHERE s.shift_date = CURRENT_DATE AND s.is_active AND NOT s.is_off_day
           AND e.status IN ('demitido','desligado','inativo','candidato')"""))).mappings().all()

    nao_transmitidos = [dict(a) for a in afast if str(a["gov"]).startswith("nao_")]

    # ⭐ O ESPELHO DO eSOCIAL É FONTE SOBRE QUEM ESTÁ NA EMPRESA — o Jordan estava certo e minha
    # objeção era parcial. Eu disse "eSocial é destino, não fonte": verdade para o que NÓS
    # enviamos, e falso para o quadro completo. A Portte transmite do lado dela, e
    # `esocial_eventos_espelho` traz o vínculo LEGAL de volta: 26 S-2230 (afastamento) e 5 S-2299
    # (desligamento), por CPF.
    #
    # 🔴 A medição que fechou a discussão: o GEILSON está `ativo` no nosso cadastro, escalado 27
    # vezes em setembro, e tem **S-2299 — DESLIGAMENTO — em 30/06**. Não era "afastamento não
    # lançado" como eu reportei: era desligamento de junho que nunca chegou aqui. E o KEYSON, que
    # o nosso diz `demitido`, tem S-2230 (afastamento). Os dois estão TROCADOS entre as fontes.
    #
    # ⚠️ O limite é de DATA, não de conceito: o espelho vai até julho. Movimentação de agosto e
    # setembro não está lá — resolve Geilson e Keyson, não resolve o Euler. Para ser fonte viva
    # precisa de sync contínuo do espelho, que hoje não roda. Digo isso no retorno para ninguém
    # concluir "não está no eSocial, então não houve".
    divergencia_gov = (await db.execute(text("""
        SELECT e.nome, e.status AS nosso_status, e.cargo,
               x.tipo AS evento_esocial, x.dt_evento::date AS quando,
               (SELECT count(*) FROM shifts s WHERE s.employee_id = e.id
                 AND s.shift_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                 AND s.is_active AND NOT s.is_off_day) AS turnos_30d
          FROM employees e
          JOIN LATERAL (
              SELECT y.tipo, y.dt_evento FROM esocial_eventos_espelho y
               WHERE regexp_replace(coalesce(y.cpf_trabalhador,''), '\D', '', 'g')
                     = regexp_replace(coalesce(e.cpf,''), '\D', '', 'g')
                 AND y.tipo IN ('S-2299','S-2230')
               ORDER BY y.dt_evento DESC LIMIT 1) x ON TRUE
         WHERE regexp_replace(coalesce(e.cpf,''), '\D', '', 'g') <> ''
           AND ((x.tipo = 'S-2299' AND e.status NOT IN ('demitido','desligado','inativo'))
             OR (x.tipo = 'S-2230' AND e.status = 'ativo'))
         ORDER BY x.dt_evento"""))).mappings().all()

    return {
        "divergencia_com_esocial": [dict(x) for x in divergencia_gov],
        "esocial_cobre_ate": (await db.execute(text(
            "SELECT max(dt_evento)::date FROM esocial_eventos_espelho"))).scalar(),
        "afastamentos_registrados": len(afast),
        "nao_transmitidos_ao_esocial": nao_transmitidos,
        "afastamento_provavel_sem_lancamento": [dict(x) for x in sem_lancamento],
        "escalado_sem_vinculo": [dict(x) for x in sem_vinculo],
        "leia_assim": (
            "⚠️ `divergencia_com_esocial` é o mais forte: o espelho traz o vínculo LEGAL "
            "(S-2299 desligamento, S-2230 afastamento) transmitido pela contabilidade. Quem o "
            "eSocial diz desligado e o nosso cadastro diz ativo está ESCALADO SEM VÍNCULO — e o "
            "número de turnos vai ao lado. ⚠️ MAS o espelho cobre só até `esocial_cobre_ate`: "
            "ausência ali NÃO prova que não houve movimentação depois. "
            "Sobre o que NÓS enviamos: só chega lá o que sai daqui. Então 'defasado' se "
            "mede por DIVERGÊNCIA — afastamento registrado e não transmitido, pessoa que a "
            "operação trata como afastada e o cadastro diz ativa, e turno para quem não tem "
            "vínculo. ⚠️ Eu NÃO transmito nada: transmitir gera evento real no governo e é ação "
            "do dono, pela tela, com OTP."),
    }


async def registrar_ajuste_de_escala(db: AsyncSession, *, relato: str, quem_relatou: str | None = None,
                                     posto: str | None = None) -> dict[str, Any]:
    """Registra ajuste de escala RELATADO POR TERCEIRO — supervisor falando de outra pessoa.

    🔴 Existe porque faltava, e a falta produziu um rótulo errado na Central. Em 24/09 o Orlailson
    disse no Gestão "hoje é a Maiara Muniz, Eidy não faz mais parte de lá", e o agente registrou
    o relato — CERTO no texto — usando `abrir_pendencia_dp`, a única ferramenta de escrita que eu
    havia lhe dado no grupo. Resultado: um ajuste de escala entrou como
    *"ORLAILSON PAIVA PEREIRA: outro assunto de DP relatado pelo funcionário"*.

    O texto estava correto e o cabeçalho enganava quem lê a lista. **Ferramenta que falta não
    produz silêncio — produz uso torto da ferramenta vizinha**, e o registro fica difícil de
    achar justamente quando alguém precisa dele.

    ⚠️ Diferente de `registrar_pedido_de_escala`: lá quem pede é a PRÓPRIA pessoa (falta, troca,
    folga) e o rascunho sai no nome dela, com sugestão de substituto. Aqui quem fala é o
    supervisor SOBRE a escala de outro, e o que importa é o ajuste, não a autorização de alguém.

    NÃO altera escala. Nunca. Vira rascunho para o Jordan ou o Orlailson aplicarem na tela.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    from modules.ai.conversation.services.orquestrador.acoes.base import ROLES_KIT_OP  # noqa: PLC0415
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho  # noqa: PLC0415

    txt = " ".join(str(relato or "").split())
    if len(txt) < 12:
        return {"erro": "me diz o que precisa ser ajustado, com posto e pessoas"}
    quem = quem_relatou or "supervisor"
    alvo = f" — {posto}" if posto else ""
    nome_curto = txt[:90]

    from datetime import UTC, datetime, timedelta  # noqa: PLC0415
    dia = (datetime.now(UTC) - timedelta(hours=4)).strftime("%Y-%m-%d")

    return await criar_rascunho(
        db, SimpleNamespace(id=None, nome=quem, name=quem),
        tipo="escala_pedido",
        modulo="operacional",
        titulo=f"Ajustar escala{alvo}: {nome_curto}",
        resumo=(f"AJUSTE DE ESCALA relatado por {quem}"
                f"{f' sobre o posto {posto}' if posto else ''}: \"{txt[:400]}\". "
                f"Aprovar AUTORIZA o ajuste; aplicar na escala continua sendo clique humano."),
        payload={"relato": txt[:1000], "relatado_por": quem, "posto": posto,
                 "origem": "grupo", "aplica_automaticamente": False},
        gate="🟡", requires_otp=False, roles_aprovador=ROLES_KIT_OP,
        idempotency_key=f"ajuste_escala:{(posto or 'sem_posto')}:{dia}:{hash(txt) % 10**8}",
    )
