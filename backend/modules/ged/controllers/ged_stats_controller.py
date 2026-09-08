"""Controller para estatísticas gerais consolidadas do GED."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.services.document_service import DocumentService
from modules.ged.services.document_share_service import DocumentShareService
from modules.ged.services.document_signature_service import DocumentSignatureService
from modules.ged.services.document_tag_service import DocumentTagService
from modules.ged.services.folder_service import FolderService

logger = logging.getLogger(__name__)

# Sem prefix aqui - será adicionado no include_router
router = APIRouter(tags=["GED - Estatísticas"])


@router.get("/stats")
async def get_ged_stats(
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """
    Retorna estatísticas consolidadas do GED combinando dados de:
    - Folders (pastas)
    - Documents (documentos)
    - Shares (compartilhamentos)
    - Signatures (assinaturas)
    - Tags (etiquetas)
    """
    # Inicializar services
    folder_service = FolderService(db)
    document_service = DocumentService(db)
    share_service = DocumentShareService(db)
    signature_service = DocumentSignatureService(db)
    tag_service = DocumentTagService(db)

    # Coletar stats de cada módulo
    try:
        folder_stats = await folder_service.get_stats(condominium_id)
        document_stats = await document_service.get_stats(condominium_id)

        # Stats de shares
        share_stats = await share_service.get_stats(condominium_id)

        # Stats de signatures
        signature_stats = await signature_service.get_stats(condominium_id)

        # Stats de tags
        tag_stats = await tag_service.get_stats(condominium_id)

    except Exception as e:
        logger.error(f"Erro ao coletar stats do GED: {e}")
        # Retornar stats vazios em caso de erro
        return {
            "total_folders": 0,
            "active_folders": 0,
            "archived_folders": 0,
            "total_documents": 0,
            "active_documents": 0,
            "total_storage_bytes": 0,
            "total_storage_mb": 0,
            "total_versions": 0,
            "expired_documents": 0,
            "total_signatures": 0,
            "pending_signatures": 0,
            "total_shares": 0,
            "active_shares": 0,
            "total_tags": 0,
            "documents_by_type": {},
            "documents_by_status": {},
            "documents_by_category": {},
            "folders_by_type": {},
            "recent_documents": [],
            "expiring_soon": [],
        }

    # Combinar stats em formato esperado pelo frontend
    return {
        # Folders
        "total_folders": getattr(folder_stats, "total_folders", 0),
        "active_folders": getattr(folder_stats, "active_folders", 0),
        "archived_folders": getattr(folder_stats, "archived_folders", 0),
        # Documents
        "total_documents": getattr(document_stats, "total_documents", 0),
        "active_documents": sum(
            count
            for status, count in getattr(document_stats, "by_status", {}).items()
            if status not in ["arquivado", "excluido"]
        ),
        "total_storage_bytes": getattr(folder_stats, "total_size_bytes", 0),
        "total_storage_mb": getattr(folder_stats, "total_size_mb", 0),
        "total_versions": 0,
        "expired_documents": getattr(document_stats, "expired", 0),
        # Signatures
        "total_signatures": getattr(signature_stats, "total_signatures", 0),
        "pending_signatures": getattr(signature_stats, "pending_signatures", 0),
        # Shares
        "total_shares": getattr(share_stats, "total_shares", 0),
        "active_shares": getattr(share_stats, "active_shares", 0),
        # Tags
        "total_tags": getattr(tag_stats, "total_tags", 0),
        # Distribuições
        "documents_by_type": getattr(document_stats, "by_type", {}),
        "documents_by_status": getattr(document_stats, "by_status", {}),
        "documents_by_category": getattr(document_stats, "by_category", {}),
        "folders_by_type": getattr(folder_stats, "by_type", {}),
        # Listas
        "recent_documents": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "created_at": doc.created_at.isoformat()
                if hasattr(doc.created_at, "isoformat")
                else str(doc.created_at),
                "file_extension": getattr(doc, "file_extension", ""),
                "file_size_bytes": getattr(doc, "file_size_bytes", 0),
            }
            for doc in (getattr(document_stats, "recent_documents", []) or [])[:10]
        ],
        "expiring_soon": [
            {
                "id": str(doc.id),
                "title": doc.title,
                "valid_until": doc.valid_until.isoformat() if hasattr(doc, "valid_until") and doc.valid_until else None,
                "file_extension": getattr(doc, "file_extension", ""),
            }
            for doc in (getattr(document_stats, "expiring_soon", []) or [])[:10]
        ],
    }
