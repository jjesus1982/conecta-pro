"""
Client Model - Cadastro de Clientes
Sprint 30: Cadastro de Clientes/Condomínios

NOTA: Este model foi sincronizado com o banco de dados real em 29/03/2026.
Colunas correspondem EXATAMENTE ao schema da tabela clients.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.clients.models.client_contract import ClientContract
    from modules.clients.models.condominium import Condominium
    from modules.clients.models.integration_settings import IntegrationSettings


# Enums para compatibilidade com controller (não são colunas SQLAlchemy)
class ClientType(StrEnum):
    CONDOMINIO = "condominio"
    EMPRESA = "empresa"
    PESSOA_FISICA = "pessoa_fisica"
    ORGAO_PUBLICO = "orgao_publico"


class ClientStatus(StrEnum):
    """Valores = labels REAIS do enum client_status_enum do banco (08/09/2026): antes nenhum
    batia ("ativo" × "active") e qualquer comparação estourava 500."""
    PROSPECT = "prospect"
    ATIVO = "active"
    INATIVO = "churned"
    SUSPENSO = "suspended"
    BLOQUEADO = "blocked"
    INADIMPLENTE = "defaulter"
    ENCERRADO = "cancelled"


class ClientSegment(StrEnum):
    RESIDENCIAL = "residencial"
    COMERCIAL = "comercial"
    INDUSTRIAL = "industrial"
    PUBLICO = "publico"
    MISTO = "misto"


class DocumentType(StrEnum):
    CPF = "cpf"
    CNPJ = "cnpj"
    PASSAPORTE = "passaporte"
    OUTRO = "outro"


class Client(Base):
    """
    Model de Cliente — sincronizado com banco real.

    Representa uma empresa, condomínio ou pessoa física que contrata
    serviços da Conecta Mais.
    """

    __tablename__ = "clients"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(20), unique=True, nullable=False, index=True)

    # Dados cadastrais — banco usa strings, não enums SQLAlchemy
    name = Column(String(200), nullable=False)
    trading_name = Column(String(200), nullable=True)
    client_type = Column("client_type", String(30), nullable=False)
    document_type = Column("document_type", String(30), nullable=False)
    document_number = Column(String(20), nullable=False, index=True)
    state_registration = Column(String(30), nullable=True)
    municipal_registration = Column(String(30), nullable=True)

    # Contatos
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    mobile = Column(String(20), nullable=True)
    whatsapp = Column(String(20), nullable=True)
    website = Column(String(255), nullable=True)

    # Endereço principal
    address_street = Column(String(255), nullable=True)
    address_number = Column(String(20), nullable=True)
    address_complement = Column(String(100), nullable=True)
    address_neighborhood = Column(String(100), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state = Column(String(2), nullable=True)
    address_zipcode = Column(String(10), nullable=True)
    address_country = Column(String(50), nullable=True)

    # Endereço cobrança
    billing_address_street = Column(String(255), nullable=True)
    billing_address_number = Column(String(20), nullable=True)
    billing_address_complement = Column(String(100), nullable=True)
    billing_address_neighborhood = Column(String(100), nullable=True)
    billing_address_city = Column(String(100), nullable=True)
    billing_address_state = Column(String(2), nullable=True)
    billing_address_zipcode = Column(String(10), nullable=True)

    # Contatos financeiro e técnico
    financial_contact_name = Column(String(200), nullable=True)
    financial_contact_email = Column(String(255), nullable=True)
    financial_contact_phone = Column(String(20), nullable=True)
    technical_contact_name = Column(String(200), nullable=True)
    technical_contact_email = Column(String(255), nullable=True)
    technical_contact_phone = Column(String(20), nullable=True)

    # Status e segmento — strings
    status = Column("status", String(30), nullable=False)
    segment = Column("segment", String(30), nullable=True)

    # Datas contratuais
    contract_start_date = Column(Date, nullable=True)
    contract_end_date = Column(Date, nullable=True)
    first_billing_date = Column(Date, nullable=True)
    last_billing_date = Column(Date, nullable=True)

    # Dados financeiros
    credit_limit = Column(Numeric(15, 2), nullable=True)
    payment_terms = Column(Integer, nullable=True)
    billing_day = Column(Integer, nullable=True)
    total_revenue = Column(Numeric(15, 2), nullable=True)
    total_debt = Column(Numeric(15, 2), nullable=True)

    # Métricas
    health_score = Column(Float, nullable=True)
    satisfaction_score = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)

    # Integrações
    guardian_enabled = Column(Boolean, nullable=False, default=False)
    plus_enabled = Column(Boolean, nullable=False, default=False)
    guardian_client_id = Column(String(50), nullable=True)
    plus_client_id = Column(String(50), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column("metadata", JSONB, nullable=True)

    # Responsáveis
    account_manager_id = Column(UUID(as_uuid=True), nullable=True)
    sales_rep_id = Column(UUID(as_uuid=True), nullable=True)

    # Flags — banco usa 'ativo' não 'is_active'
    ativo = Column(Boolean, nullable=False, default=True)
    is_defaulter = Column(Boolean, nullable=False, default=False)
    is_vip = Column(Boolean, nullable=False, default=False)
    default_since = Column(DateTime(timezone=True), nullable=True)
    default_amount = Column(Numeric(15, 2), nullable=True)

    # CRM
    lead_id = Column(UUID(as_uuid=True), nullable=True)
    crm_origin = Column(String(50), nullable=True, default="direto")

    # Auditoria
    created_at = Column(DateTime, nullable=False, server_default="now()")
    updated_at = Column(DateTime, nullable=False, server_default="now()", onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    condominiums: list["Condominium"] = relationship(
        "Condominium", back_populates="client", cascade="all, delete-orphan"
    )
    contracts: list["ClientContract"] = relationship(
        "ClientContract", back_populates="client", cascade="all, delete-orphan"
    )
    integration_settings: list["IntegrationSettings"] = relationship(
        "IntegrationSettings", back_populates="client", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Client(id={self.id}, code={self.code}, name={self.name})>"

    # Properties computadas (não são colunas)
    @property
    def is_active(self) -> bool:
        """Alias para ativo."""
        return bool(self.ativo)

    @property
    def type(self) -> str:
        """Alias para client_type."""
        return self.client_type

    @property
    def legal_name(self) -> str:
        """Alias para name."""
        return self.name

    @property
    def trade_name(self) -> str | None:
        """Alias para trading_name."""
        return self.trading_name

    @property
    def display_name(self) -> str:
        """Nome para exibição."""
        return self.trading_name or self.name

    @property
    def formatted_document(self) -> str:
        """Documento formatado."""
        doc = self.document_number
        if not doc:
            return ""

        doc = re.sub(r"\D", "", doc)

        if self.document_type == "cpf" and len(doc) == 11:
            return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
        elif self.document_type == "cnpj" and len(doc) == 14:
            return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"

        return doc

    @property
    def full_address(self) -> str:
        """Endereço completo."""
        parts = []
        if self.address_street:
            addr = self.address_street
            if self.address_number:
                addr += f", {self.address_number}"
            if self.address_complement:
                addr += f" - {self.address_complement}"
            parts.append(addr)

        if self.address_neighborhood:
            parts.append(self.address_neighborhood)

        if self.address_city and self.address_state:
            parts.append(f"{self.address_city}/{self.address_state}")

        if self.address_zipcode:
            parts.append(f"CEP: {self.address_zipcode}")

        return ", ".join(parts)

    @property
    def is_company(self) -> bool:
        """Verifica se é pessoa jurídica."""
        return self.document_type == "cnpj"

    @property
    def days_as_defaulter(self) -> int | None:
        """Dias como inadimplente."""
        if not self.is_defaulter or not self.default_since:
            return None
        return (datetime.now(tz=self.default_since.tzinfo) - self.default_since).days

    @property
    def computed_health_score(self) -> int:
        """Score de saúde do cliente computado (0-100)."""
        score = 100

        if self.status == "defaulter":
            score -= 40
        elif self.status == "suspended":
            score -= 30
        elif self.status == "blocked":
            score -= 50
        elif self.status != "active":
            score -= 20

        if self.is_defaulter:
            days = self.days_as_defaulter or 0
            if days > 90:
                score -= 30
            elif days > 60:
                score -= 20
            elif days > 30:
                score -= 10

        if self.is_vip:
            score += 10

        return max(0, min(100, score))

    # Computed properties for backwards compatibility with schemas
    @property
    def active_contracts(self) -> int:
        """Contratos ativos."""
        try:
            if not self.contracts:
                return 0
            return sum(1 for c in self.contracts if getattr(c, "status", "") == "active")
        except Exception:
            return 0

    @property
    def total_contracts(self) -> int:
        """Total de contratos."""
        try:
            if not self.contracts:
                return 0
            return len(self.contracts)
        except Exception:
            return 0

    def activate(self) -> None:
        """Ativa o cliente."""
        self.status = "active"
        self.ativo = True
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o cliente."""
        self.status = "inactive"
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def suspend(self, reason: str | None = None) -> None:
        """Suspende o cliente."""
        self.status = "suspended"
        if reason:
            self.notes = f"{self.notes or ''}\n[SUSPENSO] {datetime.now()}: {reason}".strip()
        self.updated_at = datetime.utcnow()

    def block(self, reason: str | None = None) -> None:
        """Bloqueia o cliente."""
        self.status = "blocked"
        self.ativo = False
        if reason:
            self.notes = f"{self.notes or ''}\n[BLOQUEADO] {datetime.now()}: {reason}".strip()
        self.updated_at = datetime.utcnow()

    def set_defaulter(self, debt_amount: Decimal) -> None:
        """Marca como inadimplente."""
        self.is_defaulter = True
        self.default_since = datetime.now()
        self.default_amount = debt_amount
        self.total_debt = debt_amount
        self.status = "defaulter"
        self.updated_at = datetime.utcnow()

    def clear_default(self) -> None:
        """Remove status de inadimplente."""
        self.is_defaulter = False
        self.default_since = None
        self.default_amount = None
        self.total_debt = Decimal("0")
        if self.status == "defaulter":
            self.status = "active"
        self.updated_at = datetime.utcnow()

    def enable_plus(self, client_id: str) -> None:
        """Habilita integração com Conecta Plus."""
        self.plus_enabled = True
        self.plus_client_id = client_id
        self.updated_at = datetime.utcnow()

    @staticmethod
    def generate_code(sequence: int) -> str:
        """Gera código do cliente."""
        year = datetime.now().year
        return f"CLI-{year}-{sequence:05d}"

    @staticmethod
    def validate_cnpj(cnpj: str) -> bool:
        """Valida CNPJ."""
        cnpj = re.sub(r"\D", "", cnpj)

        if len(cnpj) != 14:
            return False

        if cnpj == cnpj[0] * 14:
            return False

        def calc_digit(cnpj_part: str, weights: list[int]) -> int:
            total = sum(int(d) * w for d, w in zip(cnpj_part, weights, strict=False))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

        digit1 = calc_digit(cnpj[:12], weights1)
        digit2 = calc_digit(cnpj[:12] + str(digit1), weights2)

        return cnpj[-2:] == f"{digit1}{digit2}"

    @staticmethod
    def validate_cpf(cpf: str) -> bool:
        """Valida CPF."""
        cpf = re.sub(r"\D", "", cpf)

        if len(cpf) != 11:
            return False

        if cpf == cpf[0] * 11:
            return False

        def calc_digit(cpf_part: str, factor: int) -> int:
            total = sum(int(d) * (factor - i) for i, d in enumerate(cpf_part))
            remainder = (total * 10) % 11
            return 0 if remainder >= 10 else remainder

        digit1 = calc_digit(cpf[:9], 10)
        digit2 = calc_digit(cpf[:9] + str(digit1), 11)

        return cpf[-2:] == f"{digit1}{digit2}"
