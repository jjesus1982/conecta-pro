"""Model para categorias de contas a receber."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.receivable_account import ReceivableAccount


class CategoryType(StrEnum):
    """Tipo de categoria de receita."""

    TAXA_CONDOMINIAL = "taxa_condominial"  # Taxa de condominio
    TAXA_EXTRA = "taxa_extra"  # Taxa extra
    RESERVA = "reserva"  # Reserva de areas comuns
    MULTA = "multa"  # Multas
    JUROS = "juros"  # Juros de atraso
    ALUGUEL = "aluguel"  # Aluguel de espacos
    SERVICO = "servico"  # Servicos prestados
    REEMBOLSO = "reembolso"  # Reembolsos
    ACORDO = "acordo"  # Acordos de divida
    OUTROS = "outros"  # Outros


class ReceivableCategory(Base):
    """Categoria de conta a receber."""

    __tablename__ = "receivable_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    code = Column(String(20), nullable=True)  # Codigo interno
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category_type = Column(String(30), nullable=False, default=CategoryType.OUTROS.value)

    # Hierarquia
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receivable_categories.id"),
        nullable=True,
    )

    # Configuracoes contabeis
    accounting_code = Column(String(30), nullable=True)  # Codigo contabil
    cost_center = Column(String(30), nullable=True)  # Centro de custo

    # Configuracoes de cobranca
    apply_interest = Column(Boolean, default=True)  # Aplica juros
    interest_rate = Column(String(10), default="1.00")  # % juros ao mes
    apply_penalty = Column(Boolean, default=True)  # Aplica multa
    penalty_rate = Column(String(10), default="2.00")  # % multa
    grace_days = Column(Integer, default=0)  # Dias de carencia

    # Ordenacao
    display_order = Column(Integer, default=0)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    parent: Optional["ReceivableCategory"] = relationship(
        "ReceivableCategory",
        remote_side=[id],  # noqa: A003
        back_populates="children",
    )
    children: list["ReceivableCategory"] = relationship(
        "ReceivableCategory",
        back_populates="parent",
    )
    receivable_accounts: list["ReceivableAccount"] = relationship(
        "ReceivableAccount",
        back_populates="category",
    )

    __table_args__ = (
        Index("ix_receivable_categories_code", "code"),
        Index("ix_receivable_categories_name", "name"),
        Index("ix_receivable_categories_type", "category_type"),
        Index("ix_receivable_categories_condominio", "condominio_id"),
    )

    def __repr__(self) -> str:
        return f"<ReceivableCategory {self.code} - {self.name}>"

    @property
    def full_name(self) -> str:
        """Retorna nome completo com hierarquia."""
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    @property
    def has_children(self) -> bool:
        """Verifica se tem subcategorias."""
        try:
            return len(self.children) > 0 if self.children else False
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Converte para dicionario."""
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "category_type": self.category_type,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "accounting_code": self.accounting_code,
            "apply_interest": self.apply_interest,
            "interest_rate": self.interest_rate,
            "apply_penalty": self.apply_penalty,
            "penalty_rate": self.penalty_rate,
            "grace_days": self.grace_days,
            "full_name": self.full_name,
            "ativo": self.ativo,
        }
