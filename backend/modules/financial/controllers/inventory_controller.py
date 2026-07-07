"""Controllers para o módulo de Estoque."""

import logging
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database.session import get_sync_db_dependency
from modules.financial.models.stock_inventory import (
    InventoryStatus,
    StockInventory,
)
from modules.financial.models.stock_item import StockItem, StockItemStatus
from modules.financial.models.stock_movement import (
    MovementStatus,
    MovementType,
    StockMovement,
)
from modules.financial.models.stock_reservation import (
    ReservationStatus,
    StockReservation,
)
from modules.financial.models.warehouse import Warehouse, WarehouseStatus
from modules.financial.repositories.inventory_repository import (
    StockInventoryRepository,
    StockItemRepository,
    StockMovementRepository,
    StockReservationRepository,
    WarehouseRepository,
)
from modules.financial.schemas.inventory_schemas import (
    InventoryStats,
    MovementStats,
    ReservationStats,
    StockInventoryCreate,
    StockInventoryListResponse,
    StockInventoryResponse,
    StockItemListResponse,
    StockItemResponse,
    StockMovementCreate,
    StockMovementListResponse,
    StockMovementResponse,
    StockReservationCreate,
    StockReservationListResponse,
    StockReservationRelease,
    StockReservationResponse,
    StockStats,
    WarehouseCreate,
    WarehouseListResponse,
    WarehouseResponse,
    WarehouseStats,
    WarehouseUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["Estoque"])


# =============================================================================
# Warehouse Endpoints
# =============================================================================


@router.get("/warehouses", response_model=list[WarehouseListResponse])
async def list_warehouses(
    condominio_id: uuid.UUID | None = Query(None),
    item_status: WarehouseStatus | None = Query(None, alias="status"),
    warehouse_type: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[WarehouseListResponse]:
    """Lista armazéns."""
    try:
        repo = WarehouseRepository(db)
        _cond_id = condominio_id or getattr(_current_user, "condominio_id", None)
        warehouses = repo.list_all(
            condominio_id=_cond_id,
            status=item_status,
            warehouse_type=warehouse_type,
            skip=skip,
            limit=limit,
        )
        return [WarehouseListResponse.model_validate(w) for w in warehouses]
    except Exception as e:
        logger.error(f"Erro ao listar armazéns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar armazéns",
        ) from e


@router.get("/warehouses/stats", response_model=WarehouseStats)
async def get_warehouse_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> WarehouseStats:
    """Retorna estatísticas dos armazéns."""
    try:
        repo = WarehouseRepository(db)
        stats = repo.get_stats(_current_user.condominio_id)
        return WarehouseStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        ) from e


@router.post("/warehouses", response_model=WarehouseResponse, status_code=201)
async def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> WarehouseResponse:
    """Cria um novo armazém."""
    try:
        repo = WarehouseRepository(db)

        # Verifica código duplicado
        existing = repo.get_by_code(data.code, _current_user.condominio_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Armazém com código {data.code} já existe",
            )

        warehouse = Warehouse(
            condominio_id=_current_user.condominio_id,
            status=WarehouseStatus.ATIVO.value,
            created_by=_current_user.id,
            **data.model_dump(),
        )

        warehouse = repo.create(warehouse)
        db.commit()

        logger.info(f"Armazém criado: {warehouse.code}")
        return WarehouseResponse.model_validate(warehouse)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar armazém: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar armazém",
        ) from e


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> WarehouseResponse:
    """Busca armazém por ID."""
    repo = WarehouseRepository(db)
    warehouse = repo.get_by_id(warehouse_id)

    if not warehouse or warehouse.condominio_id != _current_user.condominio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Armazém não encontrado",
        )

    return WarehouseResponse.model_validate(warehouse)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    data: WarehouseUpdate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> WarehouseResponse:
    """Atualiza armazém."""
    try:
        repo = WarehouseRepository(db)
        warehouse = repo.get_by_id(warehouse_id)

        if not warehouse or warehouse.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Armazém não encontrado",
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(warehouse, field, value)

        warehouse = repo.update(warehouse)
        db.commit()

        return WarehouseResponse.model_validate(warehouse)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao atualizar armazém: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar armazém",
        ) from e


