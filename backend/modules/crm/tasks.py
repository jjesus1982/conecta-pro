"""Celery Tasks — CRM: follow-up de propostas.

FUNDAÇÃO 1: SELECIONA propostas vencidas para follow-up (cadência 2d/7d),
gera a lista e entrega ao Jordan via Telegram + log. NÃO contata o cliente.

⚠️  GATE LGPD — FOLLOWUP_AUTO_SEND = False:
    Com False, a rotina só GERA a lista e registra o follow-up como 'skipped'
    (a cadência AVANÇA, mas NADA é enviado ao cliente). Para LIGAR o disparo ao
    cliente (WhatsApp/e-mail) é necessário, NESTA ordem:
      1) revisão/aprovação LGPD do conteúdo e da base legal do contato;
      2) mudar FOLLOWUP_AUTO_SEND = True AQUI (constante no código, não no .env);
      3) rebuild da imagem do backend.

Semântica da cadência: ao listar uma proposta vencida, inserimos um registro em
proposal_followups (status='skipped' quando desligado). Como a próxima janela de
7 dias conta a partir desse registro, o MESMO lead NÃO reaparece na lista todo
dia — ele volta em +7 dias. Isso evita spam de lista e mantém a trilha (LGPD).
"""

import logging
import os

from celery_app import app

logger = logging.getLogger(__name__)

# === GATE LGPD — NÃO ligar sem revisão (ver docstring) ===
FOLLOWUP_AUTO_SEND = False

# Cadência
FOLLOWUP_FIRST_DAYS = 2  # 1º follow-up: 2 dias após sent_at
FOLLOWUP_NEXT_DAYS = 7  # seguintes: a cada 7 dias enquanto sem resposta


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery (engine própria)."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


def _telegram_send(text_msg: str) -> bool:
    """Entrega a lista ao Jordan via Telegram Bot API (credenciais do env). Best-effort."""
    token = os.getenv("MONITOR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("followup: TELEGRAM token/chat ausente — lista NAO enviada (so log)")
        return False
    try:
        import requests  # noqa: PLC0415

        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text_msg, "parse_mode": "HTML"},
            timeout=15,
        )
        ok = r.status_code == 200 and r.json().get("ok")
        if not ok:
            logger.error("followup: Telegram falhou %s: %s", r.status_code, r.text[:200])
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        logger.warning("followup: excecao no Telegram (best-effort): %s", e)
        return False


async def _enviar_followup_cliente(v: dict) -> tuple[str, str, str]:
    """BLOCO PRONTO — só roda com FOLLOWUP_AUTO_SEND=True. Retorna (channel, status, detail).

    NÃO é executado nesta fundação (gate LGPD). Mantido implementado p/ quando ligar.
    """
    from core.mailer import send_email  # noqa: PLC0415
    from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

    canais: list[str] = []
    msg_cli = (
        f"Olá! Sobre a proposta {v['number']} que enviamos, seguimos à disposição "
        f"para esclarecer dúvidas. Podemos avançar?"
    )
    try:
        if v.get("phone"):
            await whatsapp_service.send_custom(v["phone"], msg_cli)
            canais.append("whatsapp")
        if v.get("email"):
            await send_email(v["email"], f"Follow-up da proposta {v['number']}", f"<p>{msg_cli}</p>")
            canais.append("email")
        channel = "both" if len(canais) == 2 else (canais[0] if canais else "none")
        return channel, "sent", "enviado ao cliente"
    except Exception as e:  # noqa: BLE001
        return "none", "failed", str(e)[:200]


