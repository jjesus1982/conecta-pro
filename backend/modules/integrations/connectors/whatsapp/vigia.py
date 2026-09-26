"""Vigia de postos em tempo real — avisa o Gestão no MINUTO do problema, não às 08:30.

🔴 POR QUE ESTE ARQUIVO NASCEU EM 26/09/2026 — o dono pedindo o que faltava, às 07:07 de um
sábado, depois de ele mesmo ter que fazer o trabalho:

    Jordan — "e os outros postos, como estão?"
    José Luís — "às 07h eu não consigo disparar sozinho aqui. **Me marca às 07:05** que eu puxo"

E o veredito dele: *"preciso saber assim que houver um problema pra eu resolver, e não depois
de ele ter acontecido"*.

O diagnóstico já existia e era bom: `supervisao.situacao_do_turno()` dá dez veredictos por
turno (COBERTO · ATRASO · SEM_BATIDA · AUSENTE_PROLONGADO · ESCALADO_SEM_VINCULO · …). O que
não existia era **alguém olhando sem ser chamado**. O único olho automático era
`turno_fechar_cobertura` às 08:30 — depois da troca das 06:00 e das 07:00, ou seja, relatório
de autópsia. Entre 06:00 e 08:30 o sistema sabia do problema e não contava a ninguém.

⭐ E O FURO QUE NENHUM VEREDITO PEGAVA. O Jordan achou sozinho no mesmo diálogo:

    "Green Hills não tem ninguém entrando às 07:00 — só o Mauricio 19–07, que está SAINDO.
     Se a troca lá é 07:00, quem assume **não está na escala**. Esse é o furo."

`situacao_do_turno` percorre os turnos que EXISTEM e julga cada um. Um posto onde ninguém foi
escalado não produz linha nenhuma — e sem linha não há veredito, então o posto some do
relatório em vez de ficar vermelho. **Ausência de escala é invisível para verificação por
turno.** É a mesma família do que eu venho errando: o vazio falha ABERTO. Aqui ele passa a
falhar fechado, com `BURACO_DE_ESCALA` derivado de quem SAI sem que alguém ENTRE.

## As três coisas que este módulo NÃO faz, de propósito

1. **Não repete.** `wa_vigia_avisos` é a memória: mesma pessoa + mesmo dia + mesmo turno +
   mesmo veredito avisa UMA vez. Sem isso, um beat de 5 minutos publicaria o mesmo atraso 18
   vezes antes das 08:30 — e ruído treina o dono a não ler o grupo, que é exatamente o que ele
   disse do relatório antigo. Já cometi esse erro no sino de "conversas frias", onde uma pessoa
   ocupava 15 das 15 vagas.

2. **Não cobra quem ainda não deveria ter batido.** Turno das 19:00 às 07:10 da manhã não é
   atraso, é futuro. Eu caí nisso ONTEM: medi 29 turnos com 5 batidas e anunciei 17% de
   cobertura como anomalia — o número era artefato de contar turnos que não tinham começado.
   `AGUARDANDO` nunca vira aviso.

3. **Não trata cadastro como falta.** `AUSENTE_PROLONGADO` (o Euler, 14 dias sem bater e ainda
   escalado) é afastamento/férias/desligamento não lançado — problema de cadastro, do DP, não
   da pessoa. Avisa uma vez por SEMANA, não por dia: repetir diariamente por 14 dias é ruído
   sobre um fato que já foi contado, e a pessoa não tem o que resolver.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Veredictos que merecem interromper o dia do dono. COBERTO e AGUARDANDO ficam FORA: o
# primeiro é o normal, o segundo é o futuro.
_URGENTE = {
    "ESCALADO_SEM_VINCULO": ("🔴", "posto acha que está coberto por quem está DEMITIDO/INATIVO"),
    "SEM_BATIDA": ("🔴", "turno começou e ninguém bateu"),
    "ATRASO": ("🟡", "atraso"),
    "HORARIO_SUSPEITO": ("🟡", "bateu fora do horário do turno"),
    "BURACO_DE_ESCALA": ("🔴", "ninguém escalado para assumir"),
    # cadastro: cor diferente de propósito — não é a pessoa que resolve, é o DP
    "AUSENTE_PROLONGADO": ("🟠", "dias sem bater e ainda escalado — CADASTRO, não falta"),
}

# Cadastro, não falta: conta uma vez por semana. Repetir todo dia por 14 dias é ruído sobre
# fato já contado — e quem lê para de ler.
_CADASTRO = {"AUSENTE_PROLONGADO", "ESCALADO_SEM_VINCULO"}

# `SEM_BATIDA_JUSTIFICADA` NÃO entra: já está com o DP. Cobrar de novo é o agente brigando com
# o próprio fluxo — o `leia_assim` de `situacao_do_turno` diz isso em voz alta.

# ⭐ CARÊNCIA ANTES DE INCOMODAR O DONO — e ela não é timidez, é divisão de trabalho.
#
# O José Luís JÁ cobra a pessoa sozinho: lembrete 1h antes, aviso na hora do turno, escalada em
# +10 e +25 minutos. Esse circuito resolve a maioria — ontem o Antonio Walcicley e o Francisco
# Ramon bateram depois do +10 e a escalada parou certo.
#
# Se o vigia gritasse no Gestão a partir do minuto 1, ele avisaria o Jordan de gente que está
# ENTRANDO pelo portão, e o pedido dele ("saber assim que houver um problema") viraria o oposto
# do que quer: um grupo que apita 9 vezes às 08:05 é um grupo que ele para de ler. Então o vigia
# só fala DEPOIS que a cobrança automática teve as duas chances dela.
#
# Estrutural não espera: posto coberto por quem está demitido, ou troca sem ninguém escalado,
# não se resolve com lembrete — precisa de decisão humana, e quanto antes melhor.
_CARENCIA_MIN = {"SEM_BATIDA": 30, "ATRASO": 30, "HORARIO_SUSPEITO": 30,
                 "ESCALADO_SEM_VINCULO": 0, "BURACO_DE_ESCALA": 0, "AUSENTE_PROLONGADO": 0}


def _passou_a_carencia(a: dict[str, Any], agora_hhmm: str) -> bool:
    """O turno já começou há tempo suficiente para o problema ser do Jordan, não do agente?"""
    carencia = _CARENCIA_MIN.get(a["status"], 30)
    if carencia == 0:
        return True
    inicio = (a.get("_hora_turno") or "")[:5]
    if not inicio:
        return True
    def _min(h):
        try:
            hh, mm = h.split(":")[:2]
            return int(hh) * 60 + int(mm)
        except (ValueError, IndexError):
            return None
    i, n = _min(inicio), _min(agora_hhmm)
    if i is None or n is None:
        return True
    # ⚠️ turno da noite atravessa a meia-noite: 19:00 visto às 01:00 dá -1080 minutos, e sem
    # ajuste um turno noturno em curso pareceria futuro e nunca seria avisado.
    #
    # 🔴 MAS `n < i` NÃO É SUFICIENTE, e meu primeiro ajuste abriu um buraco no lugar de fechar:
    # um turno das 09:00 visto às 08:14 também satisfaz `n < i`, e virou "atrasado 23h e 46min".
    # A Celiane foi acusada assim. FUTURO e NOTURNO-EM-CURSO se distinguem pelo TAMANHO do vão:
    # ninguém está 13 horas atrasado — isso é turno que ainda não começou.
    if n < i:
        if (i - n) <= 12 * 60:
            return False  # ainda não começou: é futuro, não atraso
        n += 24 * 60
    return (n - i) >= carencia


async def _destino_gestao(db: AsyncSession) -> int | None:
    """A conversa do grupo que recebe relatório. Nunca telefone: JID de grupo morre no
    `_clean_phone` do `whatsapp_service`."""
    return (await db.execute(text(
        "SELECT chatwoot_conversation_id FROM wa_grupos "
        " WHERE recebe_relatorio AND chatwoot_conversation_id IS NOT NULL LIMIT 1"))).scalar()


async def buracos_de_escala(db: AsyncSession, *,
                            _agora: str | None = None) -> list[dict[str, Any]]:
    """Postos onde alguém SAI nas próximas 2h e ninguém ENTRA na mesma hora.

    ⭐ O achado do Jordan que nenhum veredito por turno pegava (Green Hills, 26/09): a escala
    tinha o Mauricio 19–07 saindo e NADA às 07:00. Verificação por turno percorre linhas
    existentes; aqui a linha não existe, e o vazio passava como silêncio.

    ⚠️ Compara pelo POSTO, não pelo nome da pessoa: substituto legítimo entra com outro nome no
    mesmo posto e mesma hora, e isso é cobertura, não buraco.
    """
    # ⚠️ VOCABULÁRIO: `shifts.status` guarda INGLÊS ('scheduled' 1136 · 'cancelled' 16). Meu
    # primeiro filtro dizia `NOT IN ('cancelado','cancelada')` e portanto NUNCA excluiu nada —
    # turno cancelado entrava como gente saindo do posto, inventando buraco. Mantenho as três
    # grafias porque a casa já teve as duas convenções e uma delas pode voltar num backfill.
    rows = (await db.execute(text("""
        WITH agora AS (SELECT coalesce(CAST(CAST(:ag AS text) AS timestamp),
                                      now() - interval '4 hours') AS ts),  -- Manaus
        -- ⭐ SAÍDA É UM INSTANTE, NÃO UMA HORA — conserto de 26/09/2026.
        --
        -- 🔴 Minha primeira versão comparava `planned_end_time` (um TIME) contra a hora de
        -- agora, dentro de `shift_date = hoje`. Isso está errado por um DIA inteiro em todo
        -- turno noturno: a linha de 26/09 com 19:00–07:00 SAI às 07:00 de **27/09**, e quem
        -- de fato sai às 07:00 de 26/09 é a linha de **25/09**, que a consulta nunca olhava.
        --
        -- ⚠️ E o pior: ela ACERTOU o Green Hills pelo motivo errado. Havia mesmo um buraco às
        -- 07:00, mas eu o encontrei casando a linha do dia errado — o tipo de acerto que some
        -- na primeira mudança de dado. Mesma família do `data da batida ≠ data da escala`:
        -- um turno que atravessa a meia-noite pertence a um dia e termina no outro.
        janela AS (
            SELECT s.id, s.post_id, s.employee_id, s.planned_end_time AS hora,
                   (s.shift_date
                    + CASE WHEN s.planned_end_time <= s.planned_start_time
                           THEN INTERVAL '1 day' ELSE INTERVAL '0' END
                    + s.planned_end_time) AS sai_em
              FROM shifts s
             WHERE s.shift_date BETWEEN (SELECT ts::date FROM agora) - 1
                                    AND (SELECT ts::date FROM agora)
               AND s.status NOT IN ('cancelled', 'cancelado', 'cancelada')
               AND s.is_active),
        saindo AS (
            -- ⚠️ `shifts.post_id` é a coluna do turno, mas o posto de VERDADE é a alocação
            -- ativa: `post_id` congela o posto do dia em que a escala foi gerada e havia 87
            -- turnos futuros divergentes. A alocação é o que o Jordan cura à mão.
            SELECT coalesce(pa.name, pp.name) AS posto, j.hora, e.nome AS quem
              FROM janela j
              JOIN employees e ON e.id = j.employee_id
              JOIN posts pp ON pp.id = j.post_id
              LEFT JOIN employee_alocacoes ea ON ea.employee_id = e.id AND ea.ativo
              LEFT JOIN posts pa ON pa.id = ea.posto_id
             -- janela À FRENTE: avisar antes da troca serve; depois dela já é autópsia
             WHERE j.sai_em BETWEEN (SELECT ts FROM agora)
                                AND (SELECT ts + interval '2 hours' FROM agora)
        )
        SELECT sa.posto, sa.hora, sa.quem
          FROM saindo sa
         WHERE NOT EXISTS (
             -- alguém ENTRA neste posto nesta hora? tolerância de 30min para troca escalonada.
             -- Compara pelo POSTO, não pela pessoa: substituto legítimo entra com outro nome.
             SELECT 1 FROM shifts s2
               JOIN posts pp2 ON pp2.id = s2.post_id
               LEFT JOIN employee_alocacoes ea2 ON ea2.employee_id = s2.employee_id AND ea2.ativo
               LEFT JOIN posts pa2 ON pa2.id = ea2.posto_id
              WHERE coalesce(pa2.name, pp2.name) = sa.posto
                AND s2.shift_date IN ((SELECT ts::date FROM agora),
                                      (SELECT ts::date FROM agora) + 1,
                                      (SELECT ts::date FROM agora) - 1)
                AND s2.status NOT IN ('cancelled', 'cancelado', 'cancelada')
                AND s2.is_active
                AND abs(EXTRACT(EPOCH FROM (s2.planned_start_time - sa.hora))) <= 1800)
         ORDER BY sa.hora, sa.posto"""), {"ag": _agora})).mappings().all()
    # ⚠️ `_agora` existe para PROVAR o ramo. Um buraco só aparece nas 2h antes da troca, e às
    # 08:05 o Green Hills das 07:00 já passou — sem poder mover o relógio eu entregaria um
    # caminho que nunca executou, que é promessa, não parede.
    return [{"posto": r["posto"], "hora": r["hora"].strftime("%H:%M"), "quem_sai": r["quem"],
             "status": "BURACO_DE_ESCALA", "_employee_id": None,
             "_hora_turno": r["hora"].strftime("%H:%M:%S")} for r in rows]


async def _novidades(db: AsyncSession, achados: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filtra o que JÁ foi avisado. É a diferença entre vigilância e ruído."""
    novos = []
    for a in achados:
        cad = a["status"] in _CADASTRO
        ja = (await db.execute(text(f"""
            SELECT 1 FROM wa_vigia_avisos
             WHERE veredito = :v AND hora_turno = CAST(CAST(:h AS text) AS time)
               AND employee_id IS NOT DISTINCT FROM CAST(:e AS uuid)
               AND posto IS NOT DISTINCT FROM :p
               AND dia >= current_date - {7 if cad else 0}
             LIMIT 1"""), {"v": a["status"], "h": a["_hora_turno"],
                           "e": a.get("_employee_id"), "p": a.get("posto")})).scalar()
        if not ja:
            novos.append(a)
    return novos


