"""Model para cotações de compra."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.purchase_order import PurchaseOrder
    from modules.financial.models.purchase_requisition import PurchaseRequisition


class QuotationStatus(StrEnum):
    """Status da cotação."""

    SOLICITADA = "solicitada"
    ENVIADA = "enviada"
    RECEBIDA = "recebida"
    EM_ANALISE = "em_analise"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
    ERRO_ENVIO = "erro_envio"  # gravado pelo envio por WhatsApp quando falha (08/09/2026)
    SELECIONADA = "selecionada"  # Vencedora
    NAO_SELECIONADA = "nao_selecionada"
    EXPIRADA = "expirada"
    CANCELADA = "cancelada"


class PaymentCondition(StrEnum):
    """Condição de pagamento."""

    A_VISTA = "a_vista"
    DIAS_7 = "7_dias"
    DIAS_14 = "14_dias"
    DIAS_21 = "21_dias"
    DIAS_28 = "28_dias"
    DIAS_30 = "30_dias"
    DIAS_45 = "45_dias"
    DIAS_60 = "60_dias"
    DIAS_90 = "90_dias"
    PARCELADO = "parcelado"
    ENTRADA_SALDO = "entrada_saldo"


class DeliveryType(StrEnum):
    """Tipo de entrega."""

    CIF = "cif"  # Frete incluso
    FOB = "fob"  # Frete por conta do comprador
    RETIRADA = "retirada"  # Cliente retira


class PurchaseQuotation(Base):
    """Cotação de compra com fornecedor."""

    __tablename__ = "purchase_quotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Requisição de origem
    requisition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_requisitions.id"),
        nullable=False,
        index=True,
    )

    # Fornecedor
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id"),
        nullable=False,
        index=True,
    )

    # Identificação
    number = Column(String(20), nullable=False, index=True)  # COT-YYYY-NNNN
    reference = Column(String(50), nullable=True)  # Referência do fornecedor
    status = Column(String(20), nullable=False, default=QuotationStatus.SOLICITADA.value)

    # Datas
    request_date = Column(Date, nullable=False, default=datetime.utcnow().date)
    sent_date = Column(DateTime, nullable=True)  # Quando foi enviada ao fornecedor
    received_date = Column(DateTime, nullable=True)  # Quando foi recebida
    validity_date = Column(Date, nullable=True)  # Validade da cotação
    expected_delivery_date = Column(Date, nullable=True)  # Prazo de entrega prometido

    # Condições comerciais
    payment_condition = Column(String(20), nullable=True, default=PaymentCondition.DIAS_30.value)
    payment_installments = Column(Integer, nullable=True)  # Número de parcelas
    delivery_type = Column(String(20), nullable=True, default=DeliveryType.CIF.value)
    delivery_days = Column(Integer, nullable=True)  # Prazo em dias úteis

    # Valores
    subtotal = Column(Numeric(15, 2), default=0)
    discount_percentage = Column(Numeric(5, 2), default=0)
    discount_amount = Column(Numeric(15, 2), default=0)
    freight_amount = Column(Numeric(15, 2), default=0)
    insurance_amount = Column(Numeric(15, 2), default=0)
    other_costs = Column(Numeric(15, 2), default=0)
    total = Column(Numeric(15, 2), default=0)

    # Impostos
    ipi_amount = Column(Numeric(15, 2), default=0)
    icms_amount = Column(Numeric(15, 2), default=0)
    pis_amount = Column(Numeric(15, 2), default=0)
    cofins_amount = Column(Numeric(15, 2), default=0)

    # Avaliação
    technical_score = Column(Numeric(5, 2), nullable=True)  # 0-100 avaliação técnica
    commercial_score = Column(Numeric(5, 2), nullable=True)  # 0-100 avaliação comercial
    delivery_score = Column(Numeric(5, 2), nullable=True)  # 0-100 prazo de entrega
    overall_score = Column(Numeric(5, 2), nullable=True)  # Score geral ponderado

    # Observações
    notes = Column(Text, nullable=True)
    supplier_notes = Column(Text, nullable=True)  # Observações do fornecedor
    internal_notes = Column(Text, nullable=True)  # Notas internas

    # Anexos
    attachments = Column(JSONB, default=list)  # [{type, url, name}]

    # Rejeição
    rejection_reason = Column(Text, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Seleção
    selected_at = Column(DateTime, nullable=True)
    selected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    selection_justification = Column(Text, nullable=True)

    # Análise comparativa
    comparison_notes = Column(Text, nullable=True)
    is_best_price = Column(Boolean, default=False)
    is_best_delivery = Column(Boolean, default=False)
    is_best_overall = Column(Boolean, default=False)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    requisition: "PurchaseRequisition" = relationship("PurchaseRequisition", back_populates="quotations")
    items: list["PurchaseQuotationItem"] = relationship(
        "PurchaseQuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
    )
    orders: list["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="quotation")

    __table_args__ = (
        Index("ix_purchase_quotations_number", "number"),
        Index("ix_purchase_quotations_status", "status"),
        Index("ix_purchase_quotations_supplier", "supplier_id"),
        Index("ix_purchase_quotations_requisition", "requisition_id"),
        Index("ix_purchase_quotations_condominio_status", "condominio_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseQuotation {self.number}>"

    @property
    def is_valid(self) -> bool:
        """Verifica se cotação ainda é válida."""
        if self.validity_date:
            return datetime.utcnow().date() <= self.validity_date
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se cotação expirou."""
        return not self.is_valid

    @property
    def is_selected(self) -> bool:
        """Verifica se foi selecionada."""
        return self.status == QuotationStatus.SELECIONADA.value

    @property
    def items_count(self) -> int:
        """Retorna quantidade de itens."""
        return len(self.items) if self.items else 0

    @property
    def total_with_taxes(self) -> Decimal:
        """Total incluindo impostos."""
        return self.total + (self.ipi_amount or Decimal("0")) + (self.icms_amount or Decimal("0"))

    @property
    def days_until_expiry(self) -> int | None:
        """Dias até expirar."""
        if self.validity_date:
            delta = self.validity_date - datetime.utcnow().date()
            return delta.days
        return None

    def send_to_supplier(self) -> None:
        """Marca como enviada ao fornecedor."""
        self.status = QuotationStatus.ENVIADA.value
        self.sent_date = datetime.utcnow()

    def receive_response(self) -> None:
        """Marca como recebida do fornecedor."""
        self.status = QuotationStatus.RECEBIDA.value
        self.received_date = datetime.utcnow()

    def start_analysis(self) -> None:
        """Inicia análise da cotação."""
        self.status = QuotationStatus.EM_ANALISE.value

    def approve(self) -> None:
        """Aprova a cotação."""
        self.status = QuotationStatus.APROVADA.value

    def reject(self, rejector_id: uuid.UUID, reason: str) -> None:
        """Rejeita a cotação."""
        self.status = QuotationStatus.REJEITADA.value
        self.rejection_reason = reason
        self.rejected_at = datetime.utcnow()
        self.rejected_by = rejector_id

    def select(self, selector_id: uuid.UUID, justification: str | None = None) -> None:
        """Seleciona como vencedora."""
        self.status = QuotationStatus.SELECIONADA.value
        self.selected_at = datetime.utcnow()
        self.selected_by = selector_id
        self.selection_justification = justification
        self.is_best_overall = True

    def mark_not_selected(self) -> None:
        """Marca como não selecionada."""
        self.status = QuotationStatus.NAO_SELECIONADA.value

    def mark_expired(self) -> None:
        """Marca como expirada."""
        self.status = QuotationStatus.EXPIRADA.value

    def cancel(self) -> None:
        """Cancela a cotação."""
        self.status = QuotationStatus.CANCELADA.value

    def calculate_total(self) -> Decimal:
        """Calcula total da cotação."""
        subtotal = Decimal("0")
        if self.items:
            for item in self.items:
                if item.total:
                    subtotal += item.total

        self.subtotal = subtotal
        self.total = (
            subtotal
            - (self.discount_amount or Decimal("0"))
            + (self.freight_amount or Decimal("0"))
            + (self.insurance_amount or Decimal("0"))
            + (self.other_costs or Decimal("0"))
        )
        return self.total

    def calculate_scores(self) -> None:
        """Calcula scores ponderados."""
        # Pesos: técnico 30%, comercial 40%, entrega 30%
        scores = []
        if self.technical_score:
            scores.append(float(self.technical_score) * 0.30)
        if self.commercial_score:
            scores.append(float(self.commercial_score) * 0.40)
        if self.delivery_score:
            scores.append(float(self.delivery_score) * 0.30)

        if scores:
            self.overall_score = Decimal(str(sum(scores)))

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "number": self.number,
            "reference": self.reference,
            "status": self.status,
            "supplier_id": str(self.supplier_id),
            "requisition_id": str(self.requisition_id),
            "request_date": self.request_date.isoformat() if self.request_date else None,
            "validity_date": self.validity_date.isoformat() if self.validity_date else None,
            "subtotal": float(self.subtotal) if self.subtotal else 0,
            "discount_amount": float(self.discount_amount) if self.discount_amount else 0,
            "freight_amount": float(self.freight_amount) if self.freight_amount else 0,
            "total": float(self.total) if self.total else 0,
            "payment_condition": self.payment_condition,
            "delivery_type": self.delivery_type,
            "delivery_days": self.delivery_days,
            "overall_score": float(self.overall_score) if self.overall_score else None,
            "is_selected": self.is_selected,
            "is_valid": self.is_valid,
            "items_count": self.items_count,
        }


