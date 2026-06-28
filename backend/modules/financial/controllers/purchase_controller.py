"""Controller para módulo de compras."""

import logging
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models.goods_receipt import ReceiptStatus, ReceiptType
from modules.financial.models.purchase_approval import ApprovalLevel, ApprovalStatus, ApprovalType
from modules.financial.models.purchase_order import OrderPriority, OrderStatus
from modules.financial.models.purchase_quotation import QuotationStatus
from modules.financial.models.purchase_requisition import RequisitionPriority, RequisitionStatus
from modules.financial.repositories.purchase_repository import (
    GoodsReceiptRepository,
    ProductCategoryRepository,
    ProductRepository,
    PurchaseApprovalRepository,
    PurchaseOrderRepository,
    PurchaseQuotationRepository,
    PurchaseRequisitionRepository,
)
from modules.financial.schemas.goods_receipt import (
    GoodsReceiptCreate,
    GoodsReceiptListResponse,
    GoodsReceiptResponse,
    GoodsReceiptUpdate,
    ReceiptApproveRequest,
    ReceiptDivergenceRequest,
    ReceiptFilter,
    ReceiptInspectionRequest,
    ReceiptRejectRequest,
    ReceiptSignRequest,
    ReceiptStats,
)
from modules.financial.schemas.product import (
    ProductBlockRequest,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductStats,
    ProductUpdate,
)
from modules.financial.schemas.product_category import (
    ProductCategoryCreate,
    ProductCategoryResponse,
    ProductCategoryStats,
    ProductCategoryTreeResponse,
    ProductCategoryUpdate,
)
from modules.financial.schemas.purchase_approval import (
    ApprovalApproveRequest,
    ApprovalDelegateRequest,
    ApprovalFilter,
    ApprovalInfoProvideRequest,
    ApprovalInfoRequest,
    ApprovalRejectRequest,
    ApprovalStats,
    MyApprovalsResponse,
    PurchaseApprovalListResponse,
    PurchaseApprovalResponse,
)
from modules.financial.schemas.purchase_order import (
    OrderApproveRequest,
    OrderCancelRequest,
    OrderFilter,
    OrderRejectRequest,
    OrderStats,
    PurchaseOrderCreate,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
)
from modules.financial.schemas.purchase_quotation import (
    PurchaseQuotationCreate,
    PurchaseQuotationListResponse,
    PurchaseQuotationResponse,
    PurchaseQuotationUpdate,
    QuotationComparisonResponse,
    QuotationRejectRequest,
    QuotationScoreRequest,
    QuotationSelectRequest,
    QuotationStats,
)
from modules.financial.schemas.purchase_requisition import (
    PurchaseRequisitionCreate,
    PurchaseRequisitionListResponse,
    PurchaseRequisitionResponse,
    PurchaseRequisitionUpdate,
    RequisitionApproveRequest,
    RequisitionCancelRequest,
    RequisitionFilter,
    RequisitionRejectRequest,
    RequisitionStats,
)
from modules.financial.services.purchase_ai_service import PurchaseAIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/purchases", tags=["Compras"])


# ==================== Product Categories ====================


@router.post(
    "/categories",
    response_model=ProductCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar categoria de produto",
)
async def create_product_category(
    data: ProductCategoryCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductCategoryResponse:
    """Cria uma nova categoria de produto."""
    try:
        repo = ProductCategoryRepository(session)
        existing = await repo.get_by_code(data.code, data.condominio_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe uma categoria com este código",
            )
        category = await repo.create(data, _current_user.id)
        await session.commit()
        return ProductCategoryResponse.model_validate(category)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar categoria: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar categoria",
        )