def _texto(novos: list[dict[str, Any]], hora: str) -> str:
    """Uma linha por problema, o pior primeiro. Sem preâmbulo: quem lê no celular quer o fato."""
    ordem = {"BURACO_DE_ESCALA": 0, "ESCALADO_SEM_VINCULO": 1, "SEM_BATIDA": 2,
             "HORARIO_SUSPEITO": 3, "ATRASO": 4}
    linhas = []
    for a in sorted(novos, key=lambda x: (ordem.get(x["status"], 9), x.get("posto") or "")):
        if a["status"] == "BURACO_DE_ESCALA":
            linhas.append(f"🔴 *{a['posto']}* — troca das {a['hora']}: {a['quem_sai']} sai e "
                          f"NINGUÉM está escalado para assumir")
            continue
        quem = a.get("quem") or "(sem nome)"
        emoji, frase = _URGENTE.get(a["status"], ("⚪", a["status"]))
        det = f" ({a['atraso_min']}min)" if a.get("atraso_min") else ""
        linha = f"{emoji} *{a.get('posto')}* — {quem}, {a.get('previsto', '?')}: {frase}{det}"
        if a.get("por_que"):
            linha += f"\n    ↳ {a['por_que']}"
        linhas.append(linha)
    return (f"*Vigia dos postos* — {hora} (Manaus)\n\n" + "\n".join(linhas) +
            "\n\n_só o que MUDOU desde o último aviso; verde não gera mensagem_")