@router.post("/warehouses/{warehouse_id}/block", status_code=201)
async def block_warehouse(
    warehouse_id: uuid.UUID,
    reason: str = Query(..., min_length=1),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Bloqueia armazém."""
    try:
        repo = WarehouseRepository(db)
        warehouse = repo.get_by_id(warehouse_id)

        if not warehouse or warehouse.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Armazém não encontrado",
            )

        warehouse.block(reason, _current_user.id)
        repo.update(warehouse)
        db.commit()

        return {"message": "Armazém bloqueado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao bloquear armazém: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao bloquear armazém",
        ) from e


@router.post("/warehouses/{warehouse_id}/unblock", status_code=201)
async def unblock_warehouse(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Desbloqueia armazém."""
    try:
        repo = WarehouseRepository(db)
        warehouse = repo.get_by_id(warehouse_id)

        if not warehouse or warehouse.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Armazém não encontrado",
            )

        warehouse.unblock()
        repo.update(warehouse)
        db.commit()

        return {"message": "Armazém desbloqueado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao desbloquear armazém: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao desbloquear armazém",
        ) from e


# =============================================================================
# StockItem Endpoints
# =============================================================================


@router.get("/stock-items", response_model=list[StockItemListResponse])
async def list_stock_items(
    condominio_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    item_status: StockItemStatus | None = Query(None, alias="status"),
    is_low_stock: bool | None = None,
    is_expired: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockItemListResponse]:
    """Lista itens em estoque."""
    try:
        repo = StockItemRepository(db)

        if warehouse_id:
            items = repo.list_by_warehouse(warehouse_id, item_status, skip, limit)
        elif product_id:
            items = repo.list_by_product(product_id, condominio_id, include_zero=True)
        elif is_low_stock:
            items = repo.list_low_stock(condominio_id)
        elif is_expired:
            items = repo.list_expired(condominio_id)
        else:
            # Lista geral - por armazém principal
            # fallback para condominio_id do usuário autenticado
            _raw_cond = (
                _current_user.get("condominio_id")
                if isinstance(_current_user, dict)
                else getattr(_current_user, "condominio_id", None)
            )
            _cond = condominio_id or (uuid.UUID(str(_raw_cond)) if _raw_cond else None)
            wh_repo = WarehouseRepository(db)
            main_wh = wh_repo.get_main_warehouse(_cond) if _cond else None
            if main_wh:
                items = repo.list_by_warehouse(main_wh.id, item_status, skip, limit)
            else:
                items = []

        return [StockItemListResponse.model_validate(i) for i in items]
    except Exception as e:
        logger.error(f"Erro ao listar itens de estoque: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar itens de estoque",
        ) from e


