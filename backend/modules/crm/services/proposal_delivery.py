"""
Entrega de proposta — e-mail com rastreio (pixel) + assinatura interna.

- send_proposal_email: envia a proposta por e-mail (core/mailer) com link de assinatura + pixel de
  rastreio (marca viewed_at quando o cliente abre).
- Assinatura INTERNA (sem provedor externo): o cliente abre o link público, confere e assina; grava
  em proposal_signatures + marca signed_at/status. Best-effort no envio (nunca quebra o fluxo).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.mailer import send_email

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://erp.conectamais.pro").rstrip("/")

# Pixel GIF 1x1 transparente.
PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00"
    b"\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def track_pixel_url(pid: str) -> str:
    return f"{_BASE_URL}/api/v1/crm/proposals/{pid}/track.gif"


def sign_url(pid: str) -> str:
    return f"{_BASE_URL}/assinar/{pid}"


def _brl(v: float) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


async def send_proposal_email(proposal) -> bool:
    """Envia a proposta por e-mail com link de assinatura + pixel de rastreio. Best-effort."""
    try:
        email = getattr(proposal, "client_email", None)
        if not email:
            logger.info("Proposta %s sem e-mail do cliente -> e-mail não enviado", getattr(proposal, "number", "?"))
            return False
        num = getattr(proposal, "number", "")
        cliente = getattr(proposal, "client_name", None) or "Cliente"
        total = _brl(getattr(proposal, "total", 0))
        link = sign_url(str(proposal.id))
        pixel = track_pixel_url(str(proposal.id))
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#222">
          <div style="border-top:4px solid #1e40af;padding:16px 0">
            <h2 style="color:#1e40af;margin:0">Conecta Mais — Segurança e Tecnologia</h2>
          </div>
          <p>Olá, {cliente},</p>
          <p>Segue a proposta <b>{num}</b> no valor de <b>{total}</b>.</p>
          <p>Clique abaixo para visualizar e <b>assinar digitalmente</b>:</p>
          <p style="text-align:center;margin:24px 0">
            <a href="{link}" style="background:#1e40af;color:#fff;text-decoration:none;
               padding:12px 28px;border-radius:8px;font-weight:bold;display:inline-block">
               Ver e assinar a proposta</a>
          </p>
          <p style="color:#888;font-size:12px">Conecta Mais · 0800 880 4414 · www.conectamaistech.com.br</p>
          <img src="{pixel}" width="1" height="1" alt="" style="display:none">
        </div>
        """
        ok = await send_email(email, f"Proposta {num} — Conecta Mais", html)
        logger.info("Proposta %s e-mail %s para %s", num, "ENVIADO" if ok else "FALHOU", email)
        return ok
    except Exception as exc:  # noqa: BLE001 — e-mail nunca quebra o fluxo
        logger.warning("send_proposal_email falhou (%s): %s", getattr(proposal, "number", "?"), exc)
        return False


async def mark_proposal_viewed(db: AsyncSession, proposal_id: str) -> None:
    """Marca viewed_at (e status sent->viewed) quando o pixel é aberto. Best-effort."""
    try:
        await db.execute(
            text("""
            UPDATE proposals SET viewed_at = COALESCE(viewed_at, now()),
                   status = CASE WHEN status = 'sent' THEN 'viewed' ELSE status END
            WHERE id = :id
            """),
            {"id": proposal_id},
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("mark_proposal_viewed ignorado: %s", exc)


async def register_signature(
    db: AsyncSession, proposal, signer_name: str, signer_cpf: str | None, ip: str | None, user_agent: str | None
) -> str | None:
    """Registra a assinatura INTERNA: grava em proposal_signatures + marca a proposta como assinada.
    Retorna o hash da assinatura. Best-effort no que é acessório, mas a gravação é a parte principal."""
    try:
        pid = str(proposal.id)
        now = datetime.utcnow()
        raw = f"{pid}|{signer_name}|{signer_cpf or ''}|{now.isoformat()}|{ip or ''}"
        sig_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        signer_email = (getattr(proposal, "client_email", None) or f"assinante-{pid[:8]}@conectamais.pro")[:255]
        await db.execute(
            text("""
            INSERT INTO proposal_signatures
                (id, proposal_id, provider, status, signer_name, signer_email, signer_cpf, signed_at,
                 signature_hash, ip_address, user_agent, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :pid, 'interno', 'signed', :name, :email, :cpf, :signed,
                 :hash, :ip, :ua, now(), now())
            """),
            {
                "pid": pid,
                "name": signer_name[:255],
                "email": signer_email,
                "cpf": (signer_cpf or None),
                "signed": now,
                "hash": sig_hash,
                "ip": (ip or None),
                "ua": (user_agent or None),
            },
        )
        await db.execute(
            text("""
            UPDATE proposals
            SET signature_status = 'signed', signed_at = :signed, signature_provider = 'interno',
                status = 'accepted', responded_at = now()
            WHERE id = :pid
            """),
            {"signed": now, "pid": pid},
        )
        await db.commit()
        logger.info(
            "Assinatura interna registrada p/ proposta %s por %s (hash %s)",
            getattr(proposal, "number", "?"),
            signer_name,
            sig_hash[:12],
        )
        return sig_hash
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_signature falhou (%s): %s", getattr(proposal, "number", "?"), exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
