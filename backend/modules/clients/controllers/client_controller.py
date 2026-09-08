"""
Client Controller - REST API Endpoints
Sprint 30: Cadastro de Clientes/Condomínios
"""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_sync_db_dependency as get_db
from modules.clients.models.client import ClientSegment, ClientStatus, ClientType
from modules.clients.schemas.client_schemas import (
    ClientCreate,
    ClientFilter,
    ClientResponse,
    ClientUpdate,
    CondominiumCreate,
    CondominiumListResponse,
    CondominiumResponse,
    CondominiumUpdate,
)
from modules.clients.services.client_ai_service import ClientAIService
from modules.clients.services.client_service import ClientService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["Clients"])


def get_service(db: Session = Depends(get_db)) -> ClientService:
    """Dependency para obter ClientService."""
    return ClientService(db)


def get_ai_service(db: Session = Depends(get_db)) -> ClientAIService:
    """Dependency para obter ClientAIService."""
    return ClientAIService(db)


# =============================================================================
# CLIENT ENDPOINTS
# =============================================================================


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
# Alias com barra final: o frontend chama POST /api/v1/clients/ e o app roda com
# redirect_slashes=False — sem o alias vira 404 (bug do cadastro de cliente, 10/07).
@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_client(
    data: ClientCreate, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Cria um novo cliente."""
    try:
        client = service.create_client(data)
        return client
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("")
@router.get("/", include_in_schema=False)
async def list_clients(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    client_type: ClientType | None = Query(None, alias="type"),
    status_filter: ClientStatus | None = Query(None, alias="status"),
    segment: ClientSegment | None = None,
    is_defaulter: bool | None = None,
    is_vip: bool | None = None,
    plus_enabled: bool | None = None,
    city: str | None = None,
    state: str | None = None,
    search: str | None = None,
    order_by: str = Query("created_at"),
    order_desc: bool = Query(True),
    service: ClientService = Depends(get_service),
):
    """Lista clientes com filtros."""
    filters = ClientFilter(
        type=client_type,
        status=status_filter,
        segment=segment,
        is_defaulter=is_defaulter,
        is_vip=is_vip,
        plus_enabled=plus_enabled,
        city=city,
        state=state,
        search=search,
    )
    clients, _ = service.list_clients(filters, skip, limit, order_by, order_desc)
    return clients


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Obtém um cliente por ID."""
    client = service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.get("/{client_id}/full", response_model=ClientResponse)
async def get_client_full(
    client_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Obtém um cliente com todas as relações."""
    client = service.get_client_full(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    current_user: CurrentActiveUser, client_id: UUID, data: ClientUpdate, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Atualiza um cliente."""
    client = service.update_client(client_id, data)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> None:
    """Remove um cliente."""
    if not service.delete_client(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")


@router.post("/{client_id}/activate", response_model=ClientResponse)
async def activate_client(
    client_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Ativa um cliente."""
    client = service.activate_client(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.post("/{client_id}/suspend", response_model=ClientResponse)
async def suspend_client(
    current_user: CurrentActiveUser,
    client_id: UUID,
    reason: str | None = None,
    service: ClientService = Depends(get_service),
) -> ClientResponse:
    """Suspende um cliente."""
    client = service.suspend_client(client_id, reason)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.post("/{client_id}/block", response_model=ClientResponse)
async def block_client(
    current_user: CurrentActiveUser,
    client_id: UUID,
    reason: str | None = None,
    service: ClientService = Depends(get_service),
) -> ClientResponse:
    """Bloqueia um cliente."""
    client = service.block_client(client_id, reason)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.post("/{client_id}/set-defaulter", response_model=ClientResponse)
async def set_defaulter(
    current_user: CurrentActiveUser,
    client_id: UUID,
    debt_amount: Decimal = Query(..., gt=0),
    service: ClientService = Depends(get_service),
) -> ClientResponse:
    """Marca cliente como inadimplente."""
    client = service.set_defaulter(client_id, debt_amount)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


@router.post("/{client_id}/clear-defaulter", response_model=ClientResponse)
async def clear_defaulter(
    client_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> ClientResponse:
    """Remove status de inadimplente."""
    client = service.clear_defaulter(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client


# =============================================================================
# CONDOMINIUM ENDPOINTS
# =============================================================================


@router.post("/{client_id}/condominiums", response_model=CondominiumResponse, status_code=status.HTTP_201_CREATED)
async def create_condominium(
    current_user: CurrentActiveUser,
    client_id: UUID,
    data: CondominiumCreate,
    service: ClientService = Depends(get_service),
) -> CondominiumResponse:
    """Cria um novo condomínio para o cliente."""
    data.client_id = client_id
    try:
        condominium = service.create_condominium(data)
        return condominium
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{client_id}/condominiums", response_model=list[CondominiumListResponse])
async def list_condominiums(
    client_id: UUID,
    current_user: CurrentActiveUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ClientService = Depends(get_service),
) -> list[CondominiumListResponse]:
    """Lista condomínios do cliente."""
    condominiums, _ = service.list_condominiums(client_id, skip, limit)
    return condominiums


@router.get("/condominiums/{condominium_id}", response_model=CondominiumResponse)
async def get_condominium(
    condominium_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> CondominiumResponse:
    """Obtém um condomínio por ID."""
    condominium = service.get_condominium(condominium_id)
    if not condominium:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condomínio não encontrado")
    return condominium


@router.put("/condominiums/{condominium_id}", response_model=CondominiumResponse)
async def update_condominium(
    current_user: CurrentActiveUser,
    condominium_id: UUID,
    data: CondominiumUpdate,
    service: ClientService = Depends(get_service),
) -> CondominiumResponse:
    """Atualiza um condomínio."""
    condominium = service.update_condominium(condominium_id, data)
    if not condominium:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condomínio não encontrado")
    return condominium


@router.delete("/condominiums/{condominium_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_condominium(
    condominium_id: UUID, current_user: CurrentActiveUser, service: ClientService = Depends(get_service)
) -> None:
    """Remove um condomínio."""
    if not service.delete_condominium(condominium_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condomínio não encontrado")


# =============================================================================
# UNIT ENDPOINTS
# =============================================================================


# =============================================================================
# CONTRACT ENDPOINTS
# =============================================================================


# =============================================================================
# INTEGRATION ENDPOINTS
# =============================================================================


# =============================================================================
# AI ENDPOINTS
# =============================================================================


