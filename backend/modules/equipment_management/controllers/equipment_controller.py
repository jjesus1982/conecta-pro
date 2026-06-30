"""Controller para Equipment."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.equipment_management.schemas.equipment import (
    EquipmentCreate,
    EquipmentFilter,
    EquipmentListResponse,
    EquipmentResponse,
    EquipmentStats,
    EquipmentUpdate,
)
from modules.equipment_management.services.equipment_service import EquipmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/equipment", tags=["Equipment"])


async def get_service(db: AsyncSession = Depends(get_db)) -> EquipmentService:
    """Dependency para obter o service."""
    return EquipmentService(db)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    data: EquipmentCreate,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Cria um novo equipamento."""
    try:
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar equipamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar equipamento",
        )


@router.get("", response_model=EquipmentListResponse)
@router.get("/", response_model=EquipmentListResponse, include_in_schema=False)  # espelho barra-final
async def list_equipment(
    current_user: CurrentActiveUser,
    search: str | None = Query(None),
    equipment_type: str | None = Query(None),
    category: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    brand: str | None = Query(None),
    client_id: str | None = Query(None),
    contract_id: str | None = Query(None),
    is_online: bool | None = Query(None),
    is_in_warranty: bool | None = Query(None),
    needs_maintenance: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: EquipmentService = Depends(get_service),
) -> EquipmentListResponse:
    """Lista equipamentos com filtros."""
    filters = EquipmentFilter(
        search=search,
        equipment_type=equipment_type,
        category=category,
        status=status_filter,
        brand=brand,
        client_id=client_id,
        contract_id=contract_id,
        is_online=is_online,
        is_in_warranty=is_in_warranty,
        needs_maintenance=needs_maintenance,
    )
    return await service.list_with_filters(filters, page, page_size)


@router.get("/stats", response_model=EquipmentStats)
async def get_stats(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    service: EquipmentService = Depends(get_service),
) -> EquipmentStats:
    """Obtém estatísticas de equipamentos."""
    return await service.get_stats(client_id)


@router.get("/in-stock", response_model=list[EquipmentResponse])
async def get_in_stock(
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos em estoque."""
    return await service.get_in_stock()


@router.get("/needing-maintenance", response_model=list[EquipmentResponse])
async def get_needing_maintenance(
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos que precisam de manutenção."""
    return await service.get_needing_maintenance()


@router.get("/offline", response_model=list[EquipmentResponse])
async def get_offline(
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos offline."""
    return await service.get_offline()


@router.get("/expiring-warranty", response_model=list[EquipmentResponse])
async def get_expiring_warranty(
    current_user: CurrentActiveUser,
    days: int = Query(30, ge=1, le=365),
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos com garantia expirando."""
    return await service.get_expiring_warranty(days)


@router.get("/by-client/{client_id}", response_model=list[EquipmentResponse])
async def get_by_client(
    client_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos de um cliente."""
    return await service.get_by_client(client_id)


@router.get("/by-contract/{contract_id}", response_model=list[EquipmentResponse])
async def get_by_contract(
    contract_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> list[EquipmentResponse]:
    """Lista equipamentos de um contrato."""
    return await service.get_by_contract(contract_id)


@router.get("/code/{code}", response_model=EquipmentResponse)
async def get_by_code(
    code: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Busca equipamento por código."""
    equipment = await service.get_by_code(code)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Busca equipamento por ID."""
    equipment = await service.get_by_id(equipment_id)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.put("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: str,
    data: EquipmentUpdate,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Atualiza um equipamento."""
    equipment = await service.update(equipment_id, data)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> None:
    """Remove um equipamento (soft delete)."""
    result = await service.delete(equipment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )


@router.post("/{equipment_id}/install", response_model=EquipmentResponse, status_code=201)
async def install_equipment(
    equipment_id: str,
    client_id: str,
    client_name: str,
    current_user: CurrentActiveUser,
    contract_id: str | None = None,
    installation_id: str | None = None,
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Registra instalação de equipamento."""
    equipment = await service.install(
        equipment_id=equipment_id,
        client_id=client_id,
        client_name=client_name,
        contract_id=contract_id,
        installation_id=installation_id,
        location=location,
        latitude=latitude,
        longitude=longitude,
    )
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.post("/{equipment_id}/uninstall", response_model=EquipmentResponse, status_code=201)
async def uninstall_equipment(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Desinstala equipamento."""
    equipment = await service.uninstall(equipment_id)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.post("/{equipment_id}/online-status", response_model=EquipmentResponse, status_code=201)
async def update_online_status(
    equipment_id: str,
    is_online: bool,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> EquipmentResponse:
    """Atualiza status online/offline."""
    equipment = await service.update_online_status(equipment_id, is_online)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return equipment


@router.post("/bulk/online-status", status_code=201)
async def bulk_update_online_status(
    equipment_ids: list[str],
    is_online: bool,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> dict:
    """Atualiza status online/offline em massa."""
    return await service.bulk_update_online_status(equipment_ids, is_online)


@router.post("/{equipment_id}/qr-code", status_code=201)
async def generate_qr_code(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> dict:
    """Gera QR Code para equipamento."""
    qr_url = await service.generate_qr_code(equipment_id)
    if not qr_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return {"qr_code_url": qr_url}


@router.get("/{equipment_id}/depreciation")
async def get_depreciation(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: EquipmentService = Depends(get_service),
) -> dict:
    """Calcula depreciação do equipamento."""
    result = await service.calculate_depreciation(equipment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return result