@router.get(
    "/categories",
    response_model=list[ProductCategoryResponse],
    summary="Listar categorias de produto",
)
async def list_product_categories(
    condominio_id: UUID | None = Query(None),
    parent_id: UUID | None = Query(None, description="ID da categoria pai"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> list[ProductCategoryResponse]:
    """Lista categorias de produto."""
    repo = ProductCategoryRepository(session)
    categories = await repo.list(condominio_id, parent_id, skip, limit)
    return [ProductCategoryResponse.model_validate(c) for c in categories]


@router.get(
    "/categories/tree",
    response_model=list[ProductCategoryTreeResponse],
    summary="Árvore de categorias",
)
async def get_category_tree(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> list[ProductCategoryTreeResponse]:
    """Retorna árvore completa de categorias."""
    repo = ProductCategoryRepository(session)
    categories = await repo.get_tree(condominio_id)
    return [ProductCategoryTreeResponse.model_validate(c) for c in categories]


@router.get(
    "/categories/stats",
    response_model=ProductCategoryStats,
    summary="Estatísticas de categorias",
)
async def get_category_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductCategoryStats:
    """Retorna estatísticas de categorias."""
    repo = ProductCategoryRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/categories/{category_id}",
    response_model=ProductCategoryResponse,
    summary="Buscar categoria",
)
async def get_product_category(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductCategoryResponse:
    """Busca categoria por ID."""
    repo = ProductCategoryRepository(session)
    category = await repo.get_by_id(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoria não encontrada",
        )
    return ProductCategoryResponse.model_validate(category)


@router.put(
    "/categories/{category_id}",
    response_model=ProductCategoryResponse,
    summary="Atualizar categoria",
)
async def update_product_category(
    category_id: UUID,
    data: ProductCategoryUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductCategoryResponse:
    """Atualiza uma categoria de produto."""
    try:
        repo = ProductCategoryRepository(session)
        category = await repo.get_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria não encontrada",
            )
        category = await repo.update(category, data)
        await session.commit()
        return ProductCategoryResponse.model_validate(category)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar categoria: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar categoria",
        )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir categoria",
)
async def delete_product_category(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Exclui uma categoria (soft delete)."""
    repo = ProductCategoryRepository(session)
    category = await repo.get_by_id(category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoria não encontrada",
        )
    await repo.delete(category)
    await session.commit()


# ==================== Products ====================


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar produto",
)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Cria um novo produto."""
    try:
        repo = ProductRepository(session)
        existing = await repo.get_by_code(data.code, data.condominio_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um produto com este código",
            )
        product = await repo.create(data, _current_user.id)
        await session.commit()
        return ProductResponse.model_validate(product)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar produto: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar produto",
        )


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="Listar produtos",
)
async def list_products(  # pylint: disable=unused-argument
    condominio_id: UUID,
    search: str | None = Query(None, description="Busca por nome ou código"),
    category_id: UUID | None = Query(None, description="ID da categoria"),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductListResponse:
    """Lista produtos com filtros."""
    repo = ProductRepository(session)
    products = await repo.list(condominio_id, search, category_id, None, skip, limit)
    total = await repo.count(condominio_id, search, category_id, None)
    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/products/stats",
    response_model=ProductStats,
    summary="Estatísticas de produtos",
)
async def get_product_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductStats:
    """Retorna estatísticas de produtos."""
    repo = ProductRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Buscar produto",
)
async def get_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Busca produto por ID."""
    repo = ProductRepository(session)
    product = await repo.get_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado",
        )
    return ProductResponse.model_validate(product)


@router.put(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Atualizar produto",
)
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Atualiza um produto."""
    try:
        repo = ProductRepository(session)
        product = await repo.get_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado",
            )
        product = await repo.update(product, data)
        await session.commit()
        return ProductResponse.model_validate(product)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar produto: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar produto",
        )


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir produto",
)
async def delete_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Exclui um produto (soft delete)."""
    repo = ProductRepository(session)
    product = await repo.get_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado",
        )
    await repo.delete(product)
    await session.commit()


@router.post(
    "/products/{product_id}/block", response_model=ProductResponse, summary="Bloquear produto", status_code=201
)
async def block_product(
    product_id: UUID,
    data: ProductBlockRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Bloqueia um produto."""
    repo = ProductRepository(session)
    product = await repo.get_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado",
        )
    product.block(data.reason, _current_user.id)
    await session.commit()
    await session.refresh(product)
    return ProductResponse.model_validate(product)


# ==================== Purchase Requisitions ====================


