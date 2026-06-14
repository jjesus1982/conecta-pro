"""
Tasks Celery do agente José Luís (WhatsApp).

whatsapp.followup_conversas — encontra conversas que ESFRIARAM (cliente sumiu
apos a ultima resposta) e envia ao Jordan, via Telegram, a lista com um rascunho
de retomada por conversa. NADA e enviado ao cliente automaticamente — o aval e
humano (Jordan/equipe decide e manda).
"""

import logging
import os

from celery_app import app

logger = logging.getLogger(__name__)

# Janela de "esfriou": cliente sem responder ha mais de 24h e menos de 7 dias.
FOLLOWUP_MIN_HORAS = 24
FOLLOWUP_MAX_DIAS = 7


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery (engine propria)."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _telegram_send(text_msg: str) -> bool:
    """Entrega a lista ao Jordan via Telegram (credenciais do env). Best-effort."""
    token = os.getenv("MONITOR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("followup_conversas: TELEGRAM ausente — lista NAO enviada (so log)")
        return False
    try:
        import requests  # noqa: PLC0415

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text_msg[:4000], "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.error("followup_conversas: telegram falhou: %s", e)
        return False


async def _coletar_conversas_frias(session):
    """Conversas cuja ULTIMA mensagem e 'out' (respondida) e o cliente sumiu 24h-7d."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                """
                WITH ultima AS (
                    SELECT DISTINCT ON (chatwoot_conversation_id)
                        chatwoot_conversation_id AS conv,
                        direction, content, created_at, phone_canonical, lead_id
                    FROM cwi_message_log
                    WHERE direction IN ('in','out') AND chatwoot_conversation_id IS NOT NULL
                    ORDER BY chatwoot_conversation_id, created_at DESC
                )
                SELECT u.conv, u.phone_canonical, u.created_at,
                       coalesce(l.name, 'Contato ' || coalesce(u.phone_canonical,'?')) AS nome,
                       coalesce(l.company, '')                                        AS empresa,
                       coalesce(l.status, '')                                         AS lead_status,
                       (SELECT i.content FROM cwi_message_log i
                         WHERE i.chatwoot_conversation_id = u.conv AND i.direction='in'
                           AND i.content IS NOT NULL AND i.content <> ''
                         ORDER BY i.created_at DESC LIMIT 1)                          AS ultimo_assunto
                FROM ultima u
                LEFT JOIN leads l ON l.id = (
                    SELECT m.lead_id FROM cwi_message_log m
                    WHERE m.chatwoot_conversation_id = u.conv AND m.lead_id IS NOT NULL
                    ORDER BY m.created_at DESC LIMIT 1
                )
                WHERE u.direction = 'out'
                  AND u.created_at < now() - interval '24 hours'
                  AND u.created_at > now() - interval '7 days'
                  AND coalesce(l.status,'') NOT IN ('converted','disqualified')
                ORDER BY u.created_at ASC
                LIMIT 15
                """
            )
        )
    ).fetchall()
    return rows


@app.task(name="whatsapp.followup_conversas", bind=True, max_retries=1)
def followup_conversas(self):  # noqa: ARG001
    """Diario: lista conversas frias + rascunho de retomada -> Telegram do Jordan."""
    try:
        rows = _run_async(_coletar_conversas_frias)
    except Exception as e:  # noqa: BLE001
        logger.error("followup_conversas: coleta falhou: %s", e)
        return {"ok": False}

    if not rows:
        _telegram_send("🤖 <b>José Luís — follow-up diário</b>\n\nNenhuma conversa esfriada nas últimas 24h–7d. 👌")
        return {"ok": True, "frias": 0}

    linhas = ["🤖 <b>José Luís — conversas que esfriaram</b> (aguardando SEU aval; nada foi enviado)\n"]
    for conv, phone, quando, nome, empresa, _status, assunto in rows:
        dias = max(1, (__import__("datetime").datetime.now(quando.tzinfo) - quando).days)
        quem = f"{nome}" + (f" ({empresa})" if empresa else "")
        tema = (assunto or "—").replace("\n", " ")[:90]
        rascunho = (
            f"Olá{', ' + nome.split()[0] if nome and not nome.startswith('Contato') else ''}! "
            f"Aqui é o José Luís, da Conecta Mais 😊 Ficou alguma dúvida sobre o que conversamos? "
            f"Sigo à disposição para ajudar."
        )
        linhas.append(
            f"• <b>{quem}</b> — conv #{conv}, parado há {dias}d\n"
            f"  Último assunto: {tema}\n"
            f"  📋 Sugestão p/ retomar: <i>{rascunho}</i>\n"
        )
    linhas.append("\nPara retomar: responda na conversa do Chatwoot (a sugestão acima é só um rascunho).")
    _telegram_send("\n".join(linhas))
    logger.info("followup_conversas: %s conversas frias notificadas", len(rows))
    return {"ok": True, "frias": len(rows)}
