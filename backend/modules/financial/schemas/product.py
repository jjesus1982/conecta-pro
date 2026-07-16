"""Schemas para produtos."""

from datetime import datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.product import ProductStatus, ProductType, UnitOfMeasure


class ProductBase(BaseModel):
    """Schema base para produto."""

    name: str = Field(..., min_length=1, max_length=200)
    short_name: str | None = Field(None, max_length=50)
    description: str | None = None
    technical_specs: str | None = None
    product_type: ProductType = ProductType.PRODUTO
    code: str | None = Field(None, max_length=50)
    barcode: str | None = Field(None, max_length=50)
    unit_of_measure: UnitOfMeasure = UnitOfMeasure.UNIDADE
    conversion_factor: Money = Decimal("1")
    category_id: UUID | None = None
    reference_price: MoneyOpt = Field(None, ge=0)
    min_stock: Money = Decimal("0")
    max_stock: MoneyOpt = Field(None, ge=0)
    reorder_point: MoneyOpt = Field(None, ge=0)
    lead_time_days: str | None = None
    ncm: str | None = Field(None, max_length=10)
    cest: str | None = Field(None, max_length=10)
    origin: str | None = Field(None, max_length=5)
    cfop_default: str | None = Field(None, max_length=10)
    preferred_supplier_id: UUID | None = None
    image_url: str | None = Field(None, max_length=500)
    brand: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    tags: list[str] = []
    attributes: dict[str, Any] = {}
    notes: str | None = None


class ProductCreate(ProductBase):
    """Schema para criar produto."""

    condominio_id: UUID


class ProductUpdate(BaseModel):
    """Schema para atualizar produto."""

    name: str | None = Field(None, min_length=1, max_length=200)
    short_name: str | None = None
    description: str | None = None
    technical_specs: str | None = None
    product_type: ProductType | None = None
    status: ProductStatus | None = None
    code: str | None = None
    barcode: str | None = None
    unit_of_measure: UnitOfMeasure | None = None
    category_id: UUID | None = None
    reference_price: MoneyOpt = None
    min_stock: MoneyOpt = None
    max_stock: MoneyOpt = None
    reorder_point: MoneyOpt = None
    lead_time_days: str | None = None
    ncm: str | None = None
    preferred_supplier_id: UUID | None = None
    image_url: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    tags: list[str] | None = None
    attributes: dict[str, Any] | None = None
    notes: str | None = None


class ProductResponse(ProductBase):
    """Schema de resposta para produto."""

    id: UUID
    condominio_id: UUID
    status: ProductStatus
    last_purchase_price: MoneyOpt = None
    average_price: MoneyOpt = None
    min_price: MoneyOpt = None
    max_price: MoneyOpt = None
    total_purchases: str = "0"
    last_purchase_at: datetime | None = None
    is_blocked: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class ProductListResponse(BaseModel):
    """Schema de resposta para lista de produtos."""

    items: list[ProductResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ProductStats(BaseModel):
    """Estatísticas de produtos."""

    total_products: int = 0
    active_products: int = 0
    blocked_products: int = 0
    by_type: dict[str, int] = {}
    by_category: dict[str, int] = {}
    low_stock_count: int = 0


class ProductBlockRequest(BaseModel):
    """Request para bloquear produto."""

    reason: str = Field(..., min_length=5, max_length=500)


class ProductPriceHistory(BaseModel):
    """Histórico de preços do produto."""

    product_id: UUID
    prices: list[dict[str, Any]] = []
    min_price: MoneyOpt = None
    max_price: MoneyOpt = None
    average_price: MoneyOpt = None
    price_variation: MoneyOpt = None
