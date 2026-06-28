"""Model para armazéns/depósitos de estoque."""

import uuid
from sqlalchemy import Integer
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.stock_item import StockItem


class WarehouseType(StrEnum):
    """Tipo de armazém."""

    PRINCIPAL = "principal"
    SECUNDARIO = "secundario"
    TRANSITO = "transito"
    DEVOLUCAO = "devolucao"
    QUARENTENA = "quarentena"
    AVARIADO = "avariado"
    CONSIGNADO = "consignado"
    TERCEIROS = "terceiros"


class WarehouseStatus(StrEnum):
    """Status do armazém."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    BLOQUEADO = "bloqueado"
    MANUTENCAO = "manutencao"
    ENCERRADO = "encerrado"


class StorageType(StrEnum):
    """Tipo de armazenagem."""

    NORMAL = "normal"
    REFRIGERADO = "refrigerado"
    CONGELADO = "congelado"
    CLIMATIZADO = "climatizado"
    PERIGOSO = "perigoso"
    ESPECIAL = "especial"


class Warehouse(Base):
    """Armazém ou depósito de estoque."""

    __tablename__ = "fin_warehouses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificação
    code = Column(String(20), nullable=False, index=True)  # DEP-001
    name = Column(String(100), nullable=False)
    short_name = Column(String(30), nullable=True)
    description = Column(Text, nullable=True)
    warehouse_type = Column(String(20), nullable=False, default=WarehouseType.PRINCIPAL.value)
    status = Column(String(20), nullable=False, default=WarehouseStatus.ATIVO.value)
    storage_type = Column(String(20), nullable=False, default=StorageType.NORMAL.value)

    # Localização
    address = Column(String(300), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(2), nullable=True)
    zip_code = Column(String(10), nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)

    # Contato
    manager_name = Column(String(100), nullable=True)  # Responsável
    manager_email = Column(String(200), nullable=True)
    manager_phone = Column(String(20), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(200), nullable=True)

    # Capacidade
    total_area_m2 = Column(Numeric(10, 2), nullable=True)  # Área total em m²
    storage_area_m2 = Column(Numeric(10, 2), nullable=True)  # Área de armazenagem
    total_positions = Column(String(10), default="0")  # Total de posições
    occupied_positions = Column(String(10), default="0")  # Posições ocupadas
    max_weight_kg = Column(Numeric(15, 2), nullable=True)  # Peso máximo suportado
    current_weight_kg = Column(Numeric(15, 2), default=0)  # Peso atual

    # Estrutura de endereçamento
    has_addressing = Column(Boolean, default=False)  # Usa endereçamento?
    addressing_format = Column(String(50), nullable=True)  # Ex: "CORREDOR-PRATELEIRA-POSIÇÃO"
    addressing_levels = Column(Integer, default=1)
    # Ex: [{"name": "corredor", "max": 10}, {"name": "prateleira", "max": 5}, ...]

    # Configurações de temperatura (para armazéns climatizados)
    min_temperature = Column(Numeric(5, 2), nullable=True)
    max_temperature = Column(Numeric(5, 2), nullable=True)
    current_temperature = Column(Numeric(5, 2), nullable=True)
    last_temperature_check = Column(DateTime, nullable=True)

    # Segurança
    has_cctv = Column(Boolean, default=False)
    has_alarm = Column(Boolean, default=False)
    has_fire_system = Column(Boolean, default=False)
    access_control_type = Column(String(50), nullable=True)  # biometria, cartão, etc

    # Horários
    opening_time = Column(String(5), nullable=True)  # HH:MM
    closing_time = Column(String(5), nullable=True)  # HH:MM
    works_24h = Column(Boolean, default=False)
    working_days = Column(JSONB, default=list)  # [1,2,3,4,5] (seg-sex)

    # Custos
    monthly_cost = Column(Numeric(15, 2), default=0)  # Custo mensal
    cost_per_m2 = Column(Numeric(10, 2), nullable=True)
    cost_center = Column(String(50), nullable=True)  # Centro de custo

    # Estatísticas
    total_items = Column(String(10), default="0")  # Total de itens distintos
    total_quantity = Column(Numeric(15, 2), default=0)  # Quantidade total
    total_value = Column(Numeric(15, 2), default=0)  # Valor total em estoque
    last_movement_at = Column(DateTime, nullable=True)
    last_inventory_at = Column(DateTime, nullable=True)

    # Configurações
    allows_negative_stock = Column(Boolean, default=False)  # Permite estoque negativo?
    fifo_enabled = Column(Boolean, default=True)  # Usa FIFO (First In, First Out)?
    auto_reorder = Column(Boolean, default=False)  # Reposição automática?

    # Bloqueio
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    blocked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Observações
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Metadados
    extra_data = Column(JSONB, default=dict)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    stock_items: list["StockItem"] = relationship(
        "StockItem",
        back_populates="warehouse",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_warehouses_code", "code"),
        Index("ix_warehouses_name", "name"),
        Index("ix_warehouses_status", "status"),
        Index("ix_warehouses_type", "warehouse_type"),
        Index("ix_warehouses_condominio_status", "condominio_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Warehouse {self.code}: {self.name}>"

    @property
    def is_active(self) -> bool:
        """Verifica se armazém está ativo."""
        return self.status == WarehouseStatus.ATIVO.value and self.ativo

    @property
    def is_main(self) -> bool:
        """Verifica se é armazém principal."""
        return self.warehouse_type == WarehouseType.PRINCIPAL.value

    @property
    def display_name(self) -> str:
        """Nome para exibição."""
        return f"[{self.code}] {self.name}"

    @property
    def occupancy_rate(self) -> Decimal | None:
        """Taxa de ocupação (%)."""
        total = int(self.total_positions) if self.total_positions else 0
        occupied = int(self.occupied_positions) if self.occupied_positions else 0
        if total > 0:
            return Decimal(occupied / total * 100).quantize(Decimal("0.01"))
        return None

    @property
    def is_full(self) -> bool:
        """Verifica se está cheio."""
        rate = self.occupancy_rate
        return rate is not None and rate >= 100

    @property
    def available_positions(self) -> int:
        """Posições disponíveis."""
        total = int(self.total_positions) if self.total_positions else 0
        occupied = int(self.occupied_positions) if self.occupied_positions else 0
        return max(0, total - occupied)

    @property
    def is_climate_controlled(self) -> bool:
        """Verifica se é climatizado."""
        return self.storage_type in [
            StorageType.REFRIGERADO.value,
            StorageType.CONGELADO.value,
            StorageType.CLIMATIZADO.value,
        ]

    def activate(self) -> None:
        """Ativa o armazém."""
        self.status = WarehouseStatus.ATIVO.value
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None

    def deactivate(self) -> None:
        """Desativa o armazém."""
        self.status = WarehouseStatus.INATIVO.value

    def block(self, reason: str, user_id: uuid.UUID) -> None:
        """Bloqueia o armazém."""
        self.status = WarehouseStatus.BLOQUEADO.value
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_at = datetime.utcnow()
        self.blocked_by = user_id

    def unblock(self) -> None:
        """Desbloqueia o armazém."""
        self.status = WarehouseStatus.ATIVO.value
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None

    def set_maintenance(self) -> None:
        """Coloca em manutenção."""
        self.status = WarehouseStatus.MANUTENCAO.value

    def update_statistics(
        self,
        total_items: int,
        total_quantity: Decimal,
        total_value: Decimal,
    ) -> None:
        """Atualiza estatísticas do armazém."""
        self.total_items = str(total_items)
        self.total_quantity = total_quantity
        self.total_value = total_value

    def update_temperature(self, temperature: Decimal) -> None:
        """Atualiza temperatura atual."""
        self.current_temperature = temperature
        self.last_temperature_check = datetime.utcnow()

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "warehouse_type": self.warehouse_type,
            "status": self.status,
            "storage_type": self.storage_type,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "total_area_m2": float(self.total_area_m2) if self.total_area_m2 else None,
            "total_positions": self.total_positions,
            "occupied_positions": self.occupied_positions,
            "occupancy_rate": float(self.occupancy_rate) if self.occupancy_rate else None,
            "total_items": self.total_items,
            "total_value": float(self.total_value) if self.total_value else 0,
            "is_active": self.is_active,
            "is_main": self.is_main,
            "is_climate_controlled": self.is_climate_controlled,
        }
