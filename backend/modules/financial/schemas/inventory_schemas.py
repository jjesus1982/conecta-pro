"""Schemas Pydantic para o módulo de Estoque."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.stock_inventory import (
    InventoryItemStatus,
    InventoryStatus,
    InventoryType,
)
from modules.financial.models.stock_item import CostingMethod, StockItemStatus
from modules.financial.models.stock_movement import MovementReason, MovementStatus, MovementType
from modules.financial.models.stock_reservation import (
    ReservationPriority,
    ReservationStatus,
    ReservationType,
)
from modules.financial.models.warehouse import StorageType, WarehouseStatus, WarehouseType

# =============================================================================
# Warehouse Schemas
# =============================================================================


class WarehouseBase(BaseModel):
    """Base schema para Warehouse."""

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    short_name: str | None = Field(None, max_length=30)
    description: str | None = None
    warehouse_type: WarehouseType = WarehouseType.PRINCIPAL
    storage_type: StorageType = StorageType.NORMAL

    # Localização
    address: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=2)
    zip_code: str | None = Field(None, max_length=10)
    latitude: MoneyOpt = None
    longitude: MoneyOpt = None

    # Contato
    manager_name: str | None = Field(None, max_length=100)
    manager_email: str | None = Field(None, max_length=200)
    manager_phone: str | None = Field(None, max_length=20)
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=200)

    # Capacidade
    total_area_m2: MoneyOpt = None
    storage_area_m2: MoneyOpt = None
    total_positions: str | None = "0"
    max_weight_kg: MoneyOpt = None

    # Estrutura de endereçamento
    has_addressing: bool = False
    addressing_format: str | None = None

    # Configurações de temperatura
    min_temperature: MoneyOpt = None
    max_temperature: MoneyOpt = None

    # Segurança
    has_cctv: bool = False
    has_alarm: bool = False
    has_fire_system: bool = False

    # Horários
    opening_time: str | None = None
    closing_time: str | None = None
    works_24h: bool = False

    # Custos
    monthly_cost: MoneyOpt = Field(default=Decimal("0"))
    cost_center: str | None = None

    # Configurações
    allows_negative_stock: bool = False
    fifo_enabled: bool = True
    auto_reorder: bool = False

    # Observações
    notes: str | None = None


class WarehouseCreate(WarehouseBase):
    """Schema para criar Warehouse."""


class WarehouseUpdate(BaseModel):
    """Schema para atualizar Warehouse."""

    name: str | None = Field(None, max_length=100)
    short_name: str | None = Field(None, max_length=30)
    description: str | None = None
    warehouse_type: WarehouseType | None = None
    storage_type: StorageType | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    manager_name: str | None = None
    manager_email: str | None = None
    manager_phone: str | None = None
    phone: str | None = None
    email: str | None = None
    total_area_m2: MoneyOpt = None
    storage_area_m2: MoneyOpt = None
    total_positions: str | None = None
    has_addressing: bool | None = None
    addressing_format: str | None = None
    min_temperature: MoneyOpt = None
    max_temperature: MoneyOpt = None
    opening_time: str | None = None
    closing_time: str | None = None
    works_24h: bool | None = None
    monthly_cost: MoneyOpt = None
    cost_center: str | None = None
    allows_negative_stock: bool | None = None
    fifo_enabled: bool | None = None
    auto_reorder: bool | None = None
    notes: str | None = None


class WarehouseResponse(WarehouseBase):
    """Schema de resposta para Warehouse."""

    id: UUID
    condominio_id: UUID
    status: WarehouseStatus
    occupied_positions: str | None = "0"
    current_weight_kg: MoneyOpt = None
    current_temperature: MoneyOpt = None
    total_items: str | None = "0"
    total_quantity: MoneyOpt = None
    total_value: MoneyOpt = None
    last_movement_at: datetime | None = None
    last_inventory_at: datetime | None = None
    is_blocked: bool = False
    blocked_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    ativo: bool = True

    # Propriedades calculadas
    is_active: bool = True
    is_main: bool = False
    occupancy_rate: float | None = None
    is_full: bool = False
    available_positions: int = 0
    is_climate_controlled: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class WarehouseListResponse(BaseModel):
    """Schema para listagem de Warehouses."""

    id: UUID
    code: str
    name: str
    warehouse_type: str
    status: str
    storage_type: str
    city: str | None = None
    total_items: str | None = "0"
    total_value: MoneyOpt = None
    occupancy_rate: float | None = None
    is_active: bool = True

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# StockItem Schemas
# =============================================================================


class StockItemBase(BaseModel):
    """Base schema para StockItem."""

    product_id: UUID
    warehouse_id: UUID
    batch_number: str | None = Field(None, max_length=50)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    serial_number: str | None = Field(None, max_length=100)

    # Localização
    location_code: str | None = Field(None, max_length=50)
    aisle: str | None = Field(None, max_length=10)
    rack: str | None = Field(None, max_length=10)
    shelf: str | None = Field(None, max_length=10)
    bin: str | None = Field(None, max_length=10)

    # Parâmetros de estoque
    min_quantity: MoneyOpt = None
    max_quantity: MoneyOpt = None
    reorder_point: MoneyOpt = None
    reorder_quantity: MoneyOpt = None
    safety_stock: MoneyOpt = None

    # Custeio
    costing_method: CostingMethod = CostingMethod.CUSTO_MEDIO

    # Classificação
    abc_class: str | None = Field(None, max_length=1)
    xyz_class: str | None = Field(None, max_length=1)

    notes: str | None = None


class StockItemCreate(StockItemBase):
    """Schema para criar StockItem."""

    quantity_on_hand: Money = Field(default=Decimal("0"))
    unit_cost: Money = Field(default=Decimal("0"))


class StockItemUpdate(BaseModel):
    """Schema para atualizar StockItem."""

    batch_number: str | None = None
    expiry_date: date | None = None
    location_code: str | None = None
    aisle: str | None = None
    rack: str | None = None
    shelf: str | None = None
    bin: str | None = None
    min_quantity: MoneyOpt = None
    max_quantity: MoneyOpt = None
    reorder_point: MoneyOpt = None
    reorder_quantity: MoneyOpt = None
    safety_stock: MoneyOpt = None
    abc_class: str | None = None
    xyz_class: str | None = None
    notes: str | None = None


class StockItemResponse(StockItemBase):
    """Schema de resposta para StockItem."""

    id: UUID
    condominio_id: UUID
    status: StockItemStatus
    quantity_on_hand: Money
    quantity_reserved: Money
    quantity_committed: Money
    quantity_on_order: Money
    quantity_in_transit: Money
    unit_cost: Money
    average_cost: Money
    last_cost: Money
    total_cost: Money
    last_receipt_date: datetime | None = None
    last_issue_date: datetime | None = None
    last_count_date: datetime | None = None
    receipt_count: str | None = "0"
    issue_count: str | None = "0"
    is_blocked: bool = False
    blocked_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    ativo: bool = True

    # Propriedades calculadas
    quantity_available: float = 0
    is_available: bool = True
    is_low_stock: bool = False
    is_below_reorder_point: bool = False
    is_overstocked: bool = False
    is_expired: bool = False
    days_to_expiry: int | None = None
    is_expiring_soon: bool = False
    full_location: str = ""
    classification: str = "--"

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class StockItemListResponse(BaseModel):
    """Schema para listagem de StockItems."""

    id: UUID
    product_id: UUID
    warehouse_id: UUID
    name: str | None = None
    code: str | None = None
    batch_number: str | None = None
    status: str
    quantity_on_hand: float
    quantity_available: float
    unit_cost: float
    total_cost: float
    expiry_date: date | None = None
    full_location: str = ""
    is_low_stock: bool = False
    is_expired: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# StockMovement Schemas
# =============================================================================


class StockMovementBase(BaseModel):
    """Base schema para StockMovement."""

    movement_type: MovementType
    reason: MovementReason = MovementReason.OUTRO
    product_id: UUID
    warehouse_id: UUID
    destination_warehouse_id: UUID | None = None
    movement_date: date
    batch_number: str | None = Field(None, max_length=50)
    expiry_date: date | None = None
    serial_number: str | None = Field(None, max_length=100)
    quantity: Money = Field(..., gt=0)
    unit_of_measure: str = Field(default="un", max_length=10)
    unit_cost: Money = Field(default=Decimal("0"))

    # Localização origem
    source_location: str | None = None
    source_aisle: str | None = None
    source_rack: str | None = None
    source_shelf: str | None = None
    source_bin: str | None = None

    # Localização destino
    dest_location: str | None = None
    dest_aisle: str | None = None
    dest_rack: str | None = None
    dest_shelf: str | None = None
    dest_bin: str | None = None

    # Referências
    reference_type: str | None = None
    reference_id: UUID | None = None
    reference_number: str | None = None
    invoice_number: str | None = None
    invoice_series: str | None = None
    invoice_key: str | None = None

    supplier_id: UUID | None = None
    customer_id: UUID | None = None
    requisition_number: str | None = None

    requires_approval: bool = False
    description: str | None = None
    notes: str | None = None


class StockMovementCreate(StockMovementBase):
    """Schema para criar StockMovement."""


class StockMovementUpdate(BaseModel):
    """Schema para atualizar StockMovement."""

    movement_date: date | None = None
    batch_number: str | None = None
    quantity: MoneyOpt = None
    unit_cost: MoneyOpt = None
    description: str | None = None
    notes: str | None = None


class StockMovementResponse(StockMovementBase):
    """Schema de resposta para StockMovement."""

    id: UUID
    condominio_id: UUID
    number: str
    status: MovementStatus
    total_cost: Money
    balance_before: MoneyOpt = None
    balance_after: MoneyOpt = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    is_reversal: bool = False
    reversal_of: UUID | None = None
    reversed_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    created_by: UUID | None = None
    ativo: bool = True

    # Propriedades calculadas
    is_entry: bool = False
    is_exit: bool = False
    is_transfer: bool = False
    is_adjustment: bool = False
    is_pending: bool = False
    is_confirmed: bool = False
    can_confirm: bool = True
    can_cancel: bool = True
    can_reverse: bool = False
    source_full_location: str = ""
    dest_full_location: str = ""
    signed_quantity: float = 0

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class StockMovementListResponse(BaseModel):
    """Schema para listagem de StockMovements."""

    id: UUID
    number: str
    movement_type: str
    reason: str
    status: str
    product_id: UUID
    warehouse_id: UUID
    movement_date: date
    quantity: float
    unit_cost: float
    total_cost: float
    reference_number: str | None = None
    is_confirmed: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# StockInventory Schemas
# =============================================================================


class StockInventoryBase(BaseModel):
    """Base schema para StockInventory."""

    warehouse_id: UUID
    description: str | None = Field(None, max_length=200)
    inventory_type: InventoryType = InventoryType.GERAL
    planned_date: date | None = None
    deadline: datetime | None = None

    # Filtros
    filter_categories: list | None = None
    filter_locations: list | None = None
    filter_abc_class: list | None = None
    filter_products: list | None = None

    # Responsável
    supervisor_id: UUID | None = None
    team_members: list | None = None

    # Configurações
    requires_approval: bool = True
    allow_recount: bool = True
    require_double_count: bool = False
    blind_count: bool = False
    auto_adjust: bool = False

    notes: str | None = None


class StockInventoryCreate(StockInventoryBase):
    """Schema para criar StockInventory."""


class StockInventoryUpdate(BaseModel):
    """Schema para atualizar StockInventory."""

    description: str | None = None
    planned_date: date | None = None
    deadline: datetime | None = None
    supervisor_id: UUID | None = None
    team_members: list | None = None
    notes: str | None = None


class StockInventoryResponse(StockInventoryBase):
    """Schema de resposta para StockInventory."""

    id: UUID
    condominio_id: UUID
    number: str
    status: InventoryStatus
    start_date: datetime | None = None
    end_date: datetime | None = None
    total_items: int = 0
    counted_items: int = 0
    verified_items: int = 0
    divergent_items: int = 0
    adjusted_items: int = 0
    expected_value: Money = Decimal("0")
    counted_value: Money = Decimal("0")
    difference_value: Money = Decimal("0")
    expected_quantity: Money = Decimal("0")
    counted_quantity: Money = Decimal("0")
    difference_quantity: Money = Decimal("0")
    accuracy_rate: MoneyOpt = None
    hit_rate: MoneyOpt = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
    created_by: UUID | None = None
    ativo: bool = True

    # Propriedades calculadas
    is_in_progress: bool = False
    is_finalized: bool = False
    is_cancelled: bool = False
    progress_percentage: float = 0
    has_divergences: bool = False
    can_start: bool = True
    can_finish: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class StockInventoryListResponse(BaseModel):
    """Schema para listagem de StockInventories."""

    id: UUID
    number: str
    description: str | None = None
    inventory_type: str
    status: str
    warehouse_id: UUID
    planned_date: date | None = None
    total_items: int = 0
    counted_items: int = 0
    divergent_items: int = 0
    progress_percentage: float = 0
    accuracy_rate: float | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# StockInventoryItem Schemas
# =============================================================================


class StockInventoryItemBase(BaseModel):
    """Base schema para StockInventoryItem."""

    product_id: UUID
    stock_item_id: UUID | None = None
    batch_number: str | None = None
    expiry_date: date | None = None
    location_code: str | None = None
    aisle: str | None = None
    rack: str | None = None
    shelf: str | None = None
    bin_loc: str | None = None
    expected_quantity: Money = Decimal("0")
    unit_cost: Money = Decimal("0")


class StockInventoryItemCreate(StockInventoryItemBase):
    """Schema para criar StockInventoryItem."""

    inventory_id: UUID


class StockInventoryItemCount(BaseModel):
    """Schema para registrar contagem."""

    counted_quantity: Money = Field(..., ge=0)
    notes: str | None = None


class StockInventoryItemResponse(StockInventoryItemBase):
    """Schema de resposta para StockInventoryItem."""

    id: UUID
    inventory_id: UUID
    status: InventoryItemStatus
    expected_value: Money = Decimal("0")
    counted_quantity: MoneyOpt = None
    recount_quantity: MoneyOpt = None
    difference_quantity: MoneyOpt = None
    adjusted_quantity: MoneyOpt = None
    counted_value: MoneyOpt = None
    difference_value: MoneyOpt = None
    counted_at: datetime | None = None
    counted_by: UUID | None = None
    recounted_at: datetime | None = None
    recounted_by: UUID | None = None
    verified_at: datetime | None = None
    verified_by: UUID | None = None
    adjustment_reason: str | None = None
    adjusted_at: datetime | None = None
    adjusted_by: UUID | None = None
    notes: str | None = None
    created_at: datetime
    ativo: bool = True

    # Propriedades calculadas
    is_counted: bool = False
    is_recounted: bool = False
    is_verified: bool = False
    is_adjusted: bool = False
    has_divergence: bool = False
    divergence_percentage: float | None = None
    full_location: str = ""

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# StockReservation Schemas
# =============================================================================


class StockReservationBase(BaseModel):
    """Base schema para StockReservation."""

    description: str | None = Field(None, max_length=200)
    reservation_type: ReservationType
    priority: ReservationPriority = ReservationPriority.MEDIA
    product_id: UUID
    warehouse_id: UUID
    stock_item_id: UUID | None = None
    batch_number: str | None = None
    quantity_requested: Money = Field(..., gt=0)
    unit_of_measure: str = Field(default="un", max_length=10)
    required_date: datetime | None = None
    expiry_date: datetime | None = None

    # Referência
    reference_type: str | None = None
    reference_id: UUID | None = None
    reference_number: str | None = None

    # Solicitante
    requester_id: UUID | None = None
    requester_name: str | None = None
    department: str | None = None
    cost_center: str | None = None

    # Configurações
    requires_approval: bool = False
    auto_release: bool = False
    auto_expire: bool = True
    allow_partial: bool = True

    notes: str | None = None


class StockReservationCreate(StockReservationBase):
    """Schema para criar StockReservation."""


class StockReservationUpdate(BaseModel):
    """Schema para atualizar StockReservation."""

    description: str | None = None
    priority: ReservationPriority | None = None
    required_date: datetime | None = None
    expiry_date: datetime | None = None
    notes: str | None = None


class StockReservationRelease(BaseModel):
    """Schema para liberar reserva."""

    quantity: Money = Field(..., gt=0)
    notes: str | None = None


class StockReservationResponse(StockReservationBase):
    """Schema de resposta para StockReservation."""

    id: UUID
    condominio_id: UUID
    number: str
    status: ReservationStatus
    quantity_reserved: Money = Decimal("0")
    quantity_released: Money = Decimal("0")
    quantity_pending: Money = Decimal("0")
    reservation_date: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    released_by: UUID | None = None
    released_at: datetime | None = None
    release_notes: str | None = None
    cancelled_by: UUID | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    created_by: UUID | None = None
    ativo: bool = True

    # Propriedades calculadas
    is_active: bool = True
    is_fulfilled: bool = False
    is_partial: bool = False
    is_expired: bool = False
    is_cancelled: bool = False
    is_released: bool = False
    fulfillment_percentage: float = 0
    is_overdue: bool = False
    days_until_required: int | None = None
    days_until_expiry: int | None = None
    is_high_priority: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class StockReservationListResponse(BaseModel):
    """Schema para listagem de StockReservations."""

    id: UUID
    number: str
    reservation_type: str
    status: str
    priority: str
    product_id: UUID
    warehouse_id: UUID
    quantity_requested: float
    quantity_reserved: float
    quantity_pending: float
    required_date: datetime | None = None
    reference_number: str | None = None
    is_overdue: bool = False

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# =============================================================================
# Stats e Filters
# =============================================================================


class WarehouseStats(BaseModel):
    """Estatísticas de armazéns."""

    total_warehouses: int = 0
    active_warehouses: int = 0
    total_items: int = 0
    total_value: float = 0
    average_occupancy: float = 0
    warehouses_near_capacity: int = 0


class StockStats(BaseModel):
    """Estatísticas de estoque."""

    total_items: int = 0
    total_quantity: float = 0
    total_value: float = 0
    low_stock_items: int = 0
    expired_items: int = 0
    expiring_soon_items: int = 0
    blocked_items: int = 0


class MovementStats(BaseModel):
    """Estatísticas de movimentações."""

    total_movements: int = 0
    entries_count: int = 0
    exits_count: int = 0
    transfers_count: int = 0
    adjustments_count: int = 0
    entries_value: float = 0
    exits_value: float = 0
    pending_movements: int = 0


class InventoryStats(BaseModel):
    """Estatísticas de inventários."""

    total_inventories: int = 0
    in_progress: int = 0
    finalized: int = 0
    average_accuracy: float = 0
    total_adjustments: int = 0
    adjustment_value: float = 0


class ReservationStats(BaseModel):
    """Estatísticas de reservas."""

    total_reservations: int = 0
    active_reservations: int = 0
    fulfilled_reservations: int = 0
    expired_reservations: int = 0
    overdue_reservations: int = 0
    reserved_value: float = 0


class StockFilter(BaseModel):
    """Filtros para consulta de estoque."""

    warehouse_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    status: StockItemStatus | None = None
    batch_number: str | None = None
    location_code: str | None = None
    abc_class: str | None = None
    is_low_stock: bool | None = None
    is_expired: bool | None = None
    is_expiring_soon: bool | None = None
    min_quantity: MoneyOpt = None
    max_quantity: MoneyOpt = None


class MovementFilter(BaseModel):
    """Filtros para consulta de movimentações."""

    warehouse_id: UUID | None = None
    product_id: UUID | None = None
    movement_type: MovementType | None = None
    reason: MovementReason | None = None
    status: MovementStatus | None = None
    reference_type: str | None = None
    reference_number: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    batch_number: str | None = None
