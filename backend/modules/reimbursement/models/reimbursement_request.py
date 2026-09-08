"""Model para solicitações de reembolso."""

import uuid
from datetime import UTC, datetime
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
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.reimbursement.models.reimbursement_attachment import ReimbursementAttachment
    from modules.reimbursement.models.reimbursement_item import ReimbursementItem


class ReimbursementStatus(StrEnum):
    """Status da solicitação de reembolso."""

    RASCUNHO = "rascunho"  # Ainda não submetido
    PENDENTE = "pendente"  # Aguardando aprovação
    EM_ANALISE = "em_analise"  # Em análise
    APROVADO = "aprovado"  # Aprovado, aguarda pagamento
    REJEITADO = "rejeitado"  # Rejeitado
    PROCESSADO = "processado"  # Pago/conta a pagar gerada
    CANCELADO = "cancelado"  # Cancelado


class ApprovalLevel(StrEnum):
    """Nível de aprovação baseado no valor."""

    SUPERVISOR = "supervisor"  # Até R$ 500
    GERENTE = "gerente"  # Até R$ 2.000
    DIRETOR = "diretor"  # Até R$ 10.000
    FINANCEIRO = "financeiro"  # Acima de R$ 10.000


# Limites de aprovação por nível
APPROVAL_LIMITS = {
    ApprovalLevel.SUPERVISOR: Decimal("500.00"),
    ApprovalLevel.GERENTE: Decimal("2000.00"),
    ApprovalLevel.DIRETOR: Decimal("10000.00"),
    ApprovalLevel.FINANCEIRO: Decimal("999999999.99"),
}


