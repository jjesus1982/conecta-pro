"""O que o funcionário relata vira TAREFA de alguém — não morre anotado (11/09/2026).

Jordan: *"ele coleta e não fecha. Registrou que o Nailson tem duplicata — mas não pode pedir a
correção do espelho. Registrou o afastamento da Cintia — mas não abre o chamado. Falta a ponte
entre 'eu anotei' e 'isso virou tarefa de alguém'."*

A ponte não é uma tabela nova: é o mecanismo de RASCUNHO que a casa já usa para tudo que espera
um humano (`orquestrador/acoes/rascunho.criar_rascunho`). Ele grava em `agent_drafts`, notifica
pelo papel do aprovador e tem estado — é o mesmo lugar onde caem as ações que o gate barra. Uma
pendência de ponto criada aqui aparece na mesma Central onde o Jordan já decide.

⚠️ NUNCA EXECUTA NADA. O agente não corrige espelho, não valida batida, não fecha afastamento:
ele descreve o caso com as palavras da pessoa e entrega a quem decide. Ponto é registro de fato
e a correção é ato do DP — o que muda é que agora o DP RECEBE, em vez de depender de alguém
lembrar de contar.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Quem decide sobre ponto nesta casa. 'admin' sempre presente ⇒ pendência não fica órfã.
ROLES_DP = ("admin", "gerente_operacional")

#: O que o agente pode abrir. Lista fechada de propósito: assunto novo entra aqui com nome, e
#: não por texto livre do modelo — senão a Central vira caixa de entrada sem dono.
ASSUNTOS = {
    "corrigir_espelho": "corrigir o espelho de ponto (batida duplicada, faltando ou trocada)",
    "validar_batida": "validar batida de contingência que ficou pendente",
    "problema_no_app": "o app do ponto não funciona para esta pessoa",
    "afastamento": "afastamento, atestado ou benefício do INSS",
    "ferias_ou_folga": "férias, folga ou troca de escala",
    "holerite_ou_pagamento": "dúvida ou divergência de holerite, VT, VR ou desconto",
    "outro": "outro assunto de DP relatado pelo funcionário",
}


async def abrir(db, *, employee_id: str, nome: str, assunto: str, relato: str,
                posto: str | None = None) -> dict:
    """Abre a pendência para o DP. Devolve o que o agente deve dizer à pessoa."""
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    assunto = assunto if assunto in ASSUNTOS else "outro"
    relato = (relato or "").strip()
    if len(relato) < 10:
        return {"ok": False, "msg": "me conta com um pouco mais de detalhe o que aconteceu, "
                                    "senão o DP não consegue resolver sem te perguntar de novo"}

    # ⚠️ `agent_drafts.solicitado_por` é UUID: um "jose-luis" literal estoura na gravação (e
    # estourou, na primeira prova). QUEM PEDE é a própria pessoa — ela relatou, o agente só
    # levou —, então usamos a conta DELA quando existe. Sem conta, cai na conta de serviço,
    # que é o que a casa já usa para ação de sistema.
    from sqlalchemy import text as _sql  # noqa: PLC0415

    uid = (await db.execute(_sql(
        "SELECT id::text FROM users WHERE employee_id = CAST(:e AS uuid) AND is_active "
        " ORDER BY last_login DESC NULLS LAST LIMIT 1"), {"e": str(employee_id)})).scalar()
    if not uid:
        uid = (await db.execute(_sql(
            "SELECT id::text FROM users WHERE lower(email) = 'mcp-service@conectamais.pro' LIMIT 1"))).scalar()
    if not uid:
        return {"ok": False, "msg": "não consegui registrar agora — vou pedir que alguém da "
                                    "equipe te procure"}

    class _Ator:
        id = uid
        email = "jose-luis@conectamais.pro"
        full_name = f"{nome} (relatado ao José Luís no WhatsApp)"
        employee_id = None
        role = "funcionario"

    titulo = f"{nome}: {ASSUNTOS[assunto]}"
    resumo = (
        f"{nome}" + (f" — {posto}" if posto else "") + "\n\n"
        f"Assunto: {ASSUNTOS[assunto]}\n\n"
        f"O que a pessoa relatou, com as palavras dela:\n\"{relato[:1200]}\"\n\n"
        "Relatado pelo WhatsApp ao José Luís. Ele NÃO corrigiu nada — ponto é registro de fato "
        "e a correção é ato do DP."
    )
    try:
        r = await criar_rascunho(
            db, _Ator(), tipo="pendencia_ponto", modulo="ponto", titulo=titulo[:180],
            resumo=resumo, payload={"employee_id": str(employee_id), "nome": nome,
                                    "assunto": assunto, "relato": relato[:2000], "posto": posto},
            gate="🔵", requires_otp=False, roles_aprovador=ROLES_DP,
            # uma pendência por pessoa/assunto por dia: quem repete a queixa não gera fila
            idempotency_key=f"pendencia_ponto:{employee_id}:{assunto}:{_hoje()}",
        )
    except Exception as e:  # noqa: BLE001 — falhar em abrir não pode calar o atendimento
        logger.warning("pendência de ponto para %s falhou: %s", nome, e)
        return {"ok": False, "msg": "não consegui registrar agora — vou pedir que alguém da "
                                    "equipe te procure"}
    if isinstance(r, dict) and r.get("erro"):
        return {"ok": False, "msg": str(r["erro"])[:200]}
    logger.info("pendência de ponto aberta: %s / %s", nome, assunto)
    return {"ok": True, "assunto": ASSUNTOS[assunto], "rascunho": (r or {}).get("draft_id"),
            "msg": "Registrei aqui e já está na fila do DP. Eles é que corrigem — assim que "
                   "resolverem, eu te aviso."}


def _hoje() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