@router.post(
    "/requisitions",
    response_model=PurchaseRequisitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar requisição de compra",
)
async def create_requisition(
    data: PurchaseRequisitionCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Cria uma nova requisição de compra."""
    try:
        repo = PurchaseRequisitionRepository(session)
        requisition = await repo.create(data, _current_user.id)
        await session.commit()
        await session.refresh(requisition)
        return PurchaseRequisitionResponse.model_validate(requisition)
    except Exception as e:
        logger.error(f"Erro ao criar requisição: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar requisição",
        )


@router.get(
    "/requisitions",
    response_model=PurchaseRequisitionListResponse,
    summary="Listar requisições",
)
async def list_requisitions(
    condominio_id: UUID,
    status_filter: list[str] | None = Query(None, alias="status"),
    priority: list[str] | None = Query(None),
    requester_id: UUID | None = Query(None),
    department: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionListResponse:
    """Lista requisições com filtros."""
    filters = RequisitionFilter(
        status=[RequisitionStatus(s) for s in status_filter] if status_filter else None,
        priority=[RequisitionPriority(p) for p in priority] if priority else None,
        requester_id=requester_id,
        department=department,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    repo = PurchaseRequisitionRepository(session)
    requisitions = await repo.list(condominio_id, filters, skip, limit)
    total = await repo.count(condominio_id, filters)
    return PurchaseRequisitionListResponse(
        items=[PurchaseRequisitionResponse.model_validate(r) for r in requisitions],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/requisitions/stats",
    response_model=RequisitionStats,
    summary="Estatísticas de requisições",
)
async def get_requisition_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> RequisitionStats:
    """Retorna estatísticas de requisições."""
    repo = PurchaseRequisitionRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/requisitions/{requisition_id}",
    response_model=PurchaseRequisitionResponse,
    summary="Buscar requisição",
)
async def get_requisition(
    requisition_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Busca requisição por ID."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )
    return PurchaseRequisitionResponse.model_validate(requisition)


@router.put(
    "/requisitions/{requisition_id}",
    response_model=PurchaseRequisitionResponse,
    summary="Atualizar requisição",
)
async def update_requisition(
    requisition_id: UUID,
    data: PurchaseRequisitionUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Atualiza uma requisição."""
    try:
        repo = PurchaseRequisitionRepository(session)
        requisition = await repo.get_by_id(requisition_id)
        if not requisition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requisição não encontrada",
            )
        requisition = await repo.update(requisition, data)
        await session.commit()
        return PurchaseRequisitionResponse.model_validate(requisition)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar requisição: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar requisição",
        )


@router.post(
    "/requisitions/{requisition_id}/submit",
    response_model=PurchaseRequisitionResponse,
    summary="Submeter para aprovação",
    status_code=201,
)
async def submit_requisition(
    requisition_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Submete requisição para aprovação."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )
    try:
        requisition.submit_for_approval()
        await session.commit()
        await session.refresh(requisition)
        return PurchaseRequisitionResponse.model_validate(requisition)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/requisitions/{requisition_id}/approve",
    response_model=PurchaseRequisitionResponse,
    summary="Aprovar requisição",
    status_code=201,
)
async def approve_requisition(
    requisition_id: UUID,
    data: RequisitionApproveRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Aprova uma requisição."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )
    try:
        notes = data.notes if data else None
        requisition.approve(_current_user.id, notes)
        await session.commit()
        await session.refresh(requisition)
        return PurchaseRequisitionResponse.model_validate(requisition)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/requisitions/{requisition_id}/reject",
    response_model=PurchaseRequisitionResponse,
    summary="Rejeitar requisição",
    status_code=201,
)
async def reject_requisition(
    requisition_id: UUID,
    data: RequisitionRejectRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Rejeita uma requisição."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )
    try:
        requisition.reject(_current_user.id, data.reason)
        await session.commit()
        await session.refresh(requisition)
        return PurchaseRequisitionResponse.model_validate(requisition)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/requisitions/{requisition_id}/cancel",
    response_model=PurchaseRequisitionResponse,
    summary="Cancelar requisição",
    status_code=201,
)
async def cancel_requisition(
    requisition_id: UUID,
    data: RequisitionCancelRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseRequisitionResponse:
    """Cancela uma requisição."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )
    try:
        requisition.cancel(data.reason)
        await session.commit()
        await session.refresh(requisition)
        return PurchaseRequisitionResponse.model_validate(requisition)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/requisitions/{requisition_id}/analyze-risks", summary="Analisar riscos da requisição", status_code=201)
async def analyze_requisition_risks(
    requisition_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Analisa riscos de uma requisição usando IA."""
    repo = PurchaseRequisitionRepository(session)
    requisition = await repo.get_by_id(requisition_id)
    if not requisition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisição não encontrada",
        )

    ai_service = PurchaseAIService(session)  # pylint: disable=too-many-function-args
    risks = await ai_service.analyze_purchase_risks(requisition)  # pylint: disable=no-value-for-parameter
    return risks


# ==================== Purchase Quotations ====================