class ReimbursementRequest(Base):
    """Solicitação de reembolso de despesas."""

    __tablename__ = "reimbursement_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Identificação
    code = Column(String(20), unique=True, nullable=False)  # REI-2026-00001
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Solicitante
    requester_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Período das despesas
    expense_date_start = Column(Date, nullable=False)
    expense_date_end = Column(Date, nullable=False)

    # Valores
    total_amount = Column(Numeric(15, 2), default=Decimal("0.00"))  # Valor total solicitado
    approved_amount = Column(Numeric(15, 2), default=Decimal("0.00"))  # Valor aprovado
    paid_amount = Column(Numeric(15, 2), default=Decimal("0.00"))  # Valor pago

    # Status e aprovação
    status = Column(String(20), nullable=False, default=ReimbursementStatus.RASCUNHO.value)
    approval_level = Column(String(20), nullable=True)  # Nível necessário

    # Submissão
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    # Aprovação/Rejeição
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Processamento (integração financeiro)
    payable_account_id = Column(UUID(as_uuid=True), nullable=True)  # FK para conta a pagar
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Dados bancários do funcionário (para pagamento)
    bank_code = Column(String(10), nullable=True)
    bank_agency = Column(String(10), nullable=True)
    bank_account = Column(String(20), nullable=True)
    pix_key = Column(String(100), nullable=True)

    # Classificação
    cost_center = Column(String(50), nullable=True)
    project = Column(String(100), nullable=True)

    # Observações
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    items: list["ReimbursementItem"] = relationship(
        "ReimbursementItem",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    attachments: list["ReimbursementAttachment"] = relationship(
        "ReimbursementAttachment",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="ReimbursementAttachment.request_id",
    )

    __table_args__ = (
        Index("ix_reimbursement_requests_code", "code"),
        Index("ix_reimbursement_requests_status", "status"),
        Index("ix_reimbursement_requests_requester", "requester_id"),
        Index(
            "ix_reimbursement_requests_condominio_status",
            "condominio_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<ReimbursementRequest {self.code} - {self.status}>"

    @staticmethod
    def generate_code(year: int, sequence: int) -> str:
        """Gera código único para a solicitação."""
        return f"REI-{year}-{sequence:05d}"

    def calculate_total(self) -> Decimal:
        """Calcula o valor total dos itens."""
        total = sum(item.amount for item in self.items if item.is_active)
        return Decimal(str(total)) if total else Decimal("0.00")

    def calculate_approved_total(self) -> Decimal:
        """Calcula o valor total aprovado dos itens."""
        total = sum(item.approved_amount or item.amount for item in self.items if item.is_active and item.is_approved)
        return Decimal(str(total)) if total else Decimal("0.00")

    def determine_approval_level(self) -> ApprovalLevel:
        """Determina o nível de aprovação necessário baseado no valor."""
        total = self.calculate_total()

        if total <= APPROVAL_LIMITS[ApprovalLevel.SUPERVISOR]:
            return ApprovalLevel.SUPERVISOR
        elif total <= APPROVAL_LIMITS[ApprovalLevel.GERENTE]:
            return ApprovalLevel.GERENTE
        elif total <= APPROVAL_LIMITS[ApprovalLevel.DIRETOR]:
            return ApprovalLevel.DIRETOR
        else:
            return ApprovalLevel.FINANCEIRO

    def submit(self) -> None:
        """Submete a solicitação para aprovação."""
        if self.status != ReimbursementStatus.RASCUNHO.value:
            raise ValueError("Apenas rascunhos podem ser submetidos")

        if not self.items or len([i for i in self.items if i.is_active]) == 0:
            raise ValueError("Solicitação deve ter pelo menos um item")

        self.total_amount = self.calculate_total()
        self.approval_level = self.determine_approval_level().value
        self.status = ReimbursementStatus.PENDENTE.value
        self.submitted_at = datetime.now(UTC)

    def approve(self, user_id: uuid.UUID, comments: str | None = None) -> None:
        """Aprova a solicitação."""
        if self.status not in [
            ReimbursementStatus.PENDENTE.value,
            ReimbursementStatus.EM_ANALISE.value,
        ]:
            raise ValueError(f"Solicitação em status {self.status} não pode ser aprovada")

        self.approved_amount = self.calculate_approved_total()
        self.approved_by = user_id
        self.approved_at = datetime.now(UTC)
        self.status = ReimbursementStatus.APROVADO.value

        if comments:
            self.notes = (self.notes or "") + f"\n[Aprovação] {comments}"

    def reject(self, user_id: uuid.UUID, reason: str) -> None:
        """Rejeita a solicitação."""
        if self.status not in [
            ReimbursementStatus.PENDENTE.value,
            ReimbursementStatus.EM_ANALISE.value,
        ]:
            raise ValueError(f"Solicitação em status {self.status} não pode ser rejeitada")

        self.approved_by = user_id
        self.approved_at = datetime.now(UTC)
        self.rejection_reason = reason
        self.status = ReimbursementStatus.REJEITADO.value

    def cancel(self, reason: str | None = None) -> None:
        """Cancela a solicitação."""
        if self.status in [
            ReimbursementStatus.PROCESSADO.value,
            ReimbursementStatus.CANCELADO.value,
        ]:
            raise ValueError(f"Solicitação em status {self.status} não pode ser cancelada")

        self.status = ReimbursementStatus.CANCELADO.value
        if reason:
            self.internal_notes = (self.internal_notes or "") + f"\n[Cancelamento] {reason}"

    def mark_as_processed(
        self,
        user_id: uuid.UUID,
        payable_account_id: uuid.UUID,
    ) -> None:
        """Marca como processado após geração de conta a pagar."""
        if self.status != ReimbursementStatus.APROVADO.value:
            raise ValueError("Apenas solicitações aprovadas podem ser processadas")

        self.payable_account_id = payable_account_id
        self.processed_by = user_id
        self.processed_at = datetime.now(UTC)
        self.status = ReimbursementStatus.PROCESSADO.value

    def return_to_draft(self, reason: str | None = None) -> None:
        """Retorna a solicitação para rascunho (devolução)."""
        if self.status not in [
            ReimbursementStatus.PENDENTE.value,
            ReimbursementStatus.EM_ANALISE.value,
        ]:
            raise ValueError("Solicitação não pode ser devolvida")

        self.status = ReimbursementStatus.RASCUNHO.value
        self.submitted_at = None
        self.approval_level = None

        if reason:
            self.notes = (self.notes or "") + f"\n[Devolvido] {reason}"

    @property
    def can_edit(self) -> bool:
        """Verifica se pode ser editada."""
        return self.status == ReimbursementStatus.RASCUNHO.value

    @property
    def can_submit(self) -> bool:
        """Verifica se pode ser submetida."""
        if self.status != ReimbursementStatus.RASCUNHO.value:
            return False
        if not self.items:
            return False
        return len([i for i in self.items if i.is_active]) > 0

    @property
    def can_approve(self) -> bool:
        """Verifica se pode ser aprovada."""
        return self.status in [
            ReimbursementStatus.PENDENTE.value,
            ReimbursementStatus.EM_ANALISE.value,
        ]

    @property
    def can_process(self) -> bool:
        """Verifica se pode ser processada (gerar conta a pagar)."""
        return self.status == ReimbursementStatus.APROVADO.value

    @property
    def items_count(self) -> int:
        """Retorna quantidade de itens ativos."""
        return len([i for i in self.items if i.is_active])

    @property
    def attachments_count(self) -> int:
        """Retorna quantidade de anexos."""
        return len([a for a in self.attachments if a.is_active])

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "requester_id": str(self.requester_id) if self.requester_id else None,
            "expense_date_start": self.expense_date_start.isoformat() if self.expense_date_start else None,
            "expense_date_end": self.expense_date_end.isoformat() if self.expense_date_end else None,
            "total_amount": float(self.total_amount or 0),
            "approved_amount": float(self.approved_amount or 0),
            "paid_amount": float(self.paid_amount or 0),
            "status": self.status,
            "approval_level": self.approval_level,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "items_count": self.items_count,
            "attachments_count": self.attachments_count,
            "can_edit": self.can_edit,
            "can_submit": self.can_submit,
            "can_approve": self.can_approve,
            "can_process": self.can_process,
        }