@router.get("/items", response_model=list[StockItemListResponse])
async def list_inventory_items(
    condominio_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockItemListResponse]:
    """Lista itens de inventário com nome e código do produto via JOIN."""
    from datetime import date as _date

    from sqlalchemy import text as _text

    try:
        sql = _text("""
            SELECT
                si.id,
                si.product_id,
                si.warehouse_id,
                COALESCE(fp.nome, fp.descricao, p.name, p.description) AS name,
                COALESCE(fp.codigo, p.code) AS code,
                si.batch_number,
                si.status,
                COALESCE(si.quantity_on_hand, 0) AS quantity_on_hand,
                COALESCE(si.quantity_available, 0) AS quantity_available,
                COALESCE(si.unit_cost, 0) AS unit_cost,
                COALESCE(si.total_cost, 0) AS total_cost,
                si.expiry_date,
                COALESCE(si.location_code, '') AS full_location,
                si.min_quantity,
                si.created_at
            FROM fin_stock_items si
            LEFT JOIN fin_products fp ON fp.id = si.product_id
            LEFT JOIN products p ON p.id = si.product_id
            WHERE (:warehouse_id IS NULL OR si.warehouse_id = :warehouse_id)
            ORDER BY si.created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        rows = (
            db.execute(
                sql,
                {
                    "warehouse_id": str(warehouse_id) if warehouse_id else None,
                    "limit": limit,
                    "skip": skip,
                },
            )
            .mappings()
            .all()
        )

        today = _date.today()
        result = []
        for row in rows:
            qty = float(row["quantity_on_hand"] or 0)
            min_qty = float(row["min_quantity"] or 0)
            expiry = row["expiry_date"]
            result.append(
                StockItemListResponse(
                    id=row["id"],
                    product_id=row["product_id"],
                    warehouse_id=row["warehouse_id"],
                    name=row["name"],
                    code=row["code"],
                    batch_number=row["batch_number"],
                    status=row["status"] or "disponivel",
                    quantity_on_hand=qty,
                    quantity_available=float(row["quantity_available"] or 0),
                    unit_cost=float(row["unit_cost"] or 0),
                    total_cost=float(row["total_cost"] or 0),
                    expiry_date=expiry,
                    full_location=row["full_location"] or "",
                    is_low_stock=bool(min_qty > 0 and qty < min_qty),
                    is_expired=bool(expiry and expiry < today),
                )
            )
        return result
    except Exception as e:
        logger.error(f"Erro ao listar inventory items: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar inventory items",
        ) from e


@router.get("/stock-items/stats", response_model=StockStats)
async def get_stock_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockStats:
    """Retorna estatísticas de estoque."""
    try:
        repo = StockItemRepository(db)
        stats = repo.get_stats(_current_user.condominio_id)
        return StockStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        ) from e


@router.get("/stock-items/low-stock", response_model=list[StockItemListResponse])
async def list_low_stock_items(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockItemListResponse]:
    """Lista itens abaixo do estoque mínimo."""
    try:
        repo = StockItemRepository(db)
        items = repo.list_low_stock(_current_user.condominio_id)
        return [StockItemListResponse.model_validate(i) for i in items]
    except Exception as e:
        logger.error(f"Erro ao listar itens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar itens",
        ) from e


@router.get("/stock-items/expiring", response_model=list[StockItemListResponse])
async def list_expiring_items(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockItemListResponse]:
    """Lista itens próximos do vencimento."""
    try:
        repo = StockItemRepository(db)
        items = repo.list_expiring(_current_user.condominio_id, days)
        return [StockItemListResponse.model_validate(i) for i in items]
    except Exception as e:
        logger.error(f"Erro ao listar itens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar itens",
        ) from e


@router.get("/stock-items/{item_id}", response_model=StockItemResponse)
async def get_stock_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockItemResponse:
    """Busca item de estoque por ID."""
    repo = StockItemRepository(db)
    item = repo.get_by_id(item_id)

    if not item or item.condominio_id != _current_user.condominio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item não encontrado",
        )

    return StockItemResponse.model_validate(item)


@router.post("/stock-items/{item_id}/block", status_code=201)
async def block_stock_item(
    item_id: uuid.UUID,
    reason: str = Query(..., min_length=1),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Bloqueia item de estoque."""
    try:
        repo = StockItemRepository(db)
        item = repo.get_by_id(item_id)

        if not item or item.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item não encontrado",
            )

        item.block(reason, _current_user.id)
        repo.update(item)
        db.commit()

        return {"message": "Item bloqueado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao bloquear item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao bloquear item",
        ) from e