async def varrer(db: AsyncSession, *, publicar: bool = True) -> dict[str, Any]:
    """Olha TODOS os postos agora, avisa o Gestão só do que é novo, e registra o que avisou.

    Silêncio é resultado bom: `{"novos": 0}` significa que nada piorou desde a última varredura.

    ⚠️ `publicar=False` é dry run PURO: não grava em `wa_vigia_avisos`. Minha primeira versão
    gravava, e isso QUEIMAVA a novidade — o problema ficava marcado como avisado sem ninguém ter
    sido avisado, e nunca mais sairia. Registro só existe se a mensagem SAIU.
    """
    from modules.integrations.connectors.whatsapp import supervisao as _sup

    sit = await _sup.situacao_do_turno(db, com_nomes=True, com_ids=True)
    achados: list[dict[str, Any]] = []
    for posto, itens in (sit.get("postos") or {}).items():
        for it in itens:
            if it["status"] in _URGENTE or it["status"] in _CADASTRO:
                achados.append({**it, "posto": posto})
    achados += await buracos_de_escala(db)
    agora = sit["hora_de_referencia_manaus"]
    achados = [a for a in achados if _passou_a_carencia(a, agora)]

    novos = await _novidades(db, achados)
    if not novos:
        return {"ok": True, "hora": sit["hora_de_referencia_manaus"],
                "problemas_abertos": len(achados), "novos": 0, "publicado": False}

    publicado = False
    if publicar:
        destino = await _destino_gestao(db)
        if destino:
            publicado = bool(await _sup._publicar_no_grupo(
                int(destino), _texto(novos, sit["hora_de_referencia_manaus"])))
        else:
            logger.warning("vigia: sem grupo de relatório — %d problemas novos NÃO publicados",
                           len(novos))

    # ⚠️ Registra SÓ depois de publicar de verdade. Marcar antes seria perder o aviso para
    # sempre se o envio falhasse — foi exatamente o defeito do `_mandar` que me deixou 4
    # pessoas em `aguardando` sem nenhuma mensagem enviada.
    if publicado:
        for a in novos:
            await db.execute(text("""
                INSERT INTO wa_vigia_avisos (dia, employee_id, posto, hora_turno, veredito)
                VALUES (current_date, CAST(:e AS uuid), :p, CAST(CAST(:h AS text) AS time), :v)
                ON CONFLICT DO NOTHING"""),
                {"e": a.get("_employee_id"), "p": a.get("posto"),
                 "h": a["_hora_turno"], "v": a["status"]})
        await db.commit()

    return {"ok": True, "hora": sit["hora_de_referencia_manaus"],
            "problemas_abertos": len(achados), "novos": len(novos), "publicado": publicado,
            "tipos": sorted({a["status"] for a in novos})}