@router.post(
    "/quotations",
    response_model=PurchaseQuotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar cotação",
)
async def create_quotation(
    data: PurchaseQuotationCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Cria uma nova cotação."""
    try:
        repo = PurchaseQuotationRepository(session)
        quotation = await repo.create(data, _current_user.id)
        await session.commit()
        await session.refresh(quotation)
        return PurchaseQuotationResponse.model_validate(quotation)
    except Exception as e:
        logger.error(f"Erro ao criar cotação: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar cotação",
        )


@router.get(
    "/quotations",
    response_model=PurchaseQuotationListResponse,
    summary="Listar cotações",
)
async def list_quotations(
    condominio_id: UUID,
    status_filter: list[str] | None = Query(None, alias="status"),
    supplier_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationListResponse:
    """Lista cotações com filtros."""
    status_list = [QuotationStatus(s) for s in status_filter] if status_filter else None
    repo = PurchaseQuotationRepository(session)
    quotations = await repo.list(condominio_id, status_list, supplier_id, date_from, date_to, skip, limit)
    total = await repo.count(condominio_id, status_list)
    return PurchaseQuotationListResponse(
        items=[PurchaseQuotationResponse.model_validate(q) for q in quotations],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/quotations/by-requisition/{requisition_id}",
    response_model=list[PurchaseQuotationResponse],
    summary="Listar cotações de uma requisição",
)
async def list_quotations_by_requisition(
    requisition_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> list[PurchaseQuotationResponse]:
    """Lista cotações de uma requisição."""
    repo = PurchaseQuotationRepository(session)
    quotations = await repo.list_by_requisition(requisition_id)
    return [PurchaseQuotationResponse.model_validate(q) for q in quotations]


@router.get(
    "/quotations/compare/{requisition_id}",
    response_model=QuotationComparisonResponse,
    summary="Comparar cotações",
)
async def compare_quotations(
    requisition_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> QuotationComparisonResponse:
    """Compara cotações de uma requisição usando IA."""
    repo = PurchaseQuotationRepository(session)
    quotations = await repo.list_by_requisition(requisition_id)
    if len(quotations) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="São necessárias pelo menos 2 cotações para comparar",
        )

    ai_service = PurchaseAIService(session)  # pylint: disable=too-many-function-args
    comparison = await ai_service.optimize_quotation_selection(quotations)
    return QuotationComparisonResponse(**comparison)


@router.get(
    "/quotations/stats",
    response_model=QuotationStats,
    summary="Estatísticas de cotações",
)
async def get_quotation_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> QuotationStats:
    """Retorna estatísticas de cotações."""
    repo = PurchaseQuotationRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/quotations/{quotation_id}",
    response_model=PurchaseQuotationResponse,
    summary="Buscar cotação",
)
async def get_quotation(
    quotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Busca cotação por ID."""
    repo = PurchaseQuotationRepository(session)
    quotation = await repo.get_by_id(quotation_id)
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotação não encontrada",
        )
    return PurchaseQuotationResponse.model_validate(quotation)


