"""
WhatsApp Controller — Endpoints REST para envio de mensagens.
"""

import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, CurrentUserId
from core.database import get_db
from modules.integrations.connectors.whatsapp import agent_service
from modules.integrations.connectors.whatsapp.service import (
    _read_secret_file,
    whatsapp_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp - Evolution API"])


# === Schemas ===


class WhatsAppStatusResponse(BaseModel):
    online: bool
    instance: str
    enabled: bool
    details: dict = {}


class SendKitNotificationRequest(BaseModel):
    phone: str = Field(..., description="Telefone com DDD")
    client_name: str
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2024, le=2030)
    documents_count: int = Field(ge=0, default=0)
    portal_url: str | None = None


class SendCertAlertRequest(BaseModel):
    phone: str
    client_name: str
    certificate_type: str
    expiry_date: str
    days_remaining: int


class SendNfseRequest(BaseModel):
    phone: str
    client_name: str
    nfse_number: str
    value: float
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2024, le=2030)


class SendCustomRequest(BaseModel):
    phone: str
    message: str = Field(..., min_length=1, max_length=4096)


class SendResponse(BaseModel):
    success: bool
    status: str
    phone: str | None = None
    message: str | None = None
    data: dict = {}


# === Endpoints ===


@router.get("/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(current_user: CurrentActiveUser) -> WhatsAppStatusResponse:
    """Verifica status da conexao WhatsApp/Evolution API."""
    result = await whatsapp_service.check_status()
    return WhatsAppStatusResponse(
        online=result.get("online", False),
        instance=whatsapp_service.instance,
        enabled=whatsapp_service.enabled,
        details=result,
    )


@router.post("/send/kit-notification", response_model=SendResponse)
async def send_kit_notification(
    request: SendKitNotificationRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia notificacao de kit documental via WhatsApp."""
    result = await whatsapp_service.send_kit_notification(
        phone=request.phone,
        client_name=request.client_name,
        month=request.month,
        year=request.year,
        documents_count=request.documents_count,
        portal_url=request.portal_url,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/certificate-alert", response_model=SendResponse)
async def send_certificate_alert(
    request: SendCertAlertRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia alerta de certidao vencendo via WhatsApp."""
    result = await whatsapp_service.send_certificate_alert(
        phone=request.phone,
        client_name=request.client_name,
        certificate_type=request.certificate_type,
        expiry_date=request.expiry_date,
        days_remaining=request.days_remaining,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/nfse-notification", response_model=SendResponse)
async def send_nfse_notification(
    request: SendNfseRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia notificacao de NFS-e emitida via WhatsApp."""
    result = await whatsapp_service.send_nfse_notification(
        phone=request.phone,
        client_name=request.client_name,
        nfse_number=request.nfse_number,
        value=request.value,
        month=request.month,
        year=request.year,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


@router.post("/send/custom", response_model=SendResponse)
async def send_custom_message(
    request: SendCustomRequest,
    user_id: CurrentUserId,
    current_user: CurrentActiveUser,
) -> SendResponse:
    """Envia mensagem customizada via WhatsApp."""
    result = await whatsapp_service.send_custom(
        phone=request.phone,
        message=request.message,
    )
    return SendResponse(
        success=result.get("status") == "sent",
        status=result.get("status", "unknown"),
        phone=result.get("phone"),
        data=result,
    )


# === Webhook de ENTRADA (Chatwoot -> backend) — Fase 2 ===


def _normalize_phone(phone: str | None) -> str | None:
    """Normaliza para os digitos DDD+numero (remove '+' e DDI 55)."""
    if not phone:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits or None


async def _match_or_create_lead(db: AsyncSession, phone_canonical: str, name: str | None) -> str | None:
    """Dedup por telefone normalizado em leads.phone; cria Lead (source=whatsapp) se novo."""
    row = (
        await db.execute(
            text(
                "SELECT id FROM leads "
                "WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = :p "
                "AND is_active = true LIMIT 1"
            ),
            {"p": phone_canonical},
        )
    ).first()
    if row:
        return str(row[0])

    from modules.crm.models.lead import LeadSource
    from modules.crm.repositories.lead_repository import LeadRepository
    from modules.crm.schemas.lead import LeadCreate

    lead_name = (name or "").strip() or f"WhatsApp {phone_canonical}"
    repo = LeadRepository(db)
    lead = await repo.create(
        LeadCreate(
            name=lead_name[:255],
            email=None,
            phone=phone_canonical,
            source=LeadSource.WHATSAPP,
        )
    )
    return lead.id


def _read_webhook_secret() -> str:
    """Segredo esperado: env (futuro rebuild) ou arquivo (docker cp no container atual)."""
    return os.getenv("WHATSAPP_WEBHOOK_SECRET", "") or _read_secret_file("/app/.whatsapp_webhook_secret")


@router.post("/webhook")
async def chatwoot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recebe eventos do Chatwoot (sem JWT). Loga entrada+saida e cria Lead na entrada.

    Autenticacao por token na URL (`?token=<segredo>`), pois o Chatwoot nao assina
    os webhooks. Idempotente por chatwoot_message_id (UNIQUE em cwi_message_log).
    """
    body = await request.body()

    expected = _read_webhook_secret()
    if expected:
        token = request.query_params.get("token", "")
        if not hmac.compare_digest(token, expected):
            logger.warning("Webhook Chatwoot: token invalido")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")

    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload invalido")

    if data.get("event") != "message_created":
        return {"status": "ignored", "event": data.get("event")}

    # Ignora notas privadas (rascunho do agente, notas internas do atendente):
    # nao loga nem reprocessa — evita poluir o historico e gerar loop.
    if data.get("private"):
        return {"status": "ignored_private"}

    msg_id = data.get("id")
    content = data.get("content")
    mtype = str(data.get("message_type", ""))
    direction = "in" if mtype in ("incoming", "0") else "out"
    conv = data.get("conversation") or {}
    conv_id = conv.get("id") or data.get("conversation_id")
    sender = data.get("sender") or {}
    meta_sender = (conv.get("meta") or {}).get("sender") or {}
    phone = sender.get("phone_number") or meta_sender.get("phone_number")
    name = sender.get("name") or meta_sender.get("name")
    phone_canonical = _normalize_phone(phone)

    lead_id = None
    if direction == "in" and phone_canonical:
        try:
            lead_id = await _match_or_create_lead(db, phone_canonical, name)
        except Exception as e:  # noqa: BLE001 — log nunca deve falhar por causa do lead
            logger.error("Webhook Chatwoot: falha ao criar/achar lead: %s", e)

    await db.execute(
        text(
            "INSERT INTO cwi_message_log "
            "(direction, phone_canonical, chatwoot_conversation_id, chatwoot_message_id, content, lead_id, status) "
            "VALUES (:direction, :phone, :conv, :msg, :content, :lead, :status) "
            "ON CONFLICT (chatwoot_message_id) DO NOTHING"
        ),
        {
            "direction": direction,
            "phone": phone_canonical,
            "conv": conv_id,
            "msg": msg_id,
            "content": content,
            "lead": lead_id,
            "status": data.get("status"),
        },
    )
    await db.commit()

    # Fase A (COPILOTO): em mensagem de ENTRADA, agendar o agente em background
    # (nao bloqueia o 200). Gera sugestao -> nota privada no Chatwoot + rascunho
    # em cwi_message_log. NAO envia ao cliente. So roda se AGENT_ENABLED=true.
    if direction == "in" and conv_id and agent_service.agent_enabled():
        background_tasks.add_task(agent_service.processar_incoming, conv_id, phone_canonical)

    return {"status": "ok", "direction": direction, "lead_id": lead_id, "message_id": msg_id}
