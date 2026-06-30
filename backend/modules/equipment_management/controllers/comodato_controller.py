"""Controller para EquipmentComodato."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.equipment_management.schemas.comodato import (
    ComodatoCreate,
    ComodatoFilter,
    ComodatoListResponse,
    ComodatoResponse,
    ComodatoUpdate,
)
from modules.equipment_management.services.comodato_service import ComodatoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comodatos", tags=["Comodatos"])


async def get_service(db: AsyncSession = Depends(get_db)) -> ComodatoService:
    """Dependency para obter o service."""
    return ComodatoService(db)


@router.post("", response_model=ComodatoResponse, status_code=status.HTTP_201_CREATED)
async def create_comodato(
    data: ComodatoCreate,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Cria um novo comodato."""
    try:
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar comodato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar comodato",
        )


@router.get("", response_model=ComodatoListResponse)
@router.get("/", response_model=ComodatoListResponse, include_in_schema=False)  # espelho barra-final
async def list_comodatos(
    current_user: CurrentActiveUser,
    search: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    client_id: str | None = Query(None),
    equipment_id: str | None = Query(None),
    is_signed: bool | None = Query(None),
    is_delivered: bool | None = Query(None),
    is_expired: bool | None = Query(None),
    has_damages: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ComodatoService = Depends(get_service),
) -> ComodatoListResponse:
    """Lista comodatos com filtros."""
    filters = ComodatoFilter(
        search=search,
        status=status_filter,
        client_id=client_id,
        equipment_id=equipment_id,
        is_signed=is_signed,
        is_delivered=is_delivered,
        is_expired=is_expired,
        has_damages=has_damages,
        date_from=date_from,
        date_to=date_to,
    )
    return await service.list_with_filters(filters, page, page_size)


@router.get("/stats")
async def get_stats(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    service: ComodatoService = Depends(get_service),
) -> dict:
    """Obtém estatísticas de comodatos."""
    return await service.get_stats(client_id)


@router.get("/active", response_model=list[ComodatoResponse])
async def get_active(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos ativos."""
    return await service.get_active(client_id)


@router.get("/pending-signature", response_model=list[ComodatoResponse])
async def get_pending_signature(
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos aguardando assinatura."""
    return await service.get_pending_signature()


@router.get("/pending-delivery", response_model=list[ComodatoResponse])
async def get_pending_delivery(
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos aguardando entrega."""
    return await service.get_pending_delivery()


@router.get("/pending-return", response_model=list[ComodatoResponse])
async def get_pending_return(
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos com devolução pendente."""
    return await service.get_pending_return()


@router.get("/expiring", response_model=list[ComodatoResponse])
async def get_expiring(
    current_user: CurrentActiveUser,
    days: int = Query(30, ge=1, le=365),
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos expirando em X dias."""
    return await service.get_expiring(days)


@router.get("/expired", response_model=list[ComodatoResponse])
async def get_expired(
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos expirados não devolvidos."""
    return await service.get_expired()


@router.get("/by-client/{client_id}", response_model=list[ComodatoResponse])
async def get_by_client(
    client_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> list[ComodatoResponse]:
    """Lista comodatos de um cliente."""
    return await service.get_by_client(client_id)


@router.get("/code/{code}", response_model=ComodatoResponse)
async def get_by_code(
    code: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Busca comodato por código."""
    comodato = await service.get_by_code(code)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.get("/{comodato_id}", response_model=ComodatoResponse)
async def get_comodato(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Busca comodato por ID."""
    comodato = await service.get_by_id(comodato_id)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.put("/{comodato_id}", response_model=ComodatoResponse)
async def update_comodato(
    comodato_id: str,
    data: ComodatoUpdate,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Atualiza um comodato."""
    comodato = await service.update(comodato_id, data)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.delete("/{comodato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comodato(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> None:
    """Remove um comodato (soft delete)."""
    result = await service.delete(comodato_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )


@router.post("/{comodato_id}/sign", response_model=ComodatoResponse, status_code=201)
async def sign_comodato(
    comodato_id: str,
    signed_by_client: str,
    signed_by_company: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Registra assinatura do contrato."""
    comodato = await service.sign(comodato_id, signed_by_client, signed_by_company)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/deliver", response_model=ComodatoResponse, status_code=201)
async def deliver_comodato(
    comodato_id: str,
    delivered_by: str,
    received_by: str,
    current_user: CurrentActiveUser,
    notes: str | None = None,
    photos: list | None = None,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Registra entrega do equipamento."""
    comodato = await service.deliver(comodato_id, delivered_by, received_by, notes, photos)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/request-return", response_model=ComodatoResponse, status_code=201)
async def request_return(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Solicita devolução."""
    comodato = await service.request_return(comodato_id)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/schedule-return", response_model=ComodatoResponse, status_code=201)
async def schedule_return(
    comodato_id: str,
    scheduled_date: datetime,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Agenda devolução."""
    comodato = await service.schedule_return(comodato_id, scheduled_date)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/return", response_model=ComodatoResponse, status_code=201)
async def register_return(
    comodato_id: str,
    returned_by: str,
    condition: str,
    current_user: CurrentActiveUser,
    notes: str | None = None,
    photos: list | None = None,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Registra devolução."""
    comodato = await service.register_return(comodato_id, returned_by, condition, notes, photos)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/damage", response_model=ComodatoResponse, status_code=201)
async def register_damage(
    comodato_id: str,
    description: str,
    cost: float,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Registra dano no equipamento."""
    comodato = await service.register_damage(comodato_id, description, cost)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/mark-lost", response_model=ComodatoResponse, status_code=201)
async def mark_as_lost(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Marca equipamento como perdido."""
    comodato = await service.mark_as_lost(comodato_id)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/terminate", response_model=ComodatoResponse, status_code=201)
async def terminate_comodato(
    comodato_id: str,
    reason: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Encerra contrato de comodato."""
    comodato = await service.terminate(comodato_id, reason)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/transfer", response_model=ComodatoResponse, status_code=201)
async def transfer_comodato(
    comodato_id: str,
    new_client_id: str,
    new_client_name: str,
    reason: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> ComodatoResponse:
    """Transfere comodato para outro cliente."""
    comodato = await service.transfer(comodato_id, new_client_id, new_client_name, reason)
    if not comodato:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return comodato


@router.post("/{comodato_id}/contract-pdf", status_code=201)
async def generate_contract_pdf(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> dict:
    """Gera PDF do contrato."""
    pdf_url = await service.generate_contract_pdf(comodato_id)
    if not pdf_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return {"pdf_url": pdf_url}


@router.post("/{comodato_id}/delivery-term", status_code=201)
async def generate_delivery_term(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> dict:
    """Gera termo de entrega."""
    pdf_url = await service.generate_delivery_term(comodato_id)
    if not pdf_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return {"pdf_url": pdf_url}


@router.post("/{comodato_id}/return-term", status_code=201)
async def generate_return_term(
    comodato_id: str,
    current_user: CurrentActiveUser,
    service: ComodatoService = Depends(get_service),
) -> dict:
    """Gera termo de devolução."""
    pdf_url = await service.generate_return_term(comodato_id)
    if not pdf_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comodato não encontrado",
        )
    return {"pdf_url": pdf_url}
