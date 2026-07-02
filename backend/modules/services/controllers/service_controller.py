"""
ServiceController - REST API Endpoints
Sprint 31: Gestão de Serviços
"""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database import get_db
from core.database.session import get_sync_db_dependency
from modules.services.models import OrderPriority, OrderStatus, ReportType, ServiceCategory, ServiceStatus, ServiceType
from modules.services.repositories import ServiceRepository
from modules.services.schemas import (
    ServiceAnalysis,
    ServiceCatalogCreate,
    ServiceCatalogListResponse,
    ServiceCatalogResponse,
    ServiceCatalogStats,
    ServiceCatalogUpdate,
    ServiceExecutionCreate,
    ServiceExecutionResponse,
    ServiceOrderCreate,
    ServiceOrderListResponse,
    ServiceOrderResponse,
    ServiceOrderStats,
    ServiceOrderUpdate,
    ServiceRecommendation,
    ServiceReportCreate,
    ServiceReportResponse,
    ServiceReportUpdate,
    SLAAnalysis,
    SLAConfigCreate,
    SLAConfigResponse,
    SLAConfigUpdate,
)
from modules.services.services import ServiceAIService, ServiceManagementService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["Services"])


def get_management_service(db: Session = Depends(get_sync_db_dependency)) -> ServiceManagementService:
    """Dependency para ServiceManagementService."""
    return ServiceManagementService(db)


def get_ai_service(db: Session = Depends(get_sync_db_dependency)) -> ServiceAIService:
    """Dependency para ServiceAIService."""
    return ServiceAIService(db)


def get_repository(db: Session = Depends(get_sync_db_dependency)) -> ServiceRepository:
    """Dependency para ServiceRepository."""
    return ServiceRepository(db)


# ============================================================
# SERVICE CATALOG ENDPOINTS
# ============================================================


@router.get("/catalog", response_model=list[ServiceCatalogListResponse], summary="Listar Serviços")
async def list_services(
    category: ServiceCategory | None = None,
    service_type: ServiceType | None = None,
    service_status: ServiceStatus | None = None,
    is_available: bool | None = None,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: ServiceRepository = Depends(get_repository),
) -> list[ServiceCatalogListResponse]:
    """Lista serviços do catálogo com filtros."""
    services, _total = repo.list_services(
        skip=skip,
        limit=limit,
        category=category.value if category else None,
        service_type=service_type.value if service_type else None,
        status=service_status.value if service_status else None,
        search=search,
    )
    # is_available e uma propriedade derivada do modelo (nao ha coluna filtravel);
    # aplica o filtro em memoria sobre o resultado real do banco.
    if is_available is not None:
        services = [s for s in services if s.is_available == is_available]
    return [ServiceCatalogListResponse.model_validate(s) for s in services]


@router.get("/catalog/stats", response_model=ServiceCatalogStats, summary="Estatísticas do Catálogo")
async def get_catalog_stats(repo: ServiceRepository = Depends(get_repository)) -> ServiceCatalogStats:
    """Retorna estatísticas do catálogo de serviços."""
    return repo.get_service_catalog_stats()


