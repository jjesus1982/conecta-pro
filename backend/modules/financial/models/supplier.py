"""Model para fornecedores."""

import uuid
from sqlalchemy import Numeric
from sqlalchemy import Integer
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.payable_account import PayableAccount


class SupplierType(StrEnum):
    """Tipo de fornecedor."""

    PESSOA_FISICA = "pessoa_fisica"
    PESSOA_JURIDICA = "pessoa_juridica"
    MEI = "mei"
    EIRELI = "eireli"
    COOPERATIVA = "cooperativa"
    OUTRO = "outro"


class SupplierStatus(StrEnum):
    """Status do fornecedor."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    BLOQUEADO = "bloqueado"
    PENDENTE = "pendente"  # Aguardando aprovação
    SUSPENSO = "suspenso"


class SupplierCategory(StrEnum):
    """Categoria do fornecedor."""

    SERVICOS = "servicos"
    MATERIAIS = "materiais"
    EQUIPAMENTOS = "equipamentos"
    MANUTENCAO = "manutencao"
    LIMPEZA = "limpeza"
    SEGURANCA = "seguranca"
    TECNOLOGIA = "tecnologia"
    CONSULTORIA = "consultoria"
    JURIDICO = "juridico"
    CONTABIL = "contabil"
    MARKETING = "marketing"
    LOGISTICA = "logistica"
    ALIMENTACAO = "alimentacao"
    UTILIDADES = "utilidades"  # Água, luz, gás, telefone
    OUTRO = "outro"


class PaymentTerms(StrEnum):
    """Condições de pagamento padrão."""

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
    CUSTOMIZADO = "customizado"


class Supplier(Base):
    """Fornecedor."""

    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificação
    code = Column(String(20), nullable=True)  # Código interno
    name = Column(String(200), nullable=False)
    trade_name = Column(String(200), nullable=True)  # Nome fantasia
    supplier_type = Column(String(20), nullable=False, default=SupplierType.PESSOA_JURIDICA.value)
    category = Column(String(30), nullable=True)
    status = Column(String(20), nullable=False, default=SupplierStatus.ATIVO.value)

    # Documentos
    cpf_cnpj = Column(String(18), nullable=True, index=True)  # CPF ou CNPJ formatado
    state_registration = Column(String(20), nullable=True)  # Inscrição estadual
    municipal_registration = Column(String(20), nullable=True)  # Inscrição municipal
    cnae = Column(String(10), nullable=True)  # CNAE principal

    # Contato
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    mobile = Column(String(20), nullable=True)
    whatsapp = Column(String(20), nullable=True)
    website = Column(String(200), nullable=True)

    # Contato principal
    contact_name = Column(String(100), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    contact_position = Column(String(50), nullable=True)  # Cargo

    # Endereço
    address_street = Column(String(200), nullable=True)
    address_number = Column(String(20), nullable=True)
    address_complement = Column(String(100), nullable=True)
    address_neighborhood = Column(String(100), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state = Column(String(2), nullable=True)
    address_zip = Column(String(10), nullable=True)
    address_country = Column(String(50), default="Brasil")

    # Dados bancários
    bank_code = Column(String(10), nullable=True)
    bank_name = Column(String(100), nullable=True)
    bank_agency = Column(String(10), nullable=True)
    bank_agency_digit = Column(String(2), nullable=True)
    bank_account = Column(String(20), nullable=True)
    bank_account_digit = Column(String(2), nullable=True)
    bank_account_type = Column(String(20), nullable=True)  # corrente, poupança
    pix_key = Column(String(100), nullable=True)
    pix_key_type = Column(String(20), nullable=True)  # cpf, cnpj, email, telefone, aleatoria

    # Condições comerciais
    payment_terms = Column(String(20), default=PaymentTerms.DIAS_30.value)
    payment_terms_days = Column(Integer, nullable=True)  # Para customizado
    credit_limit = Column(Numeric(15, 2), nullable=True)  # Limite de crédito
    discount_percentage = Column(Numeric(5, 2), nullable=True)  # % desconto padrão
    default_payment_method_id = Column(UUID(as_uuid=True), ForeignKey("payment_methods.id"), nullable=True)

    # Retenções fiscais
    withhold_iss = Column(Boolean, default=False)  # Reter ISS
    withhold_ir = Column(Boolean, default=False)  # Reter IR
    withhold_pis = Column(Boolean, default=False)  # Reter PIS
    withhold_cofins = Column(Boolean, default=False)  # Reter COFINS
    withhold_csll = Column(Boolean, default=False)  # Reter CSLL
    withhold_inss = Column(Boolean, default=False)  # Reter INSS

    # Classificação e avaliação
    rating = Column(Integer, nullable=True)  # 1-5 estrelas
    rating_count = Column(Integer, default=0)
    is_qualified = Column(Boolean, default=False)  # Fornecedor qualificado
    qualified_at = Column(DateTime, nullable=True)
    qualified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Documentos anexos (JSONB)
    documents = Column(JSONB, default=list)
    # [{"type": "contrato_social", "url": "...", "expires_at": "..."}]

    # Tags e observações
    tags = Column(ARRAY(String), default=list)  # ["prioritário", "certificado"]
    notes = Column(Text, nullable=True)

    # Bloqueio
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    blocked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    payable_accounts: list["PayableAccount"] = relationship("PayableAccount", back_populates="supplier")

    __table_args__ = (
        Index("ix_suppliers_cpf_cnpj", "cpf_cnpj"),
        Index("ix_suppliers_name", "name"),
        Index("ix_suppliers_status", "status"),
        Index("ix_suppliers_category", "category"),
        Index("ix_suppliers_condominio_status", "condominio_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.name}>"

    @property
    def is_active(self) -> bool:
        """Verifica se fornecedor está ativo."""
        return self.status == SupplierStatus.ATIVO.value and self.ativo

    @property
    def is_pessoa_juridica(self) -> bool:
        """Verifica se é pessoa jurídica."""
        return self.supplier_type in [
            SupplierType.PESSOA_JURIDICA.value,
            SupplierType.MEI.value,
            SupplierType.EIRELI.value,
            SupplierType.COOPERATIVA.value,
        ]

    @property
    def full_address(self) -> str | None:
        """Retorna endereço completo formatado."""
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
        if self.address_zip:
            parts.append(f"CEP: {self.address_zip}")
        return " - ".join(parts) if parts else None

    @property
    def bank_info(self) -> str | None:
        """Retorna informações bancárias formatadas."""
        if not self.bank_code:
            return None
        info = f"Banco {self.bank_code}"
        if self.bank_name:
            info = f"{self.bank_name} ({self.bank_code})"
        if self.bank_agency:
            ag = self.bank_agency
            if self.bank_agency_digit:
                ag += f"-{self.bank_agency_digit}"
            info += f" | Ag: {ag}"
        if self.bank_account:
            cc = self.bank_account
            if self.bank_account_digit:
                cc += f"-{self.bank_account_digit}"
            info += f" | CC: {cc}"
        return info

    def block(self, reason: str, user_id: uuid.UUID) -> None:
        """Bloqueia o fornecedor."""
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_at = datetime.utcnow()
        self.blocked_by = user_id
        self.status = SupplierStatus.BLOQUEADO.value

    def unblock(self) -> None:
        """Desbloqueia o fornecedor."""
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None
        self.status = SupplierStatus.ATIVO.value

    def qualify(self, user_id: uuid.UUID) -> None:
        """Marca como fornecedor qualificado."""
        self.is_qualified = True
        self.qualified_at = datetime.utcnow()
        self.qualified_by = user_id

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "trade_name": self.trade_name,
            "supplier_type": self.supplier_type,
            "category": self.category,
            "status": self.status,
            "cpf_cnpj": self.cpf_cnpj,
            "email": self.email,
            "phone": self.phone,
            "is_qualified": self.is_qualified,
            "is_blocked": self.is_blocked,
            "full_address": self.full_address,
            "bank_info": self.bank_info,
        }
