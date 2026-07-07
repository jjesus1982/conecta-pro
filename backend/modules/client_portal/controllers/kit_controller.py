"""
Controller de Kits Documentais do Portal do Cliente.

Endpoints protegidos por autenticacao do portal para listagem,
detalhamento e download de kits e documentos.
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.schemas.kit import (
    PortalDocumentResponse,
    PortalKitListResponse,
    PortalKitResponse,
)
from modules.client_portal.services.kit_access_service import PortalKitAccessService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kits", tags=["Portal - Kits Documentais"])


@router.get("", response_model=PortalKitListResponse)
async def list_kits(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Offset para paginacao"),
    limit: int = Query(20, ge=1, le=100, description="Registros por pagina"),
    status: str | None = Query(None, description="Filtrar por status do kit"),
) -> Any:
    """Lista kits documentais do cliente autenticado.

    Retorna kits com paginacao e filtro opcional por status.
    Cada kit inclui a lista de documentos associados.
    """
    service = PortalKitAccessService(db)
    return await service.list_kits(
        client_id=client_id,
        skip=skip,
        limit=limit,
        status_filter=status,
    )


@router.get("/historico-drive", summary="Historico de kits com links do Drive")
async def historico_drive(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Historico de kits documentais com links do Google Drive.

    Retorna os ultimos 24 meses de kits que possuem link no Drive,
    ordenados do mais recente ao mais antigo.
    """
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.models.kit_document import KitDocument

    result = await db.execute(
        sa_select(GedDocumentKit)
        .where(
            GedDocumentKit.client_id == client_id,
            GedDocumentKit.google_drive_link.isnot(None),
        )
        .order_by(GedDocumentKit.reference_month.desc())
        .limit(24)
    )
    kits = result.scalars().all()

    # total_docs AO VIVO (COUNT real em ged_kit_documents) numa única query
    # agregada — a coluna stored total_documents fica stale.
    doc_counts: dict[str, int] = {}
    kit_ids = [str(kit.id) for kit in kits]
    if kit_ids:
        counts_result = await db.execute(
            sa_select(KitDocument.kit_id, sa_func.count())
            .where(KitDocument.kit_id.in_(kit_ids))
            .group_by(KitDocument.kit_id)
        )
        doc_counts = {str(row[0]): int(row[1] or 0) for row in counts_result.all()}

    return {
        "total": len(kits),
        "kits": [
            {
                "competencia": kit.reference_month.strftime("%Y-%m"),
                "total_docs": doc_counts.get(str(kit.id), 0),
                "share_link": kit.google_drive_link,
                "status": kit.status,
                "criado_em": str(kit.created_at.date()) if kit.created_at else "",
            }
            for kit in kits
        ],
    }


@router.get("/{kit_id}", response_model=PortalKitResponse)
async def get_kit(
    kit_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um kit documental especifico.

    Registra automaticamente um log de acesso (viewed).
    """
    service = PortalKitAccessService(db)
    try:
        return await service.get_kit(client_id=client_id, kit_id=kit_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{kit_id}/documents", response_model=list[PortalDocumentResponse])
async def list_kit_documents(
    kit_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista documentos de um kit documental especifico.

    Retorna todos os documentos associados ao kit com metadados.
    """
    service = PortalKitAccessService(db)
    try:
        return await service.list_documents(client_id=client_id, kit_id=kit_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{kit_id}/documents/{document_id}/download")
async def download_document(
    kit_id: str,
    document_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Baixa um documento especifico de um kit.

    Valida que o documento pertence ao kit do cliente autenticado
    e registra um log de download antes de servir o arquivo.
    """
    service = PortalKitAccessService(db)
    try:
        doc_info = await service.get_document_for_download(
            client_id=client_id,
            kit_id=kit_id,
            document_id=document_id,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    file_path = Path(doc_info["file_path"])
    if not file_path.exists():
        logger.error("Arquivo nao encontrado no disco: %s", file_path)
        raise HTTPException(
            status_code=404,
            detail="Arquivo nao encontrado no servidor",
        )

    # Segurança: confina o arquivo servido sob /app/uploads (anti path-traversal).
    # Mesmo que um file_path malicioso entre no banco, não serve nada fora da raiz.
    raiz = Path("/app/uploads").resolve()
    if raiz not in file_path.resolve().parents:
        logger.error("Tentativa de servir arquivo fora de /app/uploads: %s", file_path)
        raise HTTPException(status_code=403, detail="Caminho de arquivo não permitido")

    return FileResponse(
        path=str(file_path),
        filename=doc_info["file_name"],
        media_type=doc_info["mime_type"],
    )