class PurchaseQuotationItem(Base):
    """Item da cotação de compra."""

    __tablename__ = "purchase_quotation_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quotation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Item da requisição de origem
    requisition_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_requisition_items.id"),
        nullable=True,
        index=True,
    )

    # Produto
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)

    # Identificação
    item_number = Column(Integer, nullable=False)
    description = Column(String(500), nullable=False)
    supplier_code = Column(String(50), nullable=True)  # Código do fornecedor
    supplier_description = Column(String(500), nullable=True)  # Descrição do fornecedor
    unit_of_measure = Column(String(10), nullable=False, default="un")

    # Quantidade
    quantity_requested = Column(Numeric(10, 2), nullable=False)
    quantity_offered = Column(Numeric(10, 2), nullable=True)  # Quantidade oferecida
    min_quantity = Column(Numeric(10, 2), nullable=True)  # Quantidade mínima

    # Preços
    unit_price = Column(Numeric(15, 2), nullable=True)
    discount_percentage = Column(Numeric(5, 2), default=0)
    discount_amount = Column(Numeric(15, 2), default=0)
    total = Column(Numeric(15, 2), nullable=True)

    # Impostos do item
    ipi_percentage = Column(Numeric(5, 2), default=0)
    icms_percentage = Column(Numeric(5, 2), default=0)

    # Entrega
    delivery_days = Column(Integer, nullable=True)  # Prazo específico do item
    availability = Column(String(50), nullable=True)  # imediata, sob_encomenda, etc.

    # Observações
    notes = Column(Text, nullable=True)
    technical_specs = Column(Text, nullable=True)

    # Avaliação do item
    meets_specs = Column(Boolean, nullable=True)  # Atende especificações
    evaluation_notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    quotation: "PurchaseQuotation" = relationship("PurchaseQuotation", back_populates="items")

    __table_args__ = (
        Index("ix_purchase_quotation_items_quotation", "quotation_id"),
        Index("ix_purchase_quotation_items_product", "product_id"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseQuotationItem {self.item_number}: {self.description[:30]}>"

    @property
    def unit_price_with_discount(self) -> Decimal:
        """Preço unitário com desconto."""
        if not self.unit_price:
            return Decimal("0")
        if self.discount_percentage:
            discount = self.unit_price * (self.discount_percentage / 100)
            return self.unit_price - discount
        return self.unit_price - (self.discount_amount or Decimal("0"))

    def calculate_total(self) -> None:
        """Calcula total do item."""
        qty = self.quantity_offered or self.quantity_requested
        if qty and self.unit_price:
            subtotal = qty * self.unit_price
            if self.discount_percentage:
                self.discount_amount = subtotal * (self.discount_percentage / 100)
            self.total = subtotal - (self.discount_amount or Decimal("0"))

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "item_number": self.item_number,
            "description": self.description,
            "supplier_code": self.supplier_code,
            "unit_of_measure": self.unit_of_measure,
            "quantity_requested": float(self.quantity_requested),
            "quantity_offered": (float(self.quantity_offered) if self.quantity_offered else None),
            "unit_price": float(self.unit_price) if self.unit_price else None,
            "discount_percentage": (float(self.discount_percentage) if self.discount_percentage else 0),
            "total": float(self.total) if self.total else None,
            "delivery_days": self.delivery_days,
            "meets_specs": self.meets_specs,
        }