async def _followup_async(session):
    from datetime import datetime  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    agora = datetime.utcnow()

    # 1) candidatas: enviadas e sem resposta
    rows = (
        await session.execute(
            text(
                "SELECT id, number, client_name, client_email, client_phone, total, sent_at "
                "FROM proposals WHERE status='sent' AND responded_at IS NULL AND sent_at IS NOT NULL"
            )
        )
    ).fetchall()

    vencidos: list[dict] = []
    for p in rows:
        pid, number, cname, cemail, cphone, total, sent_at = p
        # último follow-up já processado dessa proposta
        last = (
            await session.execute(
                text(
                    "SELECT sequence, COALESCE(sent_at, scheduled_for, created_at) AS quando "
                    "FROM proposal_followups WHERE proposal_id = :pid "
                    "ORDER BY sequence DESC LIMIT 1"
                ),
                {"pid": str(pid)},
            )
        ).first()

        if last is None:
            # nenhum follow-up ainda -> vence 2 dias após sent_at
            due = (agora - sent_at).total_seconds() >= FOLLOWUP_FIRST_DAYS * 86400
            next_seq = 1
        else:
            last_seq, quando = last
            due = (agora - quando).total_seconds() >= FOLLOWUP_NEXT_DAYS * 86400
            next_seq = last_seq + 1

        if not due:
            continue

        dias = int((agora - sent_at).total_seconds() // 86400)
        vencidos.append(
            {
                "id": str(pid),
                "number": number,
                "client_name": cname,
                "email": cemail,
                "phone": cphone,
                "total": float(total or 0),
                "dias": dias,
                "next_seq": next_seq,
            }
        )

    # 2) registra o follow-up (avança a cadência) + (se ligado) dispara ao cliente
    for v in vencidos:
        if FOLLOWUP_AUTO_SEND:
            # BLOCO PRONTO — NÃO executado nesta fundação (gate LGPD)
            channel, status_fu, detail = await _enviar_followup_cliente(v)
            await session.execute(
                text(
                    "INSERT INTO proposal_followups "
                    "(proposal_id, sequence, channel, status, scheduled_for, sent_at, detail) "
                    "VALUES (:pid, :seq, :ch, :st, :now, :now, :dt)"
                ),
                {"pid": v["id"], "seq": v["next_seq"], "ch": channel, "st": status_fu, "now": agora, "dt": detail},
            )
        else:
            await session.execute(
                text(
                    "INSERT INTO proposal_followups "
                    "(proposal_id, sequence, channel, status, scheduled_for, detail) "
                    "VALUES (:pid, :seq, 'none', 'skipped', :now, :dt)"
                ),
                {
                    "pid": v["id"],
                    "seq": v["next_seq"],
                    "now": agora,
                    "dt": "lista gerada, disparo desligado (gate LGPD)",
                },
            )
    await session.commit()

    # 3) monta e entrega a lista (Telegram + log)
    if vencidos:
        linhas = [
            f"• <b>{v['number']}</b> — {v['client_name']} — R$ {v['total']:.2f} "
            f"({v['dias']}d sem resposta, follow-up #{v['next_seq']})"
            for v in vencidos
        ]
        msg = (
            f"📋 <b>Follow-up de propostas</b> — {len(vencidos)} vencida(s)\n"
            f"(disparo ao cliente DESLIGADO — gate LGPD; lista para ação manual)\n\n" + "\n".join(linhas)
        )
    else:
        msg = "📋 Follow-up de propostas: nenhuma proposta vencida para follow-up hoje."

    entregue = _telegram_send(msg)
    logger.info("followup: vencidos=%s telegram=%s auto_send=%s", len(vencidos), entregue, FOLLOWUP_AUTO_SEND)
    return {"vencidos": len(vencidos), "telegram_ok": entregue, "auto_send": FOLLOWUP_AUTO_SEND}


@app.task(name="crm.followup_proposals", bind=True, max_retries=1)
def followup_proposals(self):
    """Rotina diária: gera lista de propostas vencidas p/ follow-up.

    NÃO contata o cliente (FOLLOWUP_AUTO_SEND=False / gate LGPD). Só seleciona,
    registra a cadência em proposal_followups e entrega a lista ao Jordan.
    """
    try:
        return _run_async(_followup_async)
    except Exception as e:  # noqa: BLE001
        logger.error("crm.followup_proposals falhou: %s", e)
        raise
