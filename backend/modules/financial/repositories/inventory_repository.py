"""Repositories para o módulo de Estoque."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from modules.financial.models.stock_inventory import (
    InventoryItemStatus,
    InventoryStatus,
    StockInventory,
    StockInventoryItem,
)
from modules.financial.models.stock_item import StockItem, StockItemStatus
from modules.financial.models.stock_movement import (
    MovementStatus,
    MovementType,
    StockMovement,
)
from modules.financial.models.stock_reservation import ReservationStatus, StockReservation
from modules.financial.models.warehouse import Warehouse, WarehouseStatus

# =============================================================================
# Mapeamento enum Python (PT) -> label real do enum nativo no Postgres (EN).
#
# As colunas status/movement_type/inventory_type/reservation_type estao
# declaradas como String(...) nos models, porem no banco sao tipos ENUM nativos
# com labels em ingles maiusculo (ex.: 'CONFIRMED', 'DRAFT', 'IN_PROGRESS').
# Comparar a coluna com o .value em portugues ('confirmada', 'rascunho', ...)
# gera InvalidTextRepresentation (500). _db_label traduz para o label real.
# =============================================================================
_ENUM_DB_LABELS: dict = {
    # MovementStatus -> movementstatus
    MovementStatus.RASCUNHO: "DRAFT",
    MovementStatus.PENDENTE: "PENDING",
    MovementStatus.APROVADA: "PENDING",
    MovementStatus.CONFIRMADA: "CONFIRMED",
    MovementStatus.CANCELADA: "CANCELLED",
    MovementStatus.ESTORNADA: "REVERSED",
    # MovementType -> movementtype
    MovementType.ENTRADA: "ENTRY",
    MovementType.SAIDA: "EXIT",
    MovementType.TRANSFERENCIA: "TRANSFER_OUT",
    MovementType.AJUSTE_POSITIVO: "ADJUSTMENT_PLUS",
    MovementType.AJUSTE_NEGATIVO: "ADJUSTMENT_MINUS",
    MovementType.DEVOLUCAO_CLIENTE: "RETURN_CUSTOMER",
    MovementType.DEVOLUCAO_FORNECEDOR: "RETURN_SUPPLIER",
    MovementType.PRODUCAO: "PRODUCTION_IN",
    MovementType.CONSUMO: "PRODUCTION_OUT",
    MovementType.PERDA: "SCRAP",
    MovementType.BONIFICACAO: "EXIT",
    # InventoryStatus -> inventorystatus
    InventoryStatus.PLANEJADO: "SCHEDULED",
    InventoryStatus.EM_ANDAMENTO: "IN_PROGRESS",
    InventoryStatus.CONTAGEM: "COUNTING",
    InventoryStatus.RECONFERENCIA: "REVIEW",
    InventoryStatus.AGUARDANDO_APROVACAO: "REVIEW",
    InventoryStatus.APROVADO: "ADJUSTMENT",
    InventoryStatus.AJUSTADO: "ADJUSTMENT",
    InventoryStatus.FINALIZADO: "COMPLETED",
    InventoryStatus.CANCELADO: "CANCELLED",
    # ReservationStatus -> reservationstatus
    ReservationStatus.ATIVA: "CONFIRMED",
    ReservationStatus.PARCIALMENTE_ATENDIDA: "PARTIAL",
    ReservationStatus.ATENDIDA: "CONSUMED",
    ReservationStatus.EXPIRADA: "EXPIRED",
    ReservationStatus.CANCELADA: "RELEASED",
    ReservationStatus.LIBERADA: "RELEASED",
}


def _db_label(member):
    """Traduz um membro de enum (PT) para o label real do enum nativo no Postgres."""
    return _ENUM_DB_LABELS.get(member, getattr(member, "value", member))


# =============================================================================
# Warehouse Repository
# =============================================================================


class WarehouseRepository:
    """Repository para operações de Warehouse."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, warehouse: Warehouse) -> Warehouse:
        """Cria um novo armazém."""
        self.db.add(warehouse)
        self.db.flush()
        return warehouse

    def get_by_id(self, warehouse_id: uuid.UUID) -> Warehouse | None:
        """Busca armazém por ID."""
        return self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()

    def get_by_code(self, code: str, condominio_id: uuid.UUID) -> Warehouse | None:
        """Busca armazém por código."""
        return (
            self.db.query(Warehouse)
            .filter(
                and_(
                    Warehouse.code == code,
                    Warehouse.condominio_id == condominio_id,
                    Warehouse.ativo.is_(True),
                )
            )
            .first()
        )

    def list_all(
        self,
        condominio_id: uuid.UUID,
        status: WarehouseStatus | None = None,
        warehouse_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Warehouse]:
        """Lista armazéns com filtros."""
        query = self.db.query(Warehouse).filter(
            and_(
                Warehouse.condominio_id == condominio_id,
                Warehouse.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(Warehouse.status == status.value)
        if warehouse_type:
            query = query.filter(Warehouse.warehouse_type == warehouse_type)

        return query.order_by(Warehouse.code).offset(skip).limit(limit).all()

    def count(
        self,
        condominio_id: uuid.UUID,
        status: WarehouseStatus | None = None,
    ) -> int:
        """Conta armazéns."""
        query = self.db.query(func.count(Warehouse.id)).filter(
            and_(
                Warehouse.condominio_id == condominio_id,
                Warehouse.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(Warehouse.status == status.value)

        return query.scalar() or 0

    def update(self, warehouse: Warehouse) -> Warehouse:
        """Atualiza armazém."""
        warehouse.updated_at = datetime.utcnow()
        self.db.flush()
        return warehouse

    def delete(self, warehouse: Warehouse) -> None:
        """Soft delete de armazém."""
        warehouse.ativo = False
        warehouse.updated_at = datetime.utcnow()
        self.db.flush()

    def get_main_warehouse(self, condominio_id: uuid.UUID) -> Warehouse | None:
        """Busca armazém principal."""
        return (
            self.db.query(Warehouse)
            .filter(
                and_(
                    Warehouse.condominio_id == condominio_id,
                    Warehouse.warehouse_type == "principal",
                    Warehouse.status == WarehouseStatus.ATIVO.value,
                    Warehouse.ativo.is_(True),
                )
            )
            .first()
        )

    def get_stats(self, condominio_id: uuid.UUID) -> dict:
        """Retorna estatísticas dos armazéns."""
        total = self.count(condominio_id)
        active = self.count(condominio_id, WarehouseStatus.ATIVO)

        # Valor total em estoque
        total_value = (
            self.db.query(func.coalesce(func.sum(Warehouse.total_value), 0))
            .filter(
                and_(
                    Warehouse.condominio_id == condominio_id,
                    Warehouse.ativo.is_(True),
                )
            )
            .scalar()
        )

        return {
            "total_warehouses": total,
            "active_warehouses": active,
            "total_value": float(total_value or 0),
        }

    def generate_next_code(self, condominio_id: uuid.UUID) -> str:
        """Gera próximo código de armazém."""
        last = (
            self.db.query(Warehouse)
            .filter(
                and_(
                    Warehouse.condominio_id == condominio_id,
                    Warehouse.code.like("DEP-%"),
                )
            )
            .order_by(Warehouse.code.desc())
            .first()
        )

        if last and last.code:
            try:
                num = int(last.code.split("-")[1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1

        return f"DEP-{num:03d}"


# =============================================================================
# StockItem Repository
# =============================================================================


class StockItemRepository:
    """Repository para operações de StockItem."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, stock_item: StockItem) -> StockItem:
        """Cria um novo item de estoque."""
        self.db.add(stock_item)
        self.db.flush()
        return stock_item

    def get_by_id(self, item_id: uuid.UUID) -> StockItem | None:
        """Busca item por ID."""
        return self.db.query(StockItem).filter(StockItem.id == item_id).first()

    def get_by_product_warehouse(
        self,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        batch_number: str | None = None,
    ) -> StockItem | None:
        """Busca item por produto + armazém + lote."""
        query = self.db.query(StockItem).filter(
            and_(
                StockItem.product_id == product_id,
                StockItem.warehouse_id == warehouse_id,
                StockItem.ativo.is_(True),
            )
        )

        if batch_number:
            query = query.filter(StockItem.batch_number == batch_number)
        else:
            query = query.filter(StockItem.batch_number.is_(None))

        return query.first()

    def list_by_product(
        self,
        product_id: uuid.UUID,
        condominio_id: uuid.UUID,
        include_zero: bool = False,
    ) -> list[StockItem]:
        """Lista itens de estoque de um produto."""
        query = self.db.query(StockItem).filter(
            and_(
                StockItem.product_id == product_id,
                StockItem.condominio_id == condominio_id,
                StockItem.ativo.is_(True),
            )
        )

        if not include_zero:
            query = query.filter(StockItem.quantity_on_hand > 0)

        return query.order_by(StockItem.expiry_date.asc().nullslast()).all()

    def list_by_warehouse(
        self,
        warehouse_id: uuid.UUID,
        status: StockItemStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockItem]:
        """Lista itens de estoque de um armazém."""
        query = self.db.query(StockItem).filter(
            and_(
                StockItem.warehouse_id == warehouse_id,
                StockItem.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(StockItem.status == status.value)

        return query.order_by(StockItem.product_id).offset(skip).limit(limit).all()

    def list_low_stock(self, condominio_id: uuid.UUID) -> list[StockItem]:
        """Lista itens abaixo do estoque mínimo."""
        return (
            self.db.query(StockItem)
            .filter(
                and_(
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                    StockItem.min_quantity.isnot(None),
                    StockItem.quantity_on_hand < StockItem.min_quantity,
                )
            )
            .all()
        )

    def list_expiring(self, condominio_id: uuid.UUID, days: int = 30) -> list[StockItem]:
        """Lista itens próximos do vencimento."""
        expiry_limit = date.today() + timedelta(days=days)
        return (
            self.db.query(StockItem)
            .filter(
                and_(
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                    StockItem.expiry_date.isnot(None),
                    StockItem.expiry_date <= expiry_limit,
                    StockItem.quantity_on_hand > 0,
                )
            )
            .order_by(StockItem.expiry_date)
            .all()
        )

    def list_expired(self, condominio_id: uuid.UUID) -> list[StockItem]:
        """Lista itens vencidos."""
        return (
            self.db.query(StockItem)
            .filter(
                and_(
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                    StockItem.expiry_date.isnot(None),
                    StockItem.expiry_date < date.today(),
                    StockItem.quantity_on_hand > 0,
                )
            )
            .all()
        )

    def get_total_quantity(self, product_id: uuid.UUID, condominio_id: uuid.UUID) -> Decimal:
        """Retorna quantidade total de um produto."""
        result = (
            self.db.query(func.coalesce(func.sum(StockItem.quantity_on_hand), 0))
            .filter(
                and_(
                    StockItem.product_id == product_id,
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                    StockItem.status == StockItemStatus.DISPONIVEL.value,
                )
            )
            .scalar()
        )
        return Decimal(str(result))

    def get_available_quantity(self, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> Decimal:
        """Retorna quantidade disponível em um armazém."""
        result = (
            self.db.query(
                func.coalesce(
                    func.sum(StockItem.quantity_on_hand - StockItem.quantity_reserved - StockItem.quantity_committed),
                    0,
                )
            )
            .filter(
                and_(
                    StockItem.product_id == product_id,
                    StockItem.warehouse_id == warehouse_id,
                    StockItem.ativo.is_(True),
                    StockItem.status == StockItemStatus.DISPONIVEL.value,
                )
            )
            .scalar()
        )
        return Decimal(str(result))

    def update(self, stock_item: StockItem) -> StockItem:
        """Atualiza item de estoque."""
        stock_item.updated_at = datetime.utcnow()
        self.db.flush()
        return stock_item

    def delete(self, stock_item: StockItem) -> None:
        """Soft delete de item."""
        stock_item.ativo = False
        stock_item.updated_at = datetime.utcnow()
        self.db.flush()

    def get_stats(self, condominio_id: uuid.UUID) -> dict:
        """Retorna estatísticas de estoque."""
        query = self.db.query(StockItem).filter(
            and_(
                StockItem.condominio_id == condominio_id,
                StockItem.ativo.is_(True),
            )
        )

        total_items = query.count()
        total_quantity = (
            self.db.query(func.coalesce(func.sum(StockItem.quantity_on_hand), 0))
            .filter(
                and_(
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                )
            )
            .scalar()
        )
        total_value = (
            self.db.query(func.coalesce(func.sum(StockItem.total_cost), 0))
            .filter(
                and_(
                    StockItem.condominio_id == condominio_id,
                    StockItem.ativo.is_(True),
                )
            )
            .scalar()
        )

        low_stock = len(self.list_low_stock(condominio_id))
        expired = len(self.list_expired(condominio_id))
        expiring = len(self.list_expiring(condominio_id, 30))

        blocked = query.filter(StockItem.status == StockItemStatus.BLOQUEADO.value).count()

        return {
            "total_items": total_items,
            "total_quantity": float(total_quantity or 0),
            "total_value": float(total_value or 0),
            "low_stock_items": low_stock,
            "expired_items": expired,
            "expiring_soon_items": expiring,
            "blocked_items": blocked,
        }


# =============================================================================
# StockMovement Repository
# =============================================================================


class StockMovementRepository:
    """Repository para operações de StockMovement."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, movement: StockMovement) -> StockMovement:
        """Cria uma nova movimentação."""
        self.db.add(movement)
        self.db.flush()
        return movement

    def get_by_id(self, movement_id: uuid.UUID) -> StockMovement | None:
        """Busca movimentação por ID."""
        return self.db.query(StockMovement).filter(StockMovement.id == movement_id).first()

    def get_by_number(self, number: str, condominio_id: uuid.UUID) -> StockMovement | None:
        """Busca movimentação por número."""
        return (
            self.db.query(StockMovement)
            .filter(
                and_(
                    StockMovement.number == number,
                    StockMovement.condominio_id == condominio_id,
                )
            )
            .first()
        )

    def list_all(
        self,
        condominio_id: uuid.UUID,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        movement_type: MovementType | None = None,
        status: MovementStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockMovement]:
        """Lista movimentações com filtros."""
        query = self.db.query(StockMovement).filter(
            and_(
                StockMovement.condominio_id == condominio_id,
                StockMovement.ativo.is_(True),
            )
        )

        if warehouse_id:
            query = query.filter(
                or_(
                    StockMovement.warehouse_id == warehouse_id,
                    StockMovement.destination_warehouse_id == warehouse_id,
                )
            )
        if product_id:
            query = query.filter(StockMovement.product_id == product_id)
        if movement_type:
            query = query.filter(StockMovement.movement_type == _db_label(movement_type))
        if status:
            query = query.filter(StockMovement.status == _db_label(status))
        if date_from:
            query = query.filter(StockMovement.movement_date >= date_from)
        if date_to:
            query = query.filter(StockMovement.movement_date <= date_to)

        return (
            query.order_by(StockMovement.movement_date.desc(), StockMovement.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_pending(self, condominio_id: uuid.UUID) -> list[StockMovement]:
        """Lista movimentações pendentes."""
        return (
            self.db.query(StockMovement)
            .filter(
                and_(
                    StockMovement.condominio_id == condominio_id,
                    StockMovement.ativo.is_(True),
                    StockMovement.status.in_(
                        [
                            _db_label(MovementStatus.RASCUNHO),
                            _db_label(MovementStatus.PENDENTE),
                        ]
                    ),
                )
            )
            .order_by(StockMovement.created_at.desc())
            .all()
        )

    def list_by_reference(
        self,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> list[StockMovement]:
        """Lista movimentações por referência."""
        return (
            self.db.query(StockMovement)
            .filter(
                and_(
                    StockMovement.reference_type == reference_type,
                    StockMovement.reference_id == reference_id,
                    StockMovement.ativo.is_(True),
                )
            )
            .order_by(StockMovement.movement_date.desc())
            .all()
        )

    def count(
        self,
        condominio_id: uuid.UUID,
        status: MovementStatus | None = None,
        movement_type: MovementType | None = None,
    ) -> int:
        """Conta movimentações."""
        query = self.db.query(func.count(StockMovement.id)).filter(
            and_(
                StockMovement.condominio_id == condominio_id,
                StockMovement.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(StockMovement.status == _db_label(status))
        if movement_type:
            query = query.filter(StockMovement.movement_type == _db_label(movement_type))

        return query.scalar() or 0

    def update(self, movement: StockMovement) -> StockMovement:
        """Atualiza movimentação."""
        movement.updated_at = datetime.utcnow()
        self.db.flush()
        return movement

    def delete(self, movement: StockMovement) -> None:
        """Soft delete de movimentação."""
        movement.ativo = False
        movement.updated_at = datetime.utcnow()
        self.db.flush()

    def get_stats(
        self,
        condominio_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """Retorna estatísticas de movimentações."""
        query = self.db.query(StockMovement).filter(
            and_(
                StockMovement.condominio_id == condominio_id,
                StockMovement.ativo.is_(True),
                StockMovement.status == _db_label(MovementStatus.CONFIRMADA),
            )
        )

        if date_from:
            query = query.filter(StockMovement.movement_date >= date_from)
        if date_to:
            query = query.filter(StockMovement.movement_date <= date_to)

        # Contagens por tipo
        entries = query.filter(
            StockMovement.movement_type.in_(
                [
                    _db_label(MovementType.ENTRADA),
                    _db_label(MovementType.AJUSTE_POSITIVO),
                    _db_label(MovementType.DEVOLUCAO_CLIENTE),
                ]
            )
        ).count()

        exits = query.filter(
            StockMovement.movement_type.in_(
                [
                    _db_label(MovementType.SAIDA),
                    _db_label(MovementType.AJUSTE_NEGATIVO),
                    _db_label(MovementType.DEVOLUCAO_FORNECEDOR),
                    _db_label(MovementType.PERDA),
                ]
            )
        ).count()

        transfers = query.filter(
            StockMovement.movement_type == _db_label(MovementType.TRANSFERENCIA)
        ).count()

        adjustments = query.filter(
            StockMovement.movement_type.in_(
                [
                    _db_label(MovementType.AJUSTE_POSITIVO),
                    _db_label(MovementType.AJUSTE_NEGATIVO),
                ]
            )
        ).count()

        # Valores
        entries_value = (
            self.db.query(func.coalesce(func.sum(StockMovement.total_cost), 0))
            .filter(
                and_(
                    StockMovement.condominio_id == condominio_id,
                    StockMovement.ativo.is_(True),
                    StockMovement.status == _db_label(MovementStatus.CONFIRMADA),
                    StockMovement.movement_type.in_(
                        [
                            _db_label(MovementType.ENTRADA),
                            _db_label(MovementType.AJUSTE_POSITIVO),
                        ]
                    ),
                )
            )
            .scalar()
        )

        exits_value = (
            self.db.query(func.coalesce(func.sum(StockMovement.total_cost), 0))
            .filter(
                and_(
                    StockMovement.condominio_id == condominio_id,
                    StockMovement.ativo.is_(True),
                    StockMovement.status == _db_label(MovementStatus.CONFIRMADA),
                    StockMovement.movement_type.in_(
                        [
                            _db_label(MovementType.SAIDA),
                            _db_label(MovementType.AJUSTE_NEGATIVO),
                        ]
                    ),
                )
            )
            .scalar()
        )

        pending = self.count(condominio_id, MovementStatus.PENDENTE)

        return {
            "total_movements": entries + exits + transfers,
            "entries_count": entries,
            "exits_count": exits,
            "transfers_count": transfers,
            "adjustments_count": adjustments,
            "entries_value": float(entries_value or 0),
            "exits_value": float(exits_value or 0),
            "pending_movements": pending,
        }

    def generate_next_number(self, condominio_id: uuid.UUID) -> str:
        """Gera próximo número de movimentação."""
        year = datetime.utcnow().year
        prefix = f"MOV-{year}-"

        last = (
            self.db.query(StockMovement)
            .filter(
                and_(
                    StockMovement.condominio_id == condominio_id,
                    StockMovement.number.like(f"{prefix}%"),
                )
            )
            .order_by(StockMovement.number.desc())
            .first()
        )

        if last and last.number:
            try:
                num = int(last.number.split("-")[-1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1

        return f"{prefix}{num:05d}"


# =============================================================================
# StockInventory Repository
# =============================================================================


class StockInventoryRepository:
    """Repository para operações de StockInventory."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, inventory: StockInventory) -> StockInventory:
        """Cria um novo inventário."""
        self.db.add(inventory)
        self.db.flush()
        return inventory

    def get_by_id(self, inventory_id: uuid.UUID) -> StockInventory | None:
        """Busca inventário por ID."""
        return self.db.query(StockInventory).filter(StockInventory.id == inventory_id).first()

    def get_by_number(self, number: str, condominio_id: uuid.UUID) -> StockInventory | None:
        """Busca inventário por número."""
        return (
            self.db.query(StockInventory)
            .filter(
                and_(
                    StockInventory.number == number,
                    StockInventory.condominio_id == condominio_id,
                )
            )
            .first()
        )

    def list_all(
        self,
        condominio_id: uuid.UUID,
        warehouse_id: uuid.UUID | None = None,
        status: InventoryStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockInventory]:
        """Lista inventários com filtros."""
        query = self.db.query(StockInventory).filter(
            and_(
                StockInventory.condominio_id == condominio_id,
                StockInventory.ativo.is_(True),
            )
        )

        if warehouse_id:
            query = query.filter(StockInventory.warehouse_id == warehouse_id)
        if status:
            query = query.filter(StockInventory.status == _db_label(status))

        return query.order_by(StockInventory.planned_date.desc()).offset(skip).limit(limit).all()

    def list_in_progress(self, condominio_id: uuid.UUID) -> list[StockInventory]:
        """Lista inventários em andamento."""
        return (
            self.db.query(StockInventory)
            .filter(
                and_(
                    StockInventory.condominio_id == condominio_id,
                    StockInventory.ativo.is_(True),
                    StockInventory.status.in_(
                        [
                            _db_label(InventoryStatus.EM_ANDAMENTO),
                            _db_label(InventoryStatus.CONTAGEM),
                            _db_label(InventoryStatus.RECONFERENCIA),
                        ]
                    ),
                )
            )
            .all()
        )

    def count(
        self,
        condominio_id: uuid.UUID,
        status: InventoryStatus | None = None,
    ) -> int:
        """Conta inventários."""
        query = self.db.query(func.count(StockInventory.id)).filter(
            and_(
                StockInventory.condominio_id == condominio_id,
                StockInventory.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(StockInventory.status == _db_label(status))

        return query.scalar() or 0

    def update(self, inventory: StockInventory) -> StockInventory:
        """Atualiza inventário."""
        inventory.updated_at = datetime.utcnow()
        self.db.flush()
        return inventory

    def delete(self, inventory: StockInventory) -> None:
        """Soft delete de inventário."""
        inventory.ativo = False
        inventory.updated_at = datetime.utcnow()
        self.db.flush()

    def get_stats(self, condominio_id: uuid.UUID) -> dict:
        """Retorna estatísticas de inventários."""
        total = self.count(condominio_id)
        in_progress = self.count(condominio_id, InventoryStatus.EM_ANDAMENTO) + self.count(
            condominio_id, InventoryStatus.CONTAGEM
        )
        finalized = self.count(condominio_id, InventoryStatus.FINALIZADO)

        # Acuracidade média dos finalizados
        avg_accuracy = (
            self.db.query(func.avg(StockInventory.accuracy_rate))
            .filter(
                and_(
                    StockInventory.condominio_id == condominio_id,
                    StockInventory.status == _db_label(InventoryStatus.FINALIZADO),
                    StockInventory.accuracy_rate.isnot(None),
                )
            )
            .scalar()
        )

        return {
            "total_inventories": total,
            "in_progress": in_progress,
            "finalized": finalized,
            "average_accuracy": float(avg_accuracy or 0),
        }

    def generate_next_number(self, condominio_id: uuid.UUID) -> str:
        """Gera próximo número de inventário."""
        year = datetime.utcnow().year
        prefix = f"INV-{year}-"

        last = (
            self.db.query(StockInventory)
            .filter(
                and_(
                    StockInventory.condominio_id == condominio_id,
                    StockInventory.number.like(f"{prefix}%"),
                )
            )
            .order_by(StockInventory.number.desc())
            .first()
        )

        if last and last.number:
            try:
                num = int(last.number.split("-")[-1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1

        return f"{prefix}{num:04d}"


# =============================================================================
# StockInventoryItem Repository
# =============================================================================


class StockInventoryItemRepository:
    """Repository para operações de StockInventoryItem."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, item: StockInventoryItem) -> StockInventoryItem:
        """Cria um novo item de inventário."""
        self.db.add(item)
        self.db.flush()
        return item

    def create_batch(self, items: list[StockInventoryItem]) -> list[StockInventoryItem]:
        """Cria múltiplos itens."""
        self.db.add_all(items)
        self.db.flush()
        return items

    def get_by_id(self, item_id: uuid.UUID) -> StockInventoryItem | None:
        """Busca item por ID."""
        return self.db.query(StockInventoryItem).filter(StockInventoryItem.id == item_id).first()

    def list_by_inventory(
        self,
        inventory_id: uuid.UUID,
        status: InventoryItemStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockInventoryItem]:
        """Lista itens de um inventário."""
        query = self.db.query(StockInventoryItem).filter(
            and_(
                StockInventoryItem.inventory_id == inventory_id,
                StockInventoryItem.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(StockInventoryItem.status == status.value)

        return query.order_by(StockInventoryItem.location_code).offset(skip).limit(limit).all()

    def list_pending(self, inventory_id: uuid.UUID) -> list[StockInventoryItem]:
        """Lista itens pendentes de contagem."""
        return (
            self.db.query(StockInventoryItem)
            .filter(
                and_(
                    StockInventoryItem.inventory_id == inventory_id,
                    StockInventoryItem.status == InventoryItemStatus.PENDENTE.value,
                    StockInventoryItem.ativo.is_(True),
                )
            )
            .order_by(StockInventoryItem.location_code)
            .all()
        )

    def list_divergent(self, inventory_id: uuid.UUID) -> list[StockInventoryItem]:
        """Lista itens com divergência."""
        return (
            self.db.query(StockInventoryItem)
            .filter(
                and_(
                    StockInventoryItem.inventory_id == inventory_id,
                    StockInventoryItem.status == InventoryItemStatus.DIVERGENTE.value,
                    StockInventoryItem.ativo.is_(True),
                )
            )
            .all()
        )

    def update(self, item: StockInventoryItem) -> StockInventoryItem:
        """Atualiza item de inventário."""
        item.updated_at = datetime.utcnow()
        self.db.flush()
        return item

    def delete(self, item: StockInventoryItem) -> None:
        """Soft delete de item."""
        item.ativo = False
        item.updated_at = datetime.utcnow()
        self.db.flush()


# =============================================================================
# StockReservation Repository
# =============================================================================


class StockReservationRepository:
    """Repository para operações de StockReservation."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, reservation: StockReservation) -> StockReservation:
        """Cria uma nova reserva."""
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def get_by_id(self, reservation_id: uuid.UUID) -> StockReservation | None:
        """Busca reserva por ID."""
        return self.db.query(StockReservation).filter(StockReservation.id == reservation_id).first()

    def get_by_number(self, number: str, condominio_id: uuid.UUID) -> StockReservation | None:
        """Busca reserva por número."""
        return (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.number == number,
                    StockReservation.condominio_id == condominio_id,
                )
            )
            .first()
        )

    def list_all(
        self,
        condominio_id: uuid.UUID,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        status: ReservationStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StockReservation]:
        """Lista reservas com filtros."""
        query = self.db.query(StockReservation).filter(
            and_(
                StockReservation.condominio_id == condominio_id,
                StockReservation.ativo.is_(True),
            )
        )

        if product_id:
            query = query.filter(StockReservation.product_id == product_id)
        if warehouse_id:
            query = query.filter(StockReservation.warehouse_id == warehouse_id)
        if status:
            query = query.filter(StockReservation.status == _db_label(status))

        return query.order_by(StockReservation.required_date.asc()).offset(skip).limit(limit).all()

    def list_active(self, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> list[StockReservation]:
        """Lista reservas ativas de um produto em um armazém."""
        return (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.product_id == product_id,
                    StockReservation.warehouse_id == warehouse_id,
                    StockReservation.status == _db_label(ReservationStatus.ATIVA),
                    StockReservation.ativo.is_(True),
                )
            )
            .order_by(StockReservation.required_date.asc())
            .all()
        )

    def list_expiring(self, condominio_id: uuid.UUID, days: int = 7) -> list[StockReservation]:
        """Lista reservas prestes a expirar."""
        expiry_limit = datetime.utcnow() + timedelta(days=days)
        return (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.condominio_id == condominio_id,
                    StockReservation.status == _db_label(ReservationStatus.ATIVA),
                    StockReservation.expiry_date.isnot(None),
                    StockReservation.expiry_date <= expiry_limit,
                    StockReservation.ativo.is_(True),
                )
            )
            .order_by(StockReservation.expiry_date)
            .all()
        )

    def list_overdue(self, condominio_id: uuid.UUID) -> list[StockReservation]:
        """Lista reservas atrasadas."""
        return (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.condominio_id == condominio_id,
                    StockReservation.status == _db_label(ReservationStatus.ATIVA),
                    StockReservation.required_date.isnot(None),
                    StockReservation.required_date < datetime.utcnow(),
                    StockReservation.ativo.is_(True),
                )
            )
            .order_by(StockReservation.required_date)
            .all()
        )

    def list_by_reference(
        self,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> list[StockReservation]:
        """Lista reservas por referência."""
        return (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.reference_type == reference_type,
                    StockReservation.reference_id == reference_id,
                    StockReservation.ativo.is_(True),
                )
            )
            .all()
        )

    def get_reserved_quantity(self, product_id: uuid.UUID, warehouse_id: uuid.UUID) -> Decimal:
        """Retorna quantidade total reservada."""
        result = (
            self.db.query(func.coalesce(func.sum(StockReservation.quantity_reserved), 0))
            .filter(
                and_(
                    StockReservation.product_id == product_id,
                    StockReservation.warehouse_id == warehouse_id,
                    StockReservation.status == _db_label(ReservationStatus.ATIVA),
                    StockReservation.ativo.is_(True),
                )
            )
            .scalar()
        )
        return Decimal(str(result))

    def count(
        self,
        condominio_id: uuid.UUID,
        status: ReservationStatus | None = None,
    ) -> int:
        """Conta reservas."""
        query = self.db.query(func.count(StockReservation.id)).filter(
            and_(
                StockReservation.condominio_id == condominio_id,
                StockReservation.ativo.is_(True),
            )
        )

        if status:
            query = query.filter(StockReservation.status == _db_label(status))

        return query.scalar() or 0

    def update(self, reservation: StockReservation) -> StockReservation:
        """Atualiza reserva."""
        reservation.updated_at = datetime.utcnow()
        self.db.flush()
        return reservation

    def delete(self, reservation: StockReservation) -> None:
        """Soft delete de reserva."""
        reservation.ativo = False
        reservation.updated_at = datetime.utcnow()
        self.db.flush()

    def get_stats(self, condominio_id: uuid.UUID) -> dict:
        """Retorna estatísticas de reservas."""
        total = self.count(condominio_id)
        active = self.count(condominio_id, ReservationStatus.ATIVA)
        fulfilled = self.count(condominio_id, ReservationStatus.ATENDIDA)
        expired = self.count(condominio_id, ReservationStatus.EXPIRADA)
        overdue = len(self.list_overdue(condominio_id))

        # Valor reservado
        reserved_value = (
            self.db.query(
                func.coalesce(
                    func.sum(StockReservation.quantity_reserved),
                    0,
                )
            )
            .filter(
                and_(
                    StockReservation.condominio_id == condominio_id,
                    StockReservation.status == _db_label(ReservationStatus.ATIVA),
                    StockReservation.ativo.is_(True),
                )
            )
            .scalar()
        )

        return {
            "total_reservations": total,
            "active_reservations": active,
            "fulfilled_reservations": fulfilled,
            "expired_reservations": expired,
            "overdue_reservations": overdue,
            "reserved_value": float(reserved_value or 0),
        }

    def generate_next_number(self, condominio_id: uuid.UUID) -> str:
        """Gera próximo número de reserva."""
        year = datetime.utcnow().year
        prefix = f"RES-{year}-"

        last = (
            self.db.query(StockReservation)
            .filter(
                and_(
                    StockReservation.condominio_id == condominio_id,
                    StockReservation.number.like(f"{prefix}%"),
                )
            )
            .order_by(StockReservation.number.desc())
            .first()
        )

        if last and last.number:
            try:
                num = int(last.number.split("-")[-1]) + 1
            except (IndexError, ValueError):
                num = 1
        else:
            num = 1

        return f"{prefix}{num:05d}"