@router.put(
    "/quotations/{quotation_id}",
    response_model=PurchaseQuotationResponse,
    summary="Atualizar cotação",
)
async def update_quotation(
    quotation_id: UUID,
    data: PurchaseQuotationUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Atualiza uma cotação."""
    try:
        repo = PurchaseQuotationRepository(session)
        quotation = await repo.get_by_id(quotation_id)
        if not quotation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cotação não encontrada",
            )
        quotation = await repo.update(quotation, data)
        await session.commit()
        return PurchaseQuotationResponse.model_validate(quotation)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar cotação: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar cotação",
        )


@router.post(
    "/quotations/{quotation_id}/score",
    response_model=PurchaseQuotationResponse,
    summary="Pontuar cotação",
    status_code=201,
)
async def score_quotation(
    quotation_id: UUID,
    data: QuotationScoreRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Pontua uma cotação."""
    repo = PurchaseQuotationRepository(session)
    quotation = await repo.get_by_id(quotation_id)
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotação não encontrada",
        )
    try:
        quotation.set_scores(
            data.technical_score,
            data.commercial_score,
            data.delivery_score,
        )
        await session.commit()
        await session.refresh(quotation)
        return PurchaseQuotationResponse.model_validate(quotation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/quotations/{quotation_id}/select",
    response_model=PurchaseQuotationResponse,
    summary="Selecionar cotação",
    status_code=201,
)
async def select_quotation(
    quotation_id: UUID,
    data: QuotationSelectRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Seleciona uma cotação como vencedora."""
    repo = PurchaseQuotationRepository(session)
    quotation = await repo.get_by_id(quotation_id)
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotação não encontrada",
        )
    try:
        notes = data.notes if data else None
        quotation.select(_current_user.id, notes)
        await session.commit()
        await session.refresh(quotation)
        return PurchaseQuotationResponse.model_validate(quotation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/quotations/{quotation_id}/reject",
    response_model=PurchaseQuotationResponse,
    summary="Rejeitar cotação",
    status_code=201,
)
async def reject_quotation(
    quotation_id: UUID,
    data: QuotationRejectRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseQuotationResponse:
    """Rejeita uma cotação."""
    repo = PurchaseQuotationRepository(session)
    quotation = await repo.get_by_id(quotation_id)
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotação não encontrada",
        )
    try:
        quotation.reject(data.reason)
        await session.commit()
        await session.refresh(quotation)
        return PurchaseQuotationResponse.model_validate(quotation)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ==================== Purchase Orders ====================


@router.post(
    "/orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar ordem de compra",
)
async def create_order(
    data: PurchaseOrderCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Cria uma nova ordem de compra."""
    try:
        repo = PurchaseOrderRepository(session)
        order = await repo.create(data, _current_user.id)
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except Exception as e:
        logger.error(f"Erro ao criar ordem: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar ordem de compra",
        )


@router.get(
    "/orders",
    response_model=PurchaseOrderListResponse,
    summary="Listar ordens de compra",
)
async def list_orders(  # pylint: disable=too-many-locals
    condominio_id: UUID | None = Query(None),
    status_filter: list[str] | None = Query(None, alias="status"),
    priority: list[str] | None = Query(None),
    supplier_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    delivery_from: date | None = Query(None),
    delivery_to: date | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderListResponse:
    """Lista ordens de compra com filtros."""
    filters = OrderFilter(
        status=[OrderStatus(s) for s in status_filter] if status_filter else None,
        priority=[OrderPriority(p) for p in priority] if priority else None,
        supplier_id=supplier_id,
        date_from=date_from,
        date_to=date_to,
        delivery_from=delivery_from,
        delivery_to=delivery_to,
        search=search,
    )
    repo = PurchaseOrderRepository(session)
    orders = await repo.list(condominio_id, filters, skip, limit)
    total = await repo.count(condominio_id, filters)
    return PurchaseOrderListResponse(
        items=[PurchaseOrderResponse.model_validate(o) for o in orders],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/orders/stats",
    response_model=OrderStats,
    summary="Estatísticas de ordens",
)
async def get_order_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> OrderStats:
    """Retorna estatísticas de ordens de compra."""
    repo = PurchaseOrderRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/orders/{order_id}",
    response_model=PurchaseOrderResponse,
    summary="Buscar ordem",
)
async def get_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Busca ordem de compra por ID."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    return PurchaseOrderResponse.model_validate(order)


@router.put(
    "/orders/{order_id}",
    response_model=PurchaseOrderResponse,
    summary="Atualizar ordem",
)
async def update_order(
    order_id: UUID,
    data: PurchaseOrderUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Atualiza uma ordem de compra."""
    try:
        repo = PurchaseOrderRepository(session)
        order = await repo.get_by_id(order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ordem de compra não encontrada",
            )
        order = await repo.update(order, data)
        await session.commit()
        return PurchaseOrderResponse.model_validate(order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar ordem: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar ordem",
        )


@router.post(
    "/orders/{order_id}/approve", response_model=PurchaseOrderResponse, summary="Aprovar ordem", status_code=201
)
async def approve_order(  # pylint: disable=unused-argument
    order_id: UUID,
    data: OrderApproveRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Aprova uma ordem de compra."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    try:
        order.approve(_current_user.id)
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/orders/{order_id}/reject", response_model=PurchaseOrderResponse, summary="Rejeitar ordem", status_code=201
)
async def reject_order(
    order_id: UUID,
    data: OrderRejectRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Rejeita uma ordem de compra."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    try:
        order.reject(data.reason)
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/orders/{order_id}/send",
    response_model=PurchaseOrderResponse,
    summary="Enviar ordem para fornecedor",
    status_code=201,
)
async def send_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Marca ordem como enviada para fornecedor."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    try:
        order.send_to_supplier()
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/orders/{order_id}/confirm",
    response_model=PurchaseOrderResponse,
    summary="Confirmar ordem pelo fornecedor",
    status_code=201,
)
async def confirm_order(
    order_id: UUID,
    notes: str | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Confirma ordem pelo fornecedor."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    try:
        order.confirm_by_supplier(notes)
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/orders/{order_id}/cancel", response_model=PurchaseOrderResponse, summary="Cancelar ordem", status_code=201
)
async def cancel_order(
    order_id: UUID,
    data: OrderCancelRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseOrderResponse:
    """Cancela uma ordem de compra."""
    repo = PurchaseOrderRepository(session)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de compra não encontrada",
        )
    try:
        order.cancel(data.reason)
        await session.commit()
        await session.refresh(order)
        return PurchaseOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ==================== Goods Receipts ====================


@router.post(
    "/receipts",
    response_model=GoodsReceiptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar recebimento",
)
async def create_receipt(
    data: GoodsReceiptCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Cria um novo recebimento de mercadorias."""
    try:
        repo = GoodsReceiptRepository(session)
        receipt = await repo.create(data, _current_user.id)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except Exception as e:
        logger.error(f"Erro ao criar recebimento: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar recebimento",
        )


@router.get(
    "/receipts",
    response_model=GoodsReceiptListResponse,
    summary="Listar recebimentos",
)
async def list_receipts(  # pylint: disable=too-many-locals
    condominio_id: UUID,
    status_filter: list[str] | None = Query(None, alias="status"),
    receipt_type: list[str] | None = Query(None),
    order_id: UUID | None = Query(None),
    supplier_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    has_divergence: bool | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptListResponse:
    """Lista recebimentos com filtros."""
    filters = ReceiptFilter(
        status=[ReceiptStatus(s) for s in status_filter] if status_filter else None,
        receipt_type=[ReceiptType(t) for t in receipt_type] if receipt_type else None,
        order_id=order_id,
        supplier_id=supplier_id,
        date_from=date_from,
        date_to=date_to,
        has_divergence=has_divergence,
        search=search,
    )
    repo = GoodsReceiptRepository(session)
    receipts = await repo.list(condominio_id, filters, skip, limit)
    total = await repo.count(condominio_id, filters)
    return GoodsReceiptListResponse(
        items=[GoodsReceiptResponse.model_validate(r) for r in receipts],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/receipts/by-order/{order_id}",
    response_model=list[GoodsReceiptResponse],
    summary="Listar recebimentos de uma ordem",
)
async def list_receipts_by_order(
    order_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> list[GoodsReceiptResponse]:
    """Lista recebimentos de uma ordem de compra."""
    repo = GoodsReceiptRepository(session)
    receipts = await repo.list_by_order(order_id)
    return [GoodsReceiptResponse.model_validate(r) for r in receipts]


@router.get(
    "/receipts/stats",
    response_model=ReceiptStats,
    summary="Estatísticas de recebimentos",
)
async def get_receipt_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ReceiptStats:
    """Retorna estatísticas de recebimentos."""
    repo = GoodsReceiptRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/receipts/{receipt_id}",
    response_model=GoodsReceiptResponse,
    summary="Buscar recebimento",
)
async def get_receipt(
    receipt_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Busca recebimento por ID."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    return GoodsReceiptResponse.model_validate(receipt)


@router.put(
    "/receipts/{receipt_id}",
    response_model=GoodsReceiptResponse,
    summary="Atualizar recebimento",
)
async def update_receipt(
    receipt_id: UUID,
    data: GoodsReceiptUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Atualiza um recebimento."""
    try:
        repo = GoodsReceiptRepository(session)
        receipt = await repo.get_by_id(receipt_id)
        if not receipt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recebimento não encontrado",
            )
        receipt = await repo.update(receipt, data)
        await session.commit()
        return GoodsReceiptResponse.model_validate(receipt)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar recebimento: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar recebimento",
        )


@router.post(
    "/receipts/{receipt_id}/inspect", response_model=GoodsReceiptResponse, summary="Realizar inspeção", status_code=201
)
async def inspect_receipt(
    receipt_id: UUID,
    data: ReceiptInspectionRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Realiza inspeção do recebimento."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    try:
        receipt.complete_inspection(data.result, _current_user.id, data.notes)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/receipts/{receipt_id}/approve",
    response_model=GoodsReceiptResponse,
    summary="Aprovar recebimento",
    status_code=201,
)
async def approve_receipt(
    receipt_id: UUID,
    _data: ReceiptApproveRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Aprova o recebimento."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    try:
        receipt.approve(_current_user.id)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/receipts/{receipt_id}/reject",
    response_model=GoodsReceiptResponse,
    summary="Rejeitar recebimento",
    status_code=201,
)
async def reject_receipt(
    receipt_id: UUID,
    data: ReceiptRejectRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Rejeita o recebimento."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    try:
        receipt.reject(data.reason)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/receipts/{receipt_id}/divergence",
    response_model=GoodsReceiptResponse,
    summary="Registrar divergência",
    status_code=201,
)
async def register_divergence(
    receipt_id: UUID,
    data: ReceiptDivergenceRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Registra divergência no recebimento."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    try:
        receipt.register_divergence(data.divergence_type, data.description, data.action)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/receipts/{receipt_id}/sign", response_model=GoodsReceiptResponse, summary="Assinar recebimento", status_code=201
)
async def sign_receipt(
    receipt_id: UUID,
    data: ReceiptSignRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> GoodsReceiptResponse:
    """Assina o recebimento."""
    repo = GoodsReceiptRepository(session)
    receipt = await repo.get_by_id(receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recebimento não encontrado",
        )
    try:
        receipt.sign(data.receiver_name, data.receiver_document)
        await session.commit()
        await session.refresh(receipt)
        return GoodsReceiptResponse.model_validate(receipt)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ==================== Purchase Approvals ====================


@router.get(
    "/approvals/my",
    response_model=MyApprovalsResponse,
    summary="Minhas aprovações pendentes",
)
async def get_my_approvals(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> MyApprovalsResponse:
    """Retorna aprovações pendentes do usuário atual."""
    repo = PurchaseApprovalRepository(session)
    pending = await repo.get_pending_for_approver(_current_user.id, condominio_id)

    # Separar em pendentes normais e atrasadas
    now = datetime.utcnow()
    overdue = [a for a in pending if a.deadline and a.deadline < now]
    normal_pending = [a for a in pending if not a.deadline or a.deadline >= now]

    # Buscar aprovações recentes (últimas 10 respondidas)
    recent_filter = ApprovalFilter(
        approver_id=_current_user.id,
        status=[ApprovalStatus.APROVADO, ApprovalStatus.REJEITADO],
    )
    recent = await repo.list(condominio_id, recent_filter, 0, 10)

    return MyApprovalsResponse(
        pending=[PurchaseApprovalResponse.model_validate(a) for a in normal_pending],
        recent=[PurchaseApprovalResponse.model_validate(a) for a in recent],
        overdue=[PurchaseApprovalResponse.model_validate(a) for a in overdue],
        total_pending=len(pending),
        total_overdue=len(overdue),
    )


@router.get(
    "/approvals",
    response_model=PurchaseApprovalListResponse,
    summary="Listar aprovações",
)
async def list_approvals(
    condominio_id: UUID,
    status_filter: list[str] | None = Query(None, alias="status"),
    approval_type: list[str] | None = Query(None),
    approval_level: list[str] | None = Query(None),
    approver_id: UUID | None = Query(None),
    document_id: UUID | None = Query(None),
    is_overdue: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalListResponse:
    """Lista aprovações com filtros."""
    filters = ApprovalFilter(
        status=[ApprovalStatus(s) for s in status_filter] if status_filter else None,
        approval_type=[ApprovalType(t) for t in approval_type] if approval_type else None,
        approval_level=[ApprovalLevel(level) for level in approval_level] if approval_level else None,
        approver_id=approver_id,
        document_id=document_id,
        is_overdue=is_overdue,
    )
    repo = PurchaseApprovalRepository(session)
    approvals = await repo.list(condominio_id, filters, skip, limit)
    total = await repo.count(condominio_id, filters)
    return PurchaseApprovalListResponse(
        items=[PurchaseApprovalResponse.model_validate(a) for a in approvals],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
    )


@router.get(
    "/approvals/stats",
    response_model=ApprovalStats,
    summary="Estatísticas de aprovações",
)
async def get_approval_stats(
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> ApprovalStats:
    """Retorna estatísticas de aprovações."""
    repo = PurchaseApprovalRepository(session)
    return await repo.get_stats(condominio_id)


@router.get(
    "/approvals/{approval_id}",
    response_model=PurchaseApprovalResponse,
    summary="Buscar aprovação",
)
async def get_approval(
    approval_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Busca aprovação por ID."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    return PurchaseApprovalResponse.model_validate(approval)


@router.post(
    "/approvals/{approval_id}/approve", response_model=PurchaseApprovalResponse, summary="Aprovar", status_code=201
)
async def approve_approval(
    approval_id: UUID,
    data: ApprovalApproveRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Aprova uma solicitação."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    if str(approval.approver_id) != _current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é o aprovador desta solicitação",
        )
    try:
        comments = data.comments if data else None
        approval.approve(comments)
        await session.commit()
        await session.refresh(approval)
        return PurchaseApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/approvals/{approval_id}/reject", response_model=PurchaseApprovalResponse, summary="Rejeitar", status_code=201
)
async def reject_approval(
    approval_id: UUID,
    data: ApprovalRejectRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Rejeita uma solicitação."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    if str(approval.approver_id) != _current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é o aprovador desta solicitação",
        )
    try:
        approval.reject(data.reason)
        await session.commit()
        await session.refresh(approval)
        return PurchaseApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/approvals/{approval_id}/delegate",
    response_model=PurchaseApprovalResponse,
    summary="Delegar aprovação",
    status_code=201,
)
async def delegate_approval(
    approval_id: UUID,
    data: ApprovalDelegateRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Delega aprovação para outro usuário."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    if str(approval.approver_id) != _current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é o aprovador desta solicitação",
        )
    try:
        approval.delegate(data.new_approver_id, _current_user.id, data.reason)
        await session.commit()
        await session.refresh(approval)
        return PurchaseApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/approvals/{approval_id}/request-info",
    response_model=PurchaseApprovalResponse,
    summary="Solicitar informações",
    status_code=201,
)
async def request_info(
    approval_id: UUID,
    data: ApprovalInfoRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Solicita informações adicionais."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    if str(approval.approver_id) != _current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é o aprovador desta solicitação",
        )
    try:
        approval.request_info(data.info_request)
        await session.commit()
        await session.refresh(approval)
        return PurchaseApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/approvals/{approval_id}/provide-info",
    response_model=PurchaseApprovalResponse,
    summary="Fornecer informações",
    status_code=201,
)
async def provide_info(
    approval_id: UUID,
    data: ApprovalInfoProvideRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> PurchaseApprovalResponse:
    """Fornece informações solicitadas."""
    repo = PurchaseApprovalRepository(session)
    approval = await repo.get_by_id(approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aprovação não encontrada",
        )
    try:
        approval.provide_info(data.info)
        await session.commit()
        await session.refresh(approval)
        return PurchaseApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ==================== AI Services ====================


@router.post("/ai/suggest-suppliers", summary="Sugerir fornecedores", status_code=201)
async def suggest_suppliers(
    condominio_id: UUID,
    product_description: str = Query(..., min_length=3),
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Sugere fornecedores para um produto usando IA."""
    ai_service = PurchaseAIService(session)  # pylint: disable=too-many-function-args
    suggestions = await ai_service.suggest_suppliers(condominio_id, product_description, limit)  # pylint: disable=no-value-for-parameter
    return suggestions


@router.get(
    "/ai/supplier-analysis/{supplier_id}",
    summary="Analisar fornecedor",
)
async def analyze_supplier(
    supplier_id: UUID,
    condominio_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Analisa performance de um fornecedor usando IA."""
    order_repo = PurchaseOrderRepository(session)
    orders = await order_repo.list(
        condominio_id,
        OrderFilter(supplier_id=supplier_id),
        skip=0,
        limit=200,
    )
    orders_data = [
        {
            "expected_delivery_date": o.expected_delivery_date,
            "actual_delivery_date": o.actual_delivery_date,
            "items": [
                {"unit_price": item.unit_price, "product_id": item.product_id}
                for item in (o.items or [])
            ],
        }
        for o in orders
    ]
    ai_service = PurchaseAIService()
    analysis = ai_service.analyze_supplier_performance(supplier_id, orders_data, [])
    return analysis


@router.post("/ai/predict-demand", summary="Prever demanda", status_code=201)
async def predict_demand(
    product_id: UUID,
    months_ahead: int = Query(3, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Prevê demanda futura de um produto usando IA."""
    ai_service = PurchaseAIService(session)  # pylint: disable=too-many-function-args
    prediction = await ai_service.predict_demand(product_id, months_ahead)  # pylint: disable=no-value-for-parameter
    return prediction


@router.get(
    "/ai/reorder-point/{product_id}",
    summary="Calcular ponto de reposição",
)
async def calculate_reorder_point(
    product_id: UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
):
    """Calcula ponto de reposição de um produto usando IA."""
    product = await ProductRepository(session).get_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado",
        )
    lead_time_days = product.lead_time_days or 7
    # Estima consumo médio diário a partir do estoque mínimo (cobertura ~30 dias)
    min_stock = Decimal(str(product.min_stock or 0))
    average_daily_consumption = (min_stock / Decimal("30")) if min_stock > 0 else Decimal("1")
    ai_service = PurchaseAIService()
    reorder = ai_service.calculate_reorder_point(average_daily_consumption, lead_time_days)
    reorder["product_id"] = str(product_id)
    return reorder
