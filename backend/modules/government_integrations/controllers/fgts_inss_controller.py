import re
"""
Controller para cálculos de FGTS e INSS.
"""

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

# Imports relativos do módulo pai


logger = logging.getLogger(__name__)

def _norm_mes(v: str | None) -> str:
    """'03.2026', '2026-03', '03/2026' → '2026-03'."""
    d = re.sub(r"[^0-9]", "", v or "")
    if len(d) != 6:
        return v or ""
    return f"{d[2:]}-{d[:2]}" if int(d[:2]) <= 12 else f"{d[:4]}-{d[4:]}"


router = APIRouter(tags=["FGTS/INSS"])


@router.get(
    "/fgts/guias",
    status_code=status.HTTP_200_OK,
    summary="Listar guias FGTS",
    description="Lista guias de recolhimento FGTS (GRF) armazenadas no GED.",
)
async def listar_guias_fgts(
    current_user: CurrentActiveUser,
    mes_ref: str | None = Query(None, description="Filtro por mês (ex: 03.2026 ou 2026-03)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lista guias GRF_FGTS do GED."""
    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.models.kit_document import KitDocument

    query = (
        select(KitDocument, GedDocumentKit.reference_month)
        .join(GedDocumentKit, KitDocument.kit_id == GedDocumentKit.id)
        .where(KitDocument.document_type.in_(["fgts_guia", "gfd_fgts_mensal"]))  # tipos reais do kit (grf_fgts nunca existiu, 08/09/2026)
        .order_by(GedDocumentKit.reference_month.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    items = []
    for doc, ref_month in rows:
        mes_str = ref_month.strftime("%m.%Y") if ref_month else None
        if mes_ref and _norm_mes(mes_ref) != _norm_mes(mes_str):
            continue
        items.append(
            {
                "id": str(doc.id),
                "mes_ref": mes_str,
                "tipo": doc.document_type,
                "nome": doc.document_name,
                "arquivo_pdf": doc.file_path,
                "status": "disponivel" if doc.file_path else "pendente",
                "criado_em": doc.created_at.isoformat() if doc.created_at else None,
            }
        )

    return {"total": len(items), "items": items}


@router.get(
    "/inss/guias",
    status_code=status.HTTP_200_OK,
    summary="Listar guias INSS",
    description="Lista guias de recolhimento INSS (GPS) armazenadas no GED.",
)
async def listar_guias_inss(
    current_user: CurrentActiveUser,
    mes_ref: str | None = Query(None, description="Filtro por mês (ex: 03.2026 ou 2026-03)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lista guias GPS_INSS do GED."""
    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.models.kit_document import KitDocument

    query = (
        select(KitDocument, GedDocumentKit.reference_month)
        .join(GedDocumentKit, KitDocument.kit_id == GedDocumentKit.id)
        .where(KitDocument.document_type.in_(["inss_guia"]))  # tipo real do kit (gps_inss nunca existiu, 08/09/2026)
        .order_by(GedDocumentKit.reference_month.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    items = []
    for doc, ref_month in rows:
        mes_str = ref_month.strftime("%m.%Y") if ref_month else None
        if mes_ref and _norm_mes(mes_ref) != _norm_mes(mes_str):
            continue
        items.append(
            {
                "id": str(doc.id),
                "mes_ref": mes_str,
                "nome": doc.document_name,
                "arquivo_pdf": doc.file_path,
                "status": "disponivel" if doc.file_path else "pendente",
                "criado_em": doc.created_at.isoformat() if doc.created_at else None,
            }
        )

    return {"total": len(items), "items": items}
