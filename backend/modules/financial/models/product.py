"""Model para produtos/serviços."""

import uuid
from sqlalchemy import Integer
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.product_category import ProductCategory


class ProductType(StrEnum):
    """Tipo de produto."""

    PRODUTO = "produto"
    SERVICO = "servico"
    KIT = "kit"
    MATERIAL = "material"
    EQUIPAMENTO = "equipamento"


class ProductStatus(StrEnum):
    """Status do produto."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    DESCONTINUADO = "descontinuado"
    EM_HOMOLOGACAO = "em_homologacao"
    BLOQUEADO = "bloqueado"


class UnitOfMeasure(StrEnum):
    """Unidade de medida."""

    UNIDADE = "un"
    PECA = "pc"
    CAIXA = "cx"
    PACOTE = "pct"
    METRO = "m"
    METRO_QUADRADO = "m2"
    METRO_CUBICO = "m3"
    QUILOGRAMA = "kg"
    GRAMA = "g"
    LITRO = "l"
    MILILITRO = "ml"
    HORA = "hr"
    DIA = "dia"
    MES = "mes"
    SERVICO = "sv"
    VERBA = "vb"


class Product(Base):
    """Produto ou serviço para compras."""

    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Categoria
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id"),
        nullable=True,
        index=True,
    )

    # Identificação
    code = Column(String(50), nullable=True, index=True)  # SKU ou código interno
    barcode = Column(String(50), nullable=True)  # Código de barras (EAN, UPC)
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), nullable=True)  # Nome abreviado
    description = Column(Text, nullable=True)
    technical_specs = Column(Text, nullable=True)  # Especificações técnicas
    product_type = Column(String(20), nullable=False, default=ProductType.PRODUTO.value)
    status = Column(String(20), nullable=False, default=ProductStatus.ATIVO.value)

    # Unidade
    unit_of_measure = Column(String(10), nullable=False, default=UnitOfMeasure.UNIDADE.value)
    conversion_factor = Column(Numeric(10, 4), default=1)  # Fator de conversão

    # Preços de referência
    reference_price = Column(Numeric(15, 2), nullable=True)  # Preço de referência
    last_purchase_price = Column(Numeric(15, 2), nullable=True)  # Último preço de compra
    average_price = Column(Numeric(15, 2), nullable=True)  # Preço médio
    min_price = Column(Numeric(15, 2), nullable=True)  # Menor preço histórico
    max_price = Column(Numeric(15, 2), nullable=True)  # Maior preço histórico

    # Estoque mínimo (para alertas de reposição)
    current_stock = Column(Numeric(10, 2), default=0)  # Estoque atual
    min_stock = Column(Numeric(10, 2), default=0)
    max_stock = Column(Numeric(10, 2), nullable=True)
    reorder_point = Column(Numeric(10, 2), nullable=True)  # Ponto de pedido
    lead_time_days = Column(Integer, nullable=True)  # Prazo médio de entrega

    # Fiscal
    ncm = Column(String(10), nullable=True)  # NCM (Nomenclatura Comum do Mercosul)
    cest = Column(String(10), nullable=True)  # CEST (Substituição Tributária)
    origin = Column(String(5), nullable=True)  # Origem (0-Nacional, 1-Importado, etc.)
    cfop_default = Column(String(10), nullable=True)  # CFOP padrão

    # Fornecedor preferencial
    preferred_supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)

    # Imagens e documentos
    image_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    documents = Column(JSONB, default=list)  # [{type, url, name}]

    # Tags e atributos
    tags = Column(JSONB, default=list)  # ["urgente", "importado"]
    attributes = Column(JSONB, default=dict)  # {cor: "azul", tamanho: "M"}
    brand = Column(String(100), nullable=True)  # Marca
    manufacturer = Column(String(100), nullable=True)  # Fabricante
    model = Column(String(100), nullable=True)  # Modelo

    # Observações
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)  # Notas internas

    # Bloqueio
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    blocked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Estatísticas
    total_purchases = Column(String(10), default="0")  # Total de compras
    last_purchase_at = Column(DateTime, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    category: Optional["ProductCategory"] = relationship("ProductCategory", back_populates="products")

    __table_args__ = (
        Index("ix_products_code", "code"),
        Index("ix_products_barcode", "barcode"),
        Index("ix_products_name", "name"),
        Index("ix_products_status", "status"),
        Index("ix_products_condominio_status", "condominio_id", "status"),
        Index("ix_products_category", "category_id"),
    )

    def __repr__(self) -> str:
        return f"<Product {self.code or self.name}>"

    @property
    def is_active(self) -> bool:
        """Verifica se produto está ativo."""
        return self.status == ProductStatus.ATIVO.value and self.ativo

    @property
    def is_service(self) -> bool:
        """Verifica se é serviço."""
        return self.product_type == ProductType.SERVICO.value

    @property
    def display_name(self) -> str:
        """Nome para exibição."""
        if self.code:
            return f"[{self.code}] {self.name}"
        return self.name

    @property
    def price_variation(self) -> Decimal | None:
        """Variação entre menor e maior preço."""
        if self.min_price and self.max_price and self.min_price > 0:
            return ((self.max_price - self.min_price) / self.min_price) * 100
        return None

    def update_prices(self, new_price: Decimal) -> None:
        """Atualiza preços com base em nova compra."""
        self.last_purchase_price = new_price
        self.last_purchase_at = datetime.utcnow()

        # Atualiza min/max
        if self.min_price is None or new_price < self.min_price:
            self.min_price = new_price
        if self.max_price is None or new_price > self.max_price:
            self.max_price = new_price

        # Atualiza média (simplificado - idealmente usar média ponderada)
        if self.average_price:
            self.average_price = (self.average_price + new_price) / 2
        else:
            self.average_price = new_price

    def block(self, reason: str, user_id: uuid.UUID) -> None:
        """Bloqueia o produto."""
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_at = datetime.utcnow()
        self.blocked_by = user_id
        self.status = ProductStatus.BLOQUEADO.value

    def unblock(self) -> None:
        """Desbloqueia o produto."""
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None
        self.status = ProductStatus.ATIVO.value

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "code": self.code,
            "barcode": self.barcode,
            "name": self.name,
            "short_name": self.short_name,
            "product_type": self.product_type,
            "status": self.status,
            "unit_of_measure": self.unit_of_measure,
            "reference_price": float(self.reference_price) if self.reference_price else None,
            "last_purchase_price": (float(self.last_purchase_price) if self.last_purchase_price else None),
            "average_price": float(self.average_price) if self.average_price else None,
            "category_id": str(self.category_id) if self.category_id else None,
            "is_active": self.is_active,
            "is_service": self.is_service,
        }