@router.post("/stock-items/{item_id}/unblock", status_code=201)
async def unblock_stock_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Desbloqueia item de estoque."""
    try:
        repo = StockItemRepository(db)
        item = repo.get_by_id(item_id)

        if not item or item.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item não encontrado",
            )

        item.unblock()
        repo.update(item)
        db.commit()

        return {"message": "Item desbloqueado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao desbloquear item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao desbloquear item",
        ) from e


# =============================================================================
# StockMovement Endpoints
# =============================================================================


@router.get("/movements", response_model=list[StockMovementListResponse])
async def list_movements(
    warehouse_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    movement_type: MovementType | None = None,
    mov_status: MovementStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockMovementListResponse]:
    """Lista movimentações de estoque."""
    try:
        repo = StockMovementRepository(db)
        movements = repo.list_all(
            condominio_id=_current_user.condominio_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            movement_type=movement_type,
            status=mov_status,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
        return [StockMovementListResponse.model_validate(m) for m in movements]
    except Exception as e:
        logger.error(f"Erro ao listar movimentações: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar movimentações",
        ) from e


@router.get("/movements/stats", response_model=MovementStats)
async def get_movement_stats(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> MovementStats:
    """Retorna estatísticas de movimentações."""
    try:
        repo = StockMovementRepository(db)
        stats = repo.get_stats(_current_user.condominio_id, date_from, date_to)
        return MovementStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        ) from e


@router.get("/movements/pending", response_model=list[StockMovementListResponse])
async def list_pending_movements(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockMovementListResponse]:
    """Lista movimentações pendentes."""
    try:
        repo = StockMovementRepository(db)
        movements = repo.list_pending(_current_user.condominio_id)
        return [StockMovementListResponse.model_validate(m) for m in movements]
    except Exception as e:
        logger.error(f"Erro ao listar movimentações: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar movimentações",
        ) from e


@router.post("/movements", response_model=StockMovementResponse, status_code=201)
async def create_movement(
    data: StockMovementCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockMovementResponse:
    """Cria uma nova movimentação de estoque."""
    try:
        repo = StockMovementRepository(db)

        number = repo.generate_next_number(_current_user.condominio_id)

        movement = StockMovement(
            condominio_id=_current_user.condominio_id,
            number=number,
            status=MovementStatus.RASCUNHO.value,
            created_by=_current_user.id,
            **data.model_dump(),
        )

        if data.movement_type:
            movement.movement_type = data.movement_type.value
        if data.reason:
            movement.reason = data.reason.value

        movement.calculate_total_cost()

        movement = repo.create(movement)
        db.commit()

        logger.info(f"Movimentação criada: {movement.number}")
        return StockMovementResponse.model_validate(movement)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar movimentação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar movimentação",
        ) from e


@router.get("/movements/{movement_id}", response_model=StockMovementResponse)
async def get_movement(
    movement_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockMovementResponse:
    """Busca movimentação por ID."""
    repo = StockMovementRepository(db)
    movement = repo.get_by_id(movement_id)

    if not movement or movement.condominio_id != _current_user.condominio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimentação não encontrada",
        )

    return StockMovementResponse.model_validate(movement)


@router.post("/movements/{movement_id}/confirm", status_code=201)
async def confirm_movement(
    movement_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Confirma movimentação e atualiza estoque."""
    try:
        mov_repo = StockMovementRepository(db)
        item_repo = StockItemRepository(db)

        movement = mov_repo.get_by_id(movement_id)
        if not movement or movement.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimentação não encontrada",
            )

        if not movement.can_confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Movimentação não pode ser confirmada",
            )

        # Busca ou cria item de estoque
        stock_item = item_repo.get_by_product_warehouse(
            movement.product_id,
            movement.warehouse_id,
            movement.batch_number,
        )

        if not stock_item:
            # Cria novo item de estoque
            stock_item = StockItem(
                condominio_id=_current_user.condominio_id,
                product_id=movement.product_id,
                warehouse_id=movement.warehouse_id,
                batch_number=movement.batch_number,
                expiry_date=movement.expiry_date,
                created_by=_current_user.id,
            )
            stock_item = item_repo.create(stock_item)

        balance_before = stock_item.quantity_on_hand or Decimal("0")

        # Aplica movimentação
        if movement.is_entry:
            stock_item.receive(movement.quantity, movement.unit_cost)
        elif movement.is_exit:
            if movement.quantity > (stock_item.quantity_on_hand or Decimal("0")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Quantidade insuficiente em estoque",
                )
            stock_item.issue(movement.quantity)

        balance_after = stock_item.quantity_on_hand

        # Confirma movimentação
        movement.confirm(_current_user.id, balance_before, balance_after)

        item_repo.update(stock_item)
        mov_repo.update(movement)
        db.commit()

        return {"message": "Movimentação confirmada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao confirmar movimentação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao confirmar movimentação",
        ) from e


