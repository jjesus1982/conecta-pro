"""
GED Config & Reports Controller.

Endpoints:
- GET  /config/drive      → status Google Drive
- GET  /config/schedule   → agendamento de envios
- PUT  /config/schedule   → salvar agendamento
- GET  /reports/monthly   → relatório mensal GED
"""

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GED - Config & Reports"])


# ─── GED Clients (alias /ged/clients → proxy to people-management) ────────────


_schedule_config: dict[str, Any] = {
    "envio_automatico": False,
    "dia_envio": 25,
    "hora_envio": "09:00",
    "canal_envio": "whatsapp",
    "incluir_certidoes": True,
    "incluir_kits": True,
    "destinatarios": [],
    "ativo": False,
}



@router.get("/clients")
@router.get("/clients/", include_in_schema=False)
async def list_ged_clients(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista clientes GED. Alias para /people-management/ged/clients."""
    result = await db.execute(
        text("""
        SELECT id, name, type, cnpj, address, contact_name, contact_email,
            contact_phone, portal_access_enabled, is_active, created_at
        FROM ged_clients
        WHERE is_active = true
        ORDER BY name
        """)
    )
    rows = result.mappings().all()
    return {
        "items": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "type": r["type"],
                "cnpj": r["cnpj"],
                "address": r["address"],
                "contact_name": r["contact_name"],
                "contact_email": r["contact_email"],
                "contact_phone": r["contact_phone"],
                "portal_access_enabled": r["portal_access_enabled"],
                "is_active": r["is_active"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/config/schedule")
async def get_config_schedule(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna configuração de agendamento de envios."""
    return _schedule_config


@router.put("/config/schedule")
async def update_config_schedule(
    config: dict[str, Any],
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Salva configuração de agendamento."""
    allowed_keys = {
        "envio_automatico",
        "dia_envio",
        "hora_envio",
        "canal_envio",
        "incluir_certidoes",
        "incluir_kits",
        "destinatarios",
        "ativo",
    }
    for key, value in config.items():
        if key in allowed_keys:
            _schedule_config[key] = value

    logger.info("GED schedule atualizado: %s", config)
    return _schedule_config


# ─── Config Email Templates ──────────────────────────────────────────────────


@router.get("/config/document-types")
async def get_document_types(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna tipos de documentos configurados para kits GED."""
    result = await db.execute(
        text("""
        SELECT id, name, category, description, required_for_kit, is_active
        FROM ged_document_types
        WHERE is_active = true
        ORDER BY category, name
        """)
    )
    rows = result.mappings().all()
    tipos = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "category": r["category"],
            "description": r["description"],
            "required_for_kit": r["required_for_kit"],
            "is_active": r["is_active"],
        }
        for r in rows
    ]
    return {"tipos": tipos, "total": len(tipos)}


# ─── Reports Monthly ─────────────────────────────────────────────────────────