@router.get("/catalog/{service_id}", response_model=ServiceCatalogResponse, summary="Obter Serviço")
async def get_service(service_id: UUID, repo: ServiceRepository = Depends(get_repository)) -> ServiceCatalogResponse:
    """Obtém detalhes de um serviço."""
    service = repo.get_service_catalog_by_id(service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return ServiceCatalogResponse.model_validate(service)


@router.post(
    "/catalog", response_model=ServiceCatalogResponse, status_code=status.HTTP_201_CREATED, summary="Criar Serviço"
)
async def create_service(
    data: ServiceCatalogCreate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceCatalogResponse:
    """Cria um novo serviço no catálogo."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    service = svc.create_service(data, user_id)
    return ServiceCatalogResponse.model_validate(service)


@router.put("/catalog/{service_id}", response_model=ServiceCatalogResponse, summary="Atualizar Serviço")
async def update_service(
    service_id: UUID,
    data: ServiceCatalogUpdate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceCatalogResponse:
    """Atualiza um serviço existente."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    service = svc.update_service(service_id, data, user_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return ServiceCatalogResponse.model_validate(service)


@router.post("/catalog/{service_id}/activate", response_model=ServiceCatalogResponse, summary="Ativar Serviço")
async def activate_service(
    service_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceCatalogResponse:
    """Ativa um serviço."""
    service = svc.activate_service(service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return ServiceCatalogResponse.model_validate(service)


@router.post("/catalog/{service_id}/deactivate", response_model=ServiceCatalogResponse, summary="Desativar Serviço")
async def deactivate_service(
    service_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceCatalogResponse:
    """Desativa um serviço."""
    service = svc.deactivate_service(service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return ServiceCatalogResponse.model_validate(service)


@router.post("/catalog/{service_id}/discontinue", response_model=ServiceCatalogResponse, summary="Descontinuar Serviço")
async def discontinue_service(
    service_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceCatalogResponse:
    """Descontinua um serviço."""
    service = svc.discontinue_service(service_id)
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return ServiceCatalogResponse.model_validate(service)


@router.get("/catalog/{service_id}/price", summary="Calcular Preço")
async def calculate_service_price(
    service_id: UUID,
    quantity: float = Query(1.0, ge=0),
    is_emergency: bool = Query(False),
    svc: ServiceManagementService = Depends(get_management_service),
) -> dict:
    """Calcula preço de um serviço."""
    price = svc.calculate_service_price(service_id, quantity, is_emergency)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return {
        "service_id": str(service_id),
        "quantity": quantity,
        "is_emergency": is_emergency,
        "calculated_price": float(price),
    }


# ============================================================
# SERVICE ORDER ENDPOINTS
# ============================================================


@router.get("/orders", response_model=list[ServiceOrderListResponse], summary="Listar Ordens")
async def list_orders(
    order_status: OrderStatus | None = Query(None, alias="status"),
    priority: OrderPriority | None = None,
    client_id: UUID | None = None,
    service_id: UUID | None = None,
    technician_id: UUID | None = None,
    scheduled_date_from: date | None = None,
    scheduled_date_to: date | None = None,
    is_overdue: bool | None = None,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: ServiceRepository = Depends(get_repository),
) -> list[ServiceOrderListResponse]:
    """Lista ordens de serviço com filtros."""
    orders = repo.list_service_orders(
        status=order_status,
        priority=priority,
        client_id=client_id,
        service_id=service_id,
        technician_id=technician_id,
        scheduled_date_from=scheduled_date_from,
        scheduled_date_to=scheduled_date_to,
        is_overdue=is_overdue,
        search=search,
        skip=skip,
        limit=limit,
    )
    return [ServiceOrderListResponse.model_validate(o) for o in orders]


@router.get("/orders/stats", response_model=ServiceOrderStats, summary="Estatísticas de Ordens")
async def get_order_stats(
    client_id: UUID | None = None, service_id: UUID | None = None, ai_svc: ServiceAIService = Depends(get_ai_service)
) -> ServiceOrderStats:
    """Retorna estatísticas de ordens."""
    return ai_svc.get_order_stats(client_id, service_id)


@router.get("/orders/overdue", response_model=list[ServiceOrderListResponse], summary="Ordens em Atraso")
async def get_overdue_orders(
    svc: ServiceManagementService = Depends(get_management_service),
) -> list[ServiceOrderListResponse]:
    """Lista ordens em atraso."""
    orders = svc.get_overdue_orders()
    return [ServiceOrderListResponse.model_validate(o) for o in orders]


@router.get("/orders/at-risk", summary="Ordens em Risco")
async def get_at_risk_orders(
    threshold_hours: int = Query(4, ge=1, le=24), svc: ServiceManagementService = Depends(get_management_service)
) -> list:
    """Lista ordens em risco de atraso."""
    at_risk = svc.get_orders_at_risk(threshold_hours)
    return [
        {"order_id": str(o.id), "order_number": o.order_number, "title": o.title, "minutes_remaining": mins}
        for o, mins in at_risk
    ]


@router.get("/orders/{order_id}", response_model=ServiceOrderResponse, summary="Obter Ordem")
async def get_order(order_id: UUID, repo: ServiceRepository = Depends(get_repository)) -> ServiceOrderResponse:
    """Obtém detalhes de uma ordem."""
    order = repo.get_service_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED, summary="Criar Ordem")
async def create_order(
    data: ServiceOrderCreate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceOrderResponse:
    """Cria uma nova ordem de serviço."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    try:
        order = svc.create_order(data, user_id)
        return ServiceOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.put("/orders/{order_id}", response_model=ServiceOrderResponse, summary="Atualizar Ordem")
async def update_order(
    order_id: UUID,
    data: ServiceOrderUpdate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceOrderResponse:
    """Atualiza uma ordem de serviço."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    try:
        order = svc.update_order(order_id, data, user_id)
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
        return ServiceOrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/orders/{order_id}/submit", response_model=ServiceOrderResponse, summary="Submeter Ordem")
async def submit_order(
    order_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceOrderResponse:
    """Submete ordem para aprovação."""
    order = svc.submit_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/approve", response_model=ServiceOrderResponse, summary="Aprovar Ordem")
async def approve_order(
    order_id: UUID,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceOrderResponse:
    """Aprova uma ordem de serviço."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    order = svc.approve_order(order_id, user_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/reject", response_model=ServiceOrderResponse, summary="Rejeitar Ordem")
async def reject_order(
    order_id: UUID,
    reason: str = Query(..., min_length=1),
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceOrderResponse:
    """Rejeita uma ordem de serviço."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    order = svc.reject_order(order_id, reason, user_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/schedule", response_model=ServiceOrderResponse, summary="Agendar Ordem")
async def schedule_order(
    order_id: UUID,
    scheduled_date: date,
    time_start: str | None = Query(None, pattern=r"^\d{2}:\d{2}$"),
    time_end: str | None = Query(None, pattern=r"^\d{2}:\d{2}$"),
    technician_id: UUID | None = None,
    technician_name: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceOrderResponse:
    """Agenda uma ordem de serviço."""
    order = svc.schedule_order(order_id, scheduled_date, time_start, time_end, technician_id, technician_name)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/start", response_model=ServiceOrderResponse, summary="Iniciar Ordem")
async def start_order(
    order_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceOrderResponse:
    """Inicia uma ordem de serviço."""
    order = svc.start_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/pause", response_model=ServiceOrderResponse, summary="Pausar Ordem")
async def pause_order(
    order_id: UUID,
    reason: str = Query(..., min_length=1),
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceOrderResponse:
    """Pausa uma ordem de serviço."""
    order = svc.pause_order(order_id, reason)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/resume", response_model=ServiceOrderResponse, summary="Retomar Ordem")
async def resume_order(
    order_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceOrderResponse:
    """Retoma uma ordem pausada."""
    order = svc.resume_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/complete", response_model=ServiceOrderResponse, summary="Concluir Ordem")
async def complete_order(
    order_id: UUID,
    final_value: Decimal | None = None,
    completion_notes: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceOrderResponse:
    """Conclui uma ordem de serviço."""
    order = svc.complete_order(order_id, final_value, completion_notes)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/cancel", response_model=ServiceOrderResponse, summary="Cancelar Ordem")
async def cancel_order(
    order_id: UUID,
    reason: str = Query(..., min_length=1),
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceOrderResponse:
    """Cancela uma ordem de serviço."""
    order = svc.cancel_order(order_id, reason)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


@router.post("/orders/{order_id}/rate", response_model=ServiceOrderResponse, summary="Avaliar Ordem")
async def rate_order(
    order_id: UUID,
    rating: int = Query(..., ge=1, le=5),
    feedback: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceOrderResponse:
    """Avalia uma ordem de serviço."""
    order = svc.rate_order(order_id, rating, feedback)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada")
    return ServiceOrderResponse.model_validate(order)


# ============================================================
# SERVICE EXECUTION ENDPOINTS
# ============================================================


@router.get("/executions", response_model=list[ServiceExecutionResponse], summary="Listar Execuções")
async def list_executions(
    order_id: UUID | None = None,
    technician_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: ServiceRepository = Depends(get_repository),
) -> list[ServiceExecutionResponse]:
    """Lista execuções de serviço."""
    executions = repo.list_service_executions(order_id=order_id, technician_id=technician_id, skip=skip, limit=limit)
    return [ServiceExecutionResponse.model_validate(e) for e in executions]


@router.get("/executions/{execution_id}", response_model=ServiceExecutionResponse, summary="Obter Execução")
async def get_execution(
    execution_id: UUID, repo: ServiceRepository = Depends(get_repository)
) -> ServiceExecutionResponse:
    """Obtém detalhes de uma execução."""
    execution = repo.get_service_execution_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post(
    "/executions",
    response_model=ServiceExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Execução",
)
async def create_execution(
    data: ServiceExecutionCreate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceExecutionResponse:
    """Cria uma nova execução de serviço."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    try:
        execution = svc.create_execution(data, user_id)
        return ServiceExecutionResponse.model_validate(execution)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/executions/{execution_id}/start-travel", response_model=ServiceExecutionResponse, summary="Iniciar Deslocamento"
)
async def start_travel(
    execution_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceExecutionResponse:
    """Inicia deslocamento para execução."""
    execution = svc.start_travel(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/arrive", response_model=ServiceExecutionResponse, summary="Registrar Chegada")
async def arrive_at_location(
    execution_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceExecutionResponse:
    """Registra chegada no local."""
    execution = svc.arrive_at_location(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/start", response_model=ServiceExecutionResponse, summary="Iniciar Execução")
async def start_execution(
    execution_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceExecutionResponse:
    """Inicia execução do serviço."""
    execution = svc.start_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/pause", response_model=ServiceExecutionResponse, summary="Pausar Execução")
async def pause_execution(
    execution_id: UUID,
    reason: str = Query(..., min_length=1),
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceExecutionResponse:
    """Pausa a execução."""
    execution = svc.pause_execution(execution_id, reason)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/resume", response_model=ServiceExecutionResponse, summary="Retomar Execução")
async def resume_execution(
    execution_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceExecutionResponse:
    """Retoma a execução."""
    execution = svc.resume_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post("/executions/{execution_id}/finish", response_model=ServiceExecutionResponse, summary="Finalizar Execução")
async def finish_execution(
    execution_id: UUID,
    work_description: str | None = None,
    findings: str | None = None,
    recommendations: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceExecutionResponse:
    """Finaliza a execução."""
    execution = svc.finish_execution(execution_id, work_description, findings, recommendations)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post(
    "/executions/{execution_id}/materials",
    response_model=ServiceExecutionResponse,
    summary="Adicionar Material",
    status_code=201,
)
async def add_material(
    execution_id: UUID,
    material_name: str,
    quantity: float = Query(..., gt=0),
    unit_price: Decimal = Query(..., ge=0),
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceExecutionResponse:
    """Adiciona material à execução."""
    execution = svc.add_material_to_execution(execution_id, material_name, quantity, unit_price)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post(
    "/executions/{execution_id}/checklist/{item_index}",
    response_model=ServiceExecutionResponse,
    summary="Atualizar Checklist",
)
async def update_checklist(
    execution_id: UUID,
    item_index: int,
    completed: bool,
    notes: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceExecutionResponse:
    """Atualiza item do checklist."""
    execution = svc.update_checklist_item(execution_id, item_index, completed, notes)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


@router.post(
    "/executions/{execution_id}/signatures",
    response_model=ServiceExecutionResponse,
    summary="Adicionar Assinatura",
    status_code=201,
)
async def add_signature(
    execution_id: UUID,
    signer_name: str,
    signature_data: str,
    signer_role: str,
    svc: ServiceManagementService = Depends(get_management_service),
) -> ServiceExecutionResponse:
    """Adiciona assinatura à execução."""
    execution = svc.add_signature(execution_id, signer_name, signature_data, signer_role)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    return ServiceExecutionResponse.model_validate(execution)


# ============================================================
# SERVICE REPORT ENDPOINTS
# ============================================================


@router.get("/reports", response_model=list[ServiceReportResponse], summary="Listar Relatórios")
async def list_reports(
    order_id: UUID | None = None,
    report_type: ReportType | None = None,
    is_approved: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: ServiceRepository = Depends(get_repository),
) -> list[ServiceReportResponse]:
    """Lista relatórios de serviço."""
    reports = repo.list_service_reports(
        order_id=order_id, report_type=report_type, is_approved=is_approved, skip=skip, limit=limit
    )
    return [ServiceReportResponse.model_validate(r) for r in reports]


@router.get("/reports/{report_id}", response_model=ServiceReportResponse, summary="Obter Relatório")
async def get_report(report_id: UUID, repo: ServiceRepository = Depends(get_repository)) -> ServiceReportResponse:
    """Obtém detalhes de um relatório."""
    report = repo.get_service_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
    return ServiceReportResponse.model_validate(report)


@router.post(
    "/reports", response_model=ServiceReportResponse, status_code=status.HTTP_201_CREATED, summary="Criar Relatório"
)
async def create_report(
    data: ServiceReportCreate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceReportResponse:
    """Cria um novo relatório."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    try:
        report = svc.create_report(data, user_id)
        return ServiceReportResponse.model_validate(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.put("/reports/{report_id}", response_model=ServiceReportResponse, summary="Atualizar Relatório")
async def update_report(
    report_id: UUID,
    data: ServiceReportUpdate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceReportResponse:
    """Atualiza um relatório."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    try:
        report = svc.update_report(report_id, data, user_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
        return ServiceReportResponse.model_validate(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/reports/{report_id}/finalize", response_model=ServiceReportResponse, summary="Finalizar Relatório")
async def finalize_report(
    report_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceReportResponse:
    """Finaliza um relatório."""
    report = svc.finalize_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
    return ServiceReportResponse.model_validate(report)


@router.post("/reports/{report_id}/review", response_model=ServiceReportResponse, summary="Revisar Relatório")
async def review_report(
    report_id: UUID,
    reviewer_name: str,
    review_notes: str | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceReportResponse:
    """Revisa um relatório."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    report = svc.review_report(report_id, user_id, reviewer_name, review_notes)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
    return ServiceReportResponse.model_validate(report)


@router.post("/reports/{report_id}/approve", response_model=ServiceReportResponse, summary="Aprovar Relatório")
async def approve_report(
    report_id: UUID,
    approver_name: str,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> ServiceReportResponse:
    """Aprova um relatório."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    report = svc.approve_report(report_id, user_id, approver_name)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
    return ServiceReportResponse.model_validate(report)


@router.post("/reports/{report_id}/send", response_model=ServiceReportResponse, summary="Enviar Relatório")
async def send_report(
    report_id: UUID, recipient: str, svc: ServiceManagementService = Depends(get_management_service)
) -> ServiceReportResponse:
    """Marca relatório como enviado."""
    report = svc.send_report(report_id, recipient)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado")
    return ServiceReportResponse.model_validate(report)


# ============================================================
# SLA CONFIG ENDPOINTS
# ============================================================


@router.get("/sla-configs", response_model=list[SLAConfigResponse], summary="Listar SLAs")
async def list_sla_configs(
    service_id: UUID | None = None,
    client_id: UUID | None = None,
    is_active: bool | None = None,
    is_default: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: ServiceRepository = Depends(get_repository),
) -> list[SLAConfigResponse]:
    """Lista configurações de SLA."""
    slas = repo.list_sla_configs(
        service_id=service_id, client_id=client_id, is_active=is_active, is_default=is_default, skip=skip, limit=limit
    )
    return [SLAConfigResponse.model_validate(s) for s in slas]


@router.get("/sla-configs/{sla_id}", response_model=SLAConfigResponse, summary="Obter SLA")
async def get_sla_config(sla_id: UUID, repo: ServiceRepository = Depends(get_repository)) -> SLAConfigResponse:
    """Obtém detalhes de um SLA."""
    sla = repo.get_sla_config_by_id(sla_id)
    if not sla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return SLAConfigResponse.model_validate(sla)


@router.post("/sla-configs", response_model=SLAConfigResponse, status_code=status.HTTP_201_CREATED, summary="Criar SLA")
async def create_sla_config(
    data: SLAConfigCreate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> SLAConfigResponse:
    """Cria uma nova configuração de SLA."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    sla = svc.create_sla_config(data, user_id)
    return SLAConfigResponse.model_validate(sla)


@router.put("/sla-configs/{sla_id}", response_model=SLAConfigResponse, summary="Atualizar SLA")
async def update_sla_config(
    sla_id: UUID,
    data: SLAConfigUpdate,
    svc: ServiceManagementService = Depends(get_management_service),
    current_user: dict = Depends(get_current_user),
) -> SLAConfigResponse:
    """Atualiza uma configuração de SLA."""
    user_id = UUID(current_user.get("sub")) if current_user.get("sub") else None
    sla = svc.update_sla_config(sla_id, data, user_id)
    if not sla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return SLAConfigResponse.model_validate(sla)


@router.post("/sla-configs/{sla_id}/activate", response_model=SLAConfigResponse, summary="Ativar SLA")
async def activate_sla(
    sla_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> SLAConfigResponse:
    """Ativa um SLA."""
    sla = svc.activate_sla(sla_id)
    if not sla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return SLAConfigResponse.model_validate(sla)


@router.post("/sla-configs/{sla_id}/deactivate", response_model=SLAConfigResponse, summary="Desativar SLA")
async def deactivate_sla(
    sla_id: UUID, svc: ServiceManagementService = Depends(get_management_service)
) -> SLAConfigResponse:
    """Desativa um SLA."""
    sla = svc.deactivate_sla(sla_id)
    if not sla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return SLAConfigResponse.model_validate(sla)


@router.post("/sla-configs/{sla_id}/set-default", response_model=SLAConfigResponse, summary="Definir SLA Padrão")
async def set_default_sla(
    sla_id: UUID, service_id: UUID | None = None, svc: ServiceManagementService = Depends(get_management_service)
) -> SLAConfigResponse:
    """Define SLA como padrão."""
    sla = svc.set_default_sla(sla_id, service_id)
    if not sla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return SLAConfigResponse.model_validate(sla)


@router.get("/sla-configs/{sla_id}/compliance-report", summary="Relatório de Compliance")
async def get_sla_compliance_report(
    sla_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    svc: ServiceManagementService = Depends(get_management_service),
) -> dict:
    """Gera relatório de compliance do SLA."""
    report = svc.get_sla_compliance_report(sla_id, start_date, end_date)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return report


# ============================================================
# AI/ANALYTICS ENDPOINTS
# ============================================================


@router.get("/analytics/service/{service_id}", response_model=ServiceAnalysis, summary="Análise de Serviço")
async def analyze_service(service_id: UUID, ai_svc: ServiceAIService = Depends(get_ai_service)) -> ServiceAnalysis:
    """Analisa performance de um serviço."""
    analysis = ai_svc.analyze_service(service_id)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return analysis


@router.get("/analytics/services", response_model=list[ServiceAnalysis], summary="Análise de Todos Serviços")
async def analyze_all_services(ai_svc: ServiceAIService = Depends(get_ai_service)) -> list[ServiceAnalysis]:
    """Analisa todos os serviços ativos."""
    return ai_svc.analyze_all_services()


@router.get(
    "/analytics/recommendations", response_model=list[ServiceRecommendation], summary="Recomendações de Serviços"
)
async def get_recommendations(
    client_id: UUID | None = None,
    category: ServiceCategory | None = None,
    limit: int = Query(10, ge=1, le=50),
    ai_svc: ServiceAIService = Depends(get_ai_service),
) -> list[ServiceRecommendation]:
    """Retorna recomendações de serviços."""
    return ai_svc.get_service_recommendations(client_id, category, limit)


@router.get("/analytics/demand/{service_id}", summary="Previsão de Demanda")
async def predict_demand(
    service_id: UUID, days_ahead: int = Query(30, ge=1, le=365), ai_svc: ServiceAIService = Depends(get_ai_service)
) -> dict:
    """Prevê demanda para um serviço."""
    prediction = ai_svc.predict_service_demand(service_id, days_ahead)
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Serviço não encontrado")
    return prediction


@router.get("/analytics/sla/{sla_id}", response_model=SLAAnalysis, summary="Análise de SLA")
async def analyze_sla(sla_id: UUID, ai_svc: ServiceAIService = Depends(get_ai_service)) -> SLAAnalysis:
    """Analisa compliance de um SLA."""
    analysis = ai_svc.analyze_sla(sla_id)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SLA não encontrado")
    return analysis


@router.get("/analytics/sla-dashboard", summary="Dashboard de SLAs")
async def get_sla_dashboard(ai_svc: ServiceAIService = Depends(get_ai_service)) -> dict:
    """Retorna dashboard de SLAs."""
    return ai_svc.get_sla_dashboard()


@router.get("/analytics/order-patterns", summary="Padrões de Ordens")
async def analyze_order_patterns(
    days: int = Query(30, ge=1, le=365), ai_svc: ServiceAIService = Depends(get_ai_service)
) -> dict:
    """Analisa padrões de ordens de serviço."""
    return ai_svc.analyze_order_patterns(days)


@router.get("/analytics/bottlenecks", summary="Gargalos Identificados")
async def identify_bottlenecks(ai_svc: ServiceAIService = Depends(get_ai_service)) -> list:
    """Identifica gargalos no processo."""
    return ai_svc.identify_bottlenecks()


@router.get("/analytics/dashboard", summary="Dashboard Executivo")
async def get_executive_dashboard(ai_svc: ServiceAIService = Depends(get_ai_service)) -> dict:
    """Retorna dashboard executivo."""
    return ai_svc.get_executive_dashboard()