@router.post("/movements/{movement_id}/cancel", status_code=201)
async def cancel_movement(
    movement_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Cancela movimentação."""
    try:
        repo = StockMovementRepository(db)
        movement = repo.get_by_id(movement_id)

        if not movement or movement.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimentação não encontrada",
            )

        if not movement.can_cancel:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Movimentação não pode ser cancelada",
            )

        movement.cancel()
        repo.update(movement)
        db.commit()

        return {"message": "Movimentação cancelada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao cancelar movimentação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cancelar movimentação",
        ) from e


# =============================================================================
# StockInventory Endpoints
# =============================================================================


@router.get("/inventories", response_model=list[StockInventoryListResponse])
async def list_inventories(
    warehouse_id: uuid.UUID | None = None,
    inv_status: InventoryStatus | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockInventoryListResponse]:
    """Lista inventários."""
    try:
        repo = StockInventoryRepository(db)
        inventories = repo.list_all(
            condominio_id=_current_user.condominio_id,
            warehouse_id=warehouse_id,
            status=inv_status,
            skip=skip,
            limit=limit,
        )
        return [StockInventoryListResponse.model_validate(i) for i in inventories]
    except Exception as e:
        logger.error(f"Erro ao listar inventários: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar inventários",
        ) from e


@router.get("/inventories/stats", response_model=InventoryStats)
async def get_inventory_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> InventoryStats:
    """Retorna estatísticas de inventários."""
    try:
        repo = StockInventoryRepository(db)
        stats = repo.get_stats(_current_user.condominio_id)
        return InventoryStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        ) from e


@router.post("/inventories", response_model=StockInventoryResponse, status_code=201)
async def create_inventory(
    data: StockInventoryCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockInventoryResponse:
    """Cria um novo inventário."""
    try:
        repo = StockInventoryRepository(db)

        number = repo.generate_next_number(_current_user.condominio_id)

        inventory = StockInventory(
            condominio_id=_current_user.condominio_id,
            number=number,
            status=InventoryStatus.PLANEJADO.value,
            created_by=_current_user.id,
            **data.model_dump(exclude={"inventory_type"}),
        )

        if data.inventory_type:
            inventory.inventory_type = data.inventory_type.value

        inventory = repo.create(inventory)
        db.commit()

        logger.info(f"Inventário criado: {inventory.number}")
        return StockInventoryResponse.model_validate(inventory)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar inventário: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar inventário",
        ) from e


@router.get("/inventories/{inventory_id}", response_model=StockInventoryResponse)
async def get_inventory(
    inventory_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockInventoryResponse:
    """Busca inventário por ID."""
    repo = StockInventoryRepository(db)
    inventory = repo.get_by_id(inventory_id)

    if not inventory or inventory.condominio_id != _current_user.condominio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventário não encontrado",
        )

    return StockInventoryResponse.model_validate(inventory)


@router.post("/inventories/{inventory_id}/start", status_code=201)
async def start_inventory(
    inventory_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Inicia inventário."""
    try:
        repo = StockInventoryRepository(db)
        inventory = repo.get_by_id(inventory_id)

        if not inventory or inventory.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventário não encontrado",
            )

        if not inventory.can_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inventário não pode ser iniciado",
            )

        inventory.start()
        repo.update(inventory)
        db.commit()

        return {"message": "Inventário iniciado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao iniciar inventário: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao iniciar inventário",
        ) from e


@router.post("/inventories/{inventory_id}/finalize", status_code=201)
async def finalize_inventory(
    inventory_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Finaliza inventário."""
    try:
        repo = StockInventoryRepository(db)
        inventory = repo.get_by_id(inventory_id)

        if not inventory or inventory.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventário não encontrado",
            )

        inventory.update_statistics()
        inventory.finalize()
        repo.update(inventory)
        db.commit()

        return {"message": "Inventário finalizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao finalizar inventário: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao finalizar inventário",
        ) from e


# =============================================================================
# StockReservation Endpoints
# =============================================================================


@router.get("/reservations", response_model=list[StockReservationListResponse])
async def list_reservations(
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    res_status: ReservationStatus | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> list[StockReservationListResponse]:
    """Lista reservas de estoque."""
    try:
        repo = StockReservationRepository(db)
        reservations = repo.list_all(
            condominio_id=_current_user.condominio_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            status=res_status,
            skip=skip,
            limit=limit,
        )
        return [StockReservationListResponse.model_validate(r) for r in reservations]
    except Exception as e:
        logger.error(f"Erro ao listar reservas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar reservas",
        ) from e


@router.get("/reservations/stats", response_model=ReservationStats)
async def get_reservation_stats(
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> ReservationStats:
    """Retorna estatísticas de reservas."""
    try:
        repo = StockReservationRepository(db)
        stats = repo.get_stats(_current_user.condominio_id)
        return ReservationStats(**stats)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        ) from e


@router.post("/reservations", response_model=StockReservationResponse, status_code=201)
async def create_reservation(
    data: StockReservationCreate,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockReservationResponse:
    """Cria uma nova reserva de estoque."""
    try:
        res_repo = StockReservationRepository(db)
        item_repo = StockItemRepository(db)

        # Verifica disponibilidade
        available = item_repo.get_available_quantity(data.product_id, data.warehouse_id)
        if data.quantity_requested > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Quantidade indisponível. Disponível: {available}",
            )

        number = res_repo.generate_next_number(_current_user.condominio_id)

        reservation = StockReservation(
            condominio_id=_current_user.condominio_id,
            number=number,
            status=ReservationStatus.ATIVA.value,
            created_by=_current_user.id,
            requester_id=_current_user.id,
            **data.model_dump(exclude={"reservation_type", "priority"}),
        )

        if data.reservation_type:
            reservation.reservation_type = data.reservation_type.value
        if data.priority:
            reservation.priority = data.priority.value

        # Efetiva reserva
        reservation.reserve(data.quantity_requested)

        reservation = res_repo.create(reservation)
        db.commit()

        logger.info(f"Reserva criada: {reservation.number}")
        return StockReservationResponse.model_validate(reservation)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao criar reserva: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar reserva",
        ) from e


@router.get("/reservations/{reservation_id}", response_model=StockReservationResponse)
async def get_reservation(
    reservation_id: uuid.UUID,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> StockReservationResponse:
    """Busca reserva por ID."""
    repo = StockReservationRepository(db)
    reservation = repo.get_by_id(reservation_id)

    if not reservation or reservation.condominio_id != _current_user.condominio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reserva não encontrada",
        )

    return StockReservationResponse.model_validate(reservation)


@router.post("/reservations/{reservation_id}/release", status_code=201)
async def release_reservation(
    reservation_id: uuid.UUID,
    data: StockReservationRelease,
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Libera quantidade da reserva."""
    try:
        repo = StockReservationRepository(db)
        reservation = repo.get_by_id(reservation_id)

        if not reservation or reservation.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reserva não encontrada",
            )

        if not reservation.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reserva não está ativa",
            )

        success = reservation.release(data.quantity, _current_user.id, data.notes)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantidade a liberar maior que disponível",
            )

        repo.update(reservation)
        db.commit()

        return {"message": "Reserva liberada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao liberar reserva: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao liberar reserva",
        ) from e


