"""
Meta Conversions API (CAPI) — Conecta Marketing AI

Envia o evento "Lead" para o conjunto de dados da Meta sempre que o Conecta PRO
capta um lead (ex.: José Luís no WhatsApp). É a forma SERVER-SIDE de rastrear —
mais confiável que o pixel de navegador e liga o anúncio direto ao CRM.

Dorme até o token estar configurado (env META_CAPI_TOKEN). Best-effort: nunca
quebra a criação do lead.

Configuração (env):
  META_CAPI_TOKEN          -> token da API de Conversões do dataset (SECRET; vazio = desligado)
  META_DATASET_ID          -> id do conjunto de dados (default: pixel "Captura de leads")
  META_GRAPH_VERSION       -> versão da Graph API (default v21.0)
  META_CAPI_ACTION_SOURCE  -> action_source (default system_generated)
  META_CAPI_TEST_EVENT_CODE-> código de teste do Events Manager (só para validar; vazio em produção)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time

import aiohttp

logger = logging.getLogger(__name__)

_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")
_DATASET_ID = os.getenv("META_DATASET_ID", "1646163319127517")  # "Captura de leads"
_ACTION_SOURCE = os.getenv("META_CAPI_ACTION_SOURCE", "system_generated")


def _token() -> str:
    # Lido a cada chamada para refletir mudança de env sem rebuild de código.
    return os.getenv("META_CAPI_TOKEN", "").strip()


def capi_ativa() -> bool:
    return bool(_token())


def _sha256(valor: str | None) -> str | None:
    if not valor:
        return None
    return hashlib.sha256(valor.strip().lower().encode("utf-8")).hexdigest()


async def send_lead_event(
    phone: str | None = None,
    email: str | None = None,
    lead_id: str | None = None,
    ad_referral: dict | None = None,
    value: float = 0.0,
    currency: str = "BRL",
) -> bool:
    """Envia um evento 'Lead' para a Meta (CAPI). Retorna True se aceito (200)."""
    token = _token()
    if not token:
        return False  # dorme até configurar o token

    # user_data com PII hasheada em SHA256 (exigência da Meta).
    user_data: dict = {}
    digits = re.sub(r"\D", "", phone or "")
    if digits:
        user_data["ph"] = [_sha256(digits)]
    if email:
        user_data["em"] = [_sha256(email)]
    # Click-to-WhatsApp click id (atribuição precisa ao anúncio), se houver.
    if isinstance(ad_referral, dict):
        clid = ad_referral.get("ctwa_clid") or ad_referral.get("ctwaClid")
        if clid:
            user_data["ctwa_clid"] = clid
    if not user_data:
        return False  # a Meta exige ao menos 1 identificador

    event = {
        "event_name": "Lead",
        "event_time": int(time.time()),
        "action_source": _ACTION_SOURCE,
        "user_data": user_data,
        "custom_data": {"value": float(value or 0), "currency": currency, "lead_source": "whatsapp"},
    }
    if lead_id:
        event["event_id"] = f"lead-{lead_id}"  # dedup com o pixel, se existir

    payload: dict = {"data": [event]}
    test_code = os.getenv("META_CAPI_TEST_EVENT_CODE", "").strip()
    if test_code:
        payload["test_event_code"] = test_code

    url = f"https://graph.facebook.com/{_GRAPH_VERSION}/{_DATASET_ID}/events?access_token={token}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    logger.info("Meta CAPI: evento Lead enviado (lead_id=%s)", lead_id)
                    return True
                logger.warning("Meta CAPI: Lead falhou HTTP %s — %s", r.status, (await r.text())[:240])
                return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Meta CAPI: exceção ao enviar Lead: %s", e)
        return False
