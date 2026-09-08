"""Controller para fornecedores."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.schemas.supplier import (
    SupplierBlockRequest,
    SupplierCreate,
    SupplierFilter,
    SupplierListResponse,
    SupplierQualifyRequest,
    SupplierResponse,
    SupplierStats,
    SupplierUpdate,
)
from modules.financial.services.supplier_service import SupplierService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suppliers", tags=["Fornecedores"])


def get_service(session: AsyncSession = Depends(get_session)) -> SupplierService:
    """Retorna instância do service."""
    return SupplierService(session)


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar fornecedor",
)
async def create_supplier(
    data: SupplierCreate,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Cria um novo fornecedor."""
    try:
        supplier = await service.create(data, current_user.id)
        return SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar fornecedor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar fornecedor",
        )


@router.get(
    "",
    response_model=list[SupplierListResponse],
    summary="Listar fornecedores",
)
async def list_suppliers(  # pylint: disable=too-many-locals,unused-argument
    condominio_id: UUID | None = Query(None),
    search: str | None = Query(None, description="Busca por nome, razão social ou CNPJ"),
    supplier_type: str | None = Query(None, description="Tipo de fornecedor"),
    category: str | None = Query(None, description="Categoria"),
    status_filter: str | None = Query(None, alias="status", description="Status"),
    is_qualified: bool | None = Query(None, description="Apenas qualificados"),
    is_blocked: bool | None = Query(None, description="Apenas bloqueados"),
    city: str | None = Query(None, description="Cidade"),
    state: str | None = Query(None, description="Estado (UF)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
):
    """Lista fornecedores com filtros."""
    filters = SupplierFilter(
        search=search,
        supplier_type=supplier_type,
        category=category,
        status=status_filter,
        is_qualified=is_qualified,
        is_blocked=is_blocked,
        city=city,
        state=state,
    )

    suppliers, _total = await service.list(condominio_id, filters, skip, limit)
    return [SupplierListResponse.model_validate(s) for s in suppliers]


@router.get(
    "/stats",
    response_model=SupplierStats,
    summary="Estatísticas de fornecedores",
)
async def get_stats(  # pylint: disable=unused-argument
    condominio_id: UUID | None = Query(None),
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierStats:
    """Retorna estatísticas de fornecedores."""
    return await service.get_stats(condominio_id)


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Buscar fornecedor",
)
async def get_supplier(  # pylint: disable=unused-argument
    supplier_id: UUID,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Busca fornecedor por ID."""
    supplier = await service.get_by_id(supplier_id)
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fornecedor não encontrado",
        )
    return SupplierResponse.model_validate(supplier)


@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Atualizar fornecedor",
)
async def update_supplier(  # pylint: disable=unused-argument
    supplier_id: UUID,
    data: SupplierUpdate,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Atualiza um fornecedor."""
    try:
        supplier = await service.update(supplier_id, data)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fornecedor não encontrado",
            )
        return SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir fornecedor",
)
async def delete_supplier(  # pylint: disable=unused-argument
    supplier_id: UUID,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
):
    """Exclui um fornecedor (soft delete)."""
    deleted = await service.delete(supplier_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fornecedor não encontrado",
        )


@router.post("/{supplier_id}/block", response_model=SupplierResponse, summary="Bloquear fornecedor", status_code=201)
async def block_supplier(
    supplier_id: UUID,
    data: SupplierBlockRequest,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Bloqueia um fornecedor."""
    try:
        supplier = await service.block(supplier_id, data.reason, current_user.id)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fornecedor não encontrado",
            )
        return SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{supplier_id}/unblock", response_model=SupplierResponse, summary="Desbloquear fornecedor", status_code=201
)
async def unblock_supplier(  # pylint: disable=unused-argument
    supplier_id: UUID,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Desbloqueia um fornecedor."""
    try:
        supplier = await service.unblock(supplier_id)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fornecedor não encontrado",
            )
        return SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{supplier_id}/qualify", response_model=SupplierResponse, summary="Qualificar fornecedor", status_code=201
)
async def qualify_supplier(  # pylint: disable=unused-argument
    supplier_id: UUID,
    data: SupplierQualifyRequest | None = None,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
) -> SupplierResponse:
    """Qualifica um fornecedor."""
    try:
        supplier = await service.qualify(supplier_id, current_user.id)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fornecedor não encontrado",
            )
        return SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{supplier_id}/validate-payment",
    summary="Validar fornecedor para pagamento",
)
async def validate_for_payment(  # pylint: disable=unused-argument
    supplier_id: UUID,
    service: SupplierService = Depends(get_service),
    current_user: dict = Depends(get_current_user),
):
    """Valida se fornecedor pode receber pagamentos."""
    is_valid, message = await service.validate_for_payment(supplier_id)
    return {"is_valid": is_valid, "message": message}
