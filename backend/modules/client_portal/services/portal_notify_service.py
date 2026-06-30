"""Portal do Cliente — motor de notificações proativas (José Luís).

Avisa o condomínio quando algo merece atenção (mudança de escala, falta, advertência,
kit pronto, certidão a vencer) por: caixa de avisos no portal + e-mail + (best-effort)
WhatsApp pelo José Luís. Respeita as preferências do cliente.
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.client_portal.models.notification import ClientPortalNotification

logger = logging.getLogger(__name__)

ASSINATURA = "\n\nAtenciosamente,\nJosé Luís — Conecta Mais Patrimonial"

# SEGURANÇA: envio externo (e-mail/WhatsApp) ao cliente fica DESLIGADO por padrão
# (decisão Jordan: entrega ao cliente é manual). A caixa de avisos NO PORTAL sempre
# funciona. Para ligar o envio proativo, setar PORTAL_NOTIFY_ENABLED=true no .env.
_ENVIO_EXTERNO_ATIVO = os.getenv("PORTAL_NOTIFY_ENABLED", "false").lower() == "true"


def _prefs(client_id: str) -> dict:
    prefs = {"email_notifications": True, "whatsapp_notifications": True}
    try:
        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        raw = r.get(f"portal:prefs:{client_id}")
        if raw:
            prefs.update(json.loads(raw))
    except Exception:
        pass
    return prefs


async def notificar(
    db: AsyncSession,
    client_id: str,
    tipo: str,
    titulo: str,
    mensagem: str,
    link: str | None = None,
    forcar_email: bool = False,
) -> dict:
    """Cria o aviso na caixa do portal + envia e-mail/WhatsApp conforme preferências."""
    prefs = _prefs(client_id)
    # dados de contato
    contato = (
        await db.execute(
            text("SELECT name, contact_email, contact_name FROM ged_clients WHERE id = :cid"),
            {"cid": client_id},
        )
    ).mappings().first()
    email = contato["contact_email"] if contato else None

    enviou_email = False
    if _ENVIO_EXTERNO_ATIVO and email and (prefs.get("email_notifications") or forcar_email):
        try:
            from core.mailer import send_email

            html = (
                f"<div style='font-family:sans-serif;max-width:560px'>"
                f"<h2 style='color:#4338ca'>{titulo}</h2>"
                f"<p style='color:#374151;white-space:pre-line'>{mensagem}</p>"
                + (f"<p><a href='{link}' style='background:#4338ca;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none'>Abrir no portal</a></p>" if link else "")
                + "<hr style='border:none;border-top:1px solid #e5e7eb'>"
                f"<p style='color:#6b7280;font-size:13px'>José Luís · Conecta Mais Patrimonial<br>Portal do Cliente</p></div>"
            )
            enviou_email = await send_email(email, f"[Conecta Mais] {titulo}", html)
        except Exception as exc:
            logger.warning("Falha ao enviar e-mail de notificação: %s", exc)

    enviou_wpp = False  # WhatsApp via José Luís — best-effort (infra Baileys/Chatwoot); hook futuro

    aviso = ClientPortalNotification(
        client_id=client_id, tipo=tipo, titulo=titulo, mensagem=mensagem, link=link,
        canal_email=enviou_email, canal_whatsapp=enviou_wpp,
    )
    db.add(aviso)
    await db.commit()
    await db.refresh(aviso)
    return {"id": aviso.id, "email": enviou_email, "whatsapp": enviou_wpp}


async def listar(db: AsyncSession, client_id: str, apenas_nao_lidas: bool = False) -> list[dict]:
    q = select(ClientPortalNotification).where(ClientPortalNotification.client_id == client_id)
    if apenas_nao_lidas:
        q = q.where(ClientPortalNotification.lida.is_(False))
    q = q.order_by(ClientPortalNotification.created_at.desc()).limit(50)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": n.id, "tipo": n.tipo, "titulo": n.titulo, "mensagem": n.mensagem,
            "link": n.link, "lida": n.lida,
            "criado_em": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


async def marcar_lida(db: AsyncSession, client_id: str, notif_id: str) -> bool:
    n = (
        await db.execute(
            select(ClientPortalNotification).where(
                ClientPortalNotification.id == notif_id,
                ClientPortalNotification.client_id == client_id,
            )
        )
    ).scalar_one_or_none()
    if not n:
        return False
    n.lida = True
    await db.commit()
    return True


async def nao_lidas(db: AsyncSession, client_id: str) -> int:
    from sqlalchemy import func as sfunc

    return (
        await db.execute(
            select(sfunc.count()).select_from(ClientPortalNotification).where(
                ClientPortalNotification.client_id == client_id,
                ClientPortalNotification.lida.is_(False),
            )
        )
    ).scalar() or 0