@router.post("/reservations/{reservation_id}/cancel", status_code=201)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    reason: str = Query(..., min_length=1),
    db: Session = Depends(get_sync_db_dependency),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Cancela reserva."""
    try:
        repo = StockReservationRepository(db)
        reservation = repo.get_by_id(reservation_id)

        if not reservation or reservation.condominio_id != _current_user.condominio_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reserva não encontrada",
            )

        reservation.cancel(_current_user.id, reason)
        repo.update(reservation)
        db.commit()

        return {"message": "Reserva cancelada com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao cancelar reserva: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cancelar reserva",
        ) from e


# =============================================================================
# Estoque REAL (NF-e de entrada → nfe_compras_estoque) + Saída com COGS
# =============================================================================
from pydantic import BaseModel  # noqa: E402

from modules.financial.services.estoque_real_service import EstoqueRealService  # noqa: E402

_estoque_real = EstoqueRealService()


class SaidaEstoquePayload(BaseModel):
    item_code: str
    quantidade: float
    servico_ref: str | None = None
    motivo: str | None = None
    nfse_id: str | None = None


@router.get("/real/itens")
async def estoque_real_itens(
    busca: str | None = Query(None, description="Busca por descrição ou código"),
    _current_user: dict = Depends(get_current_user),
) -> list:
    """Estoque REAL a partir das NF-e de entrada (nfe_compras_estoque)."""
    return _estoque_real.listar_itens(busca)


@router.get("/real/resumo")
async def estoque_real_resumo(_current_user: dict = Depends(get_current_user)) -> dict:
    """Totais do estoque real: itens, valor, unidades, saídas do mês."""
    return _estoque_real.resumo()


@router.get("/real/movimentos")
async def estoque_real_movimentos(
    limite: int = Query(100, ge=1, le=500),
    _current_user: dict = Depends(get_current_user),
) -> list:
    """Histórico de movimentos (saídas com vínculo a serviço)."""
    return _estoque_real.listar_movimentos(limite)


@router.post("/real/saida")
async def estoque_real_saida(
    payload: SaidaEstoquePayload,
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Baixa de material vinculada a serviço/NFS-e: reduz saldo + posta COGS no razão."""
    try:
        return _estoque_real.registrar_saida(
            item_code=payload.item_code,
            quantidade=payload.quantidade,
            servico_ref=payload.servico_ref,
            motivo=payload.motivo,
            nfse_id=payload.nfse_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
