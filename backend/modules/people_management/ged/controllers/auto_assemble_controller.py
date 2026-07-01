"""
Controller standalone para auto-assemble de kits documentais.

Isolado do aggregator para evitar import circular via people_management.__init__.
Registrado diretamente no main_production.py.
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GED - Auto-Assemble"])


@router.post("/auto-assemble", status_code=201)
async def auto_assemble_kits(
    reference_month: date | None = Query(None, description="Mes de referencia (default: mes atual)"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Monta kits automaticamente para todos os clientes ativos.

    Coleta documentos de DP, Fiscal e Operacoes automaticamente
    para cada cliente que tem funcionarios alocados.
    """
    from modules.people_management.ged.services.kit_builder_service import KitBuilderService

    ref = reference_month or date.today().replace(day=1)
    builder = KitBuilderService(db)
    try:
        result = await builder.auto_build_all_kits(ref)
        await db.commit()
        return result
    except Exception as e:
        logger.error("Erro no auto-assemble: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kits")
async def list_kits(
    client_id: str | None = Query(None),
    status: str | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista kits documentais com filtros."""
    from sqlalchemy import text

    conditions = []
    params: dict[str, Any] = {}

    if client_id:
        conditions.append("client_id = :client_id")
        params["client_id"] = client_id
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if month and year:
        conditions.append("EXTRACT(MONTH FROM reference_month) = :month")
        conditions.append("EXTRACT(YEAR FROM reference_month) = :year")
        params["month"] = month
        params["year"] = year

    where = " AND ".join(conditions) if conditions else "1=1"
    query = text(
        f"SELECT * FROM ged_document_kits WHERE {where} ORDER BY reference_month DESC, created_at DESC LIMIT 50"
    )
    result = await db.execute(query, params)
    rows = result.mappings().all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(r["id"]),
                "client_id": str(r["client_id"]) if r["client_id"] else None,
                "reference_month": r["reference_month"].isoformat() if r["reference_month"] else None,
                "status": r["status"],
                "total_employees": r["total_employees"],
                "total_documents": r["total_documents"],
                "documents_signed": r["documents_signed"],
                "completion_percentage": float(r["completion_percentage"]) if r["completion_percentage"] else 0,
                "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
                "sent_method": r["sent_method"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/dashboard")
async def ged_dashboard(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard consolidado do GED com metricas operacionais."""
    from sqlalchemy import text

    # Total de documentos por status
    docs_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE NOT is_signed) as ativos,
            count(*) FILTER (WHERE is_signed) as assinados,
            0 as expirados
        FROM ged_kit_documents
    """)
    )
    docs = docs_result.mappings().first()

    # Kits do mes atual
    kits_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE status = 'EM_MONTAGEM') as em_montagem,
            count(*) FILTER (WHERE status = 'COMPLETO') as completos,
            count(*) FILTER (WHERE status = 'ENVIADO') as enviados,
            count(*) FILTER (WHERE status = 'APROVADO') as aprovados,
            COALESCE(AVG(completion_percentage), 0) as media_completude
        FROM ged_document_kits
        WHERE EXTRACT(MONTH FROM reference_month) = EXTRACT(MONTH FROM CURRENT_DATE)
          AND EXTRACT(YEAR FROM reference_month) = EXTRACT(YEAR FROM CURRENT_DATE)
    """)
    )
    kits = kits_result.mappings().first()

    # Pastas
    folders_result = await db.execute(
        text("""
        SELECT count(*) as total FROM ged_folders WHERE status = 'ativa'
    """)
    )
    folders = folders_result.mappings().first()

    # Tags
    tags_result = await db.execute(
        text("""
        SELECT count(*) as total FROM ged_document_tags WHERE is_active = true
    """)
    )
    tags = tags_result.mappings().first()

    # Clientes GED
    clients_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE portal_access_enabled = true) as com_portal
        FROM ged_clients
    """)
    )
    clients = clients_result.mappings().first()

    return {
        "documentos": {
            "total": docs["total"] if docs else 0,
            "ativos": docs["ativos"] if docs else 0,
            "assinados": docs["assinados"] if docs else 0,
            "expirados": docs["expirados"] if docs else 0,
        },
        "kits_mes_atual": {
            "total": kits["total"] if kits else 0,
            "em_montagem": kits["em_montagem"] if kits else 0,
            "completos": kits["completos"] if kits else 0,
            "enviados": kits["enviados"] if kits else 0,
            "aprovados": kits["aprovados"] if kits else 0,
            "media_completude": round(float(kits["media_completude"]), 1) if kits else 0,
        },
        "pastas": folders["total"] if folders else 0,
        "tags": tags["total"] if tags else 0,
        "clientes": {
            "total": clients["total"] if clients else 0,
            "com_portal": clients["com_portal"] if clients else 0,
        },
    }
