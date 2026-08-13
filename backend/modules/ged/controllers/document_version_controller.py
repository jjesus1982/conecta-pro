"""Controller para DocumentVersion."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from modules.ged.schemas.document_version import (
    DocumentVersionCompare,
    DocumentVersionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-versions", tags=["GED - Versões"])


@router.get("/{version_id}", response_model=DocumentVersionResponse)
async def get_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionResponse:
    """Busca versão por ID."""
    repository = DocumentVersionRepository(db)
    version = await repository.get_by_id(version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    return DocumentVersionResponse.model_validate(version)


@router.get("/document/{document_id}", response_model=list[DocumentVersionResponse])
async def get_by_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentVersionResponse]:
    """Retorna versões de um documento."""
    repository = DocumentVersionRepository(db)
    versions = await repository.get_by_document(document_id)
    return [DocumentVersionResponse.model_validate(v) for v in versions]


@router.get("/document/{document_id}/current", response_model=DocumentVersionResponse)
async def get_current_version(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionResponse:
    """Retorna versão atual do documento."""
    repository = DocumentVersionRepository(db)
    version = await repository.get_current(document_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    return DocumentVersionResponse.model_validate(version)


@router.get(
    "/document/{document_id}/version/{version_number}",
    response_model=DocumentVersionResponse,
)
async def get_by_version_number(
    document_id: str,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionResponse:
    """Retorna versão específica."""
    repository = DocumentVersionRepository(db)
    version = await repository.get_by_number(document_id, version_number)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    return DocumentVersionResponse.model_validate(version)


@router.post("/{version_id}/set-current", response_model=DocumentVersionResponse, status_code=201)
async def set_as_current(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionResponse:
    """Define versão como atual."""
    repository = DocumentVersionRepository(db)
    version = await repository.set_as_current(version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    await db.commit()
    return DocumentVersionResponse.model_validate(version)


@router.post("/{version_id}/archive", response_model=DocumentVersionResponse, status_code=201)
async def archive_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionResponse:
    """Arquiva versão."""
    repository = DocumentVersionRepository(db)
    version = await repository.archive(version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    await db.commit()
    return DocumentVersionResponse.model_validate(version)


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove versão."""
    repository = DocumentVersionRepository(db)

    # Verifica se é a versão atual
    version = await repository.get_by_id(version_id)
    if version and version.is_current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível remover a versão atual",
        )

    if not await repository.delete(version_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versão não encontrada")
    await db.commit()


@router.get(
    "/document/{document_id}/compare",
    response_model=DocumentVersionCompare,
)
async def compare_versions(
    document_id: str,
    version_a: int = Query(..., ge=1),
    version_b: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentVersionCompare:
    """Compara duas versões."""
    repository = DocumentVersionRepository(db)

    ver_a = await repository.get_by_number(document_id, version_a)
    ver_b = await repository.get_by_number(document_id, version_b)

    if not ver_a or not ver_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uma ou ambas versões não encontradas",
        )

    compare_result = await repository.compare_versions(ver_a.id, ver_b.id)
    # `compare_versions` devolve `dict | None`; sem esta guarda o None virava
    # `DocumentVersionCompare(**None)` → TypeError → 500 no lugar do 404 honesto.
    if compare_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Não foi possível comparar as versões informadas",
        )
    return DocumentVersionCompare(**compare_result)


@router.get("/document/{document_id}/count")
async def get_version_count(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict[str, Any]:
    """Retorna contagem de versões."""
    repository = DocumentVersionRepository(db)
    versions = await repository.get_by_document(document_id)
    return {
        "document_id": document_id,
        "total_versions": len(versions),
        "current_version": max((v.version_number for v in versions if v.is_current), default=0),
    }


@router.get("/document/{document_id}/stats")
async def get_version_stats(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict[str, Any]:
    """Retorna estatísticas de versões."""
    repository = DocumentVersionRepository(db)
    stats = await repository.get_stats(document_id)
    return stats
