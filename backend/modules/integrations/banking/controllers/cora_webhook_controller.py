"""Webhook Controller — receptor de notificações do Banco Cora (Patrimonial).

Multi-CNPJ E4. Referência: docs/CORA_API_REFERENCIA_COMPLETA §5.

Particularidade do Cora: a notificação chega como **POST de corpo VAZIO** —
toda a informação vem nos HEADERS (webhook-event-type, webhook-resource-id).
NÃO há assinatura/HMAC (§5) → o webhook é tratado só como GATILHO: ao receber,
o sistema RE-CONSULTA o recurso na API autenticada antes de conciliar
(princípio da casa: valor exibido == fato no banco). Como rede de segurança
contra evento perdido, o beat diário de extrato (08:10) continua rodando.

Registrar a URL no Cora (uma vez): POST /endpoints com {url, resource, trigger}.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request

router = APIRouter(prefix="/webhooks/cora", tags=["Webhooks — Cora"])
logger = logging.getLogger(__name__)


@router.post("")
@router.post("/")
async def receber_webhook_cora(
    request: Request,
    webhook_event_type: str | None = Header(None, alias="webhook-event-type"),
    webhook_resource_id: str | None = Header(None, alias="webhook-resource-id"),
    webhook_event_id: str | None = Header(None, alias="webhook-event-id"),
) -> dict:
    """Recebe a notificação do Cora (corpo vazio; dados nos headers) e concilia
    RE-CONSULTANDO o recurso na API. Sempre responde 200 (o Cora reenvia em 404)."""
    # fallback: alguns proxies rebaixam os headers p/ o corpo — tenta ambos
    if not webhook_event_type:
        try:
            body = await request.json()
            webhook_event_type = body.get("webhook-event-type") or body.get("event_type")
            webhook_resource_id = webhook_resource_id or body.get("webhook-resource-id")
        except Exception:  # noqa: BLE001
            pass

    logger.info("Webhook Cora: event=%s resource=%s id=%s",
                webhook_event_type, webhook_resource_id, webhook_event_id)

    if not webhook_event_type or not webhook_resource_id:
        return {"success": True, "ignored": "headers ausentes"}

    resource = webhook_event_type.split(".")[0]
    try:
        if resource == "invoice":
            await _conciliar_invoice(webhook_resource_id, webhook_event_type)
        elif resource == "payment":
            await _atualizar_pagamento(webhook_resource_id, webhook_event_type)
        # transfer/service_receipt: logados; conciliação via extrato/beat
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook Cora: falha ao processar %s (%s) — beat concilia depois",
                       webhook_resource_id, exc)

    return {"success": True}


async def _conciliar_invoice(invoice_id: str, event_type: str) -> None:
    """invoice.paid → marca o receivable como pago (RE-CONSULTA a invoice antes)."""
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.integrations.banking.adapters.cora import CoraAdapter

    cora = CoraAdapter()
    await cora.authenticate()
    inv = await cora.consultar_cobranca(invoice_id)
    status = (inv.get("status") or "").upper()
    total_pago = int(inv.get("total_paid") or 0) / 100
    async with async_session_factory() as db:
        await db.execute(
            text(
                "UPDATE receivable_accounts SET "
                "status = CASE WHEN :st = 'PAID' THEN 'pago' ELSE status END, "
                "updated_at = NOW() "
                "WHERE pix_txid = :code OR metadata->>'cora_invoice_id' = :iid"
            ),
            {"st": status, "code": inv.get("code") or "", "iid": invoice_id},
        )
        await db.commit()
    logger.info("Webhook Cora invoice %s: %s (pago R$%.2f) — conciliado", invoice_id, event_type, total_pago)


async def _atualizar_pagamento(payment_id: str, event_type: str) -> None:
    """payment.approved/completed/reproved → atualiza o status do pagamento no ERP."""
    from sqlalchemy import text

    from core.database import async_session_factory

    trigger = event_type.split(".", 1)[-1]
    mapa = {"approved": "aprovado", "completed": "confirmado",
            "reproved": "reprovado", "error": "erro", "created": "processando"}
    novo = mapa.get(trigger)
    if not novo:
        return
    async with async_session_factory() as db:
        await db.execute(
            text(
                "UPDATE bank_transactions SET status = :st, reconciliation_note = "
                "COALESCE(reconciliation_note,'') || ' | cora:' || :trig, updated_at = NOW() "
                "WHERE external_id = :pid"
            ),
            {"st": "efetivada" if novo == "confirmado" else "pendente", "trig": trigger, "pid": payment_id},
        )
        await db.commit()
    logger.info("Webhook Cora payment %s: %s", payment_id, event_type)
