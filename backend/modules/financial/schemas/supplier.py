"""Schemas para fornecedores."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from modules.financial.models.supplier import (
    PaymentTerms,
    SupplierCategory,
    SupplierStatus,
    SupplierType,
)


class SupplierBase(BaseModel):
    """Base para fornecedor."""

    name: str = Field(..., min_length=2, max_length=200)
    trade_name: str | None = Field(None, max_length=200)
    supplier_type: SupplierType = SupplierType.PESSOA_JURIDICA
    category: SupplierCategory | None = None
    cpf_cnpj: str | None = Field(None, max_length=18)
    state_registration: str | None = Field(None, max_length=20)
    municipal_registration: str | None = Field(None, max_length=20)
    cnae: str | None = Field(None, max_length=10)

    # Contato
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    mobile: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=200)

    # Contato principal
    contact_name: str | None = Field(None, max_length=100)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=20)
    contact_position: str | None = Field(None, max_length=50)

    # Endereço
    address_street: str | None = Field(None, max_length=200)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zip: str | None = Field(None, max_length=10)

    # Dados bancários
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)
    bank_agency: str | None = Field(None, max_length=10)
    bank_agency_digit: str | None = Field(None, max_length=2)
    bank_account: str | None = Field(None, max_length=20)
    bank_account_digit: str | None = Field(None, max_length=2)
    bank_account_type: str | None = Field(None, max_length=20)
    pix_key: str | None = Field(None, max_length=100)
    pix_key_type: str | None = Field(None, max_length=20)

    # Condições comerciais
    payment_terms: PaymentTerms = PaymentTerms.DIAS_30
    payment_terms_days: int | None = None
    credit_limit: float | None = None
    discount_percentage: float | None = None

    # Retenções fiscais
    withhold_iss: bool = False
    withhold_ir: bool = False
    withhold_pis: bool = False
    withhold_cofins: bool = False
    withhold_csll: bool = False
    withhold_inss: bool = False

    # Tags e observações
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class SupplierCreate(SupplierBase):
    """Schema para criação de fornecedor."""

    condominio_id: UUID


class SupplierUpdate(BaseModel):
    """Schema para atualização de fornecedor."""

    name: str | None = Field(None, min_length=2, max_length=200)
    trade_name: str | None = Field(None, max_length=200)
    supplier_type: SupplierType | None = None
    category: SupplierCategory | None = None
    status: SupplierStatus | None = None
    cpf_cnpj: str | None = Field(None, max_length=18)

    # Contato
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    mobile: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=200)

    # Contato principal
    contact_name: str | None = Field(None, max_length=100)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=20)
    contact_position: str | None = Field(None, max_length=50)

    # Endereço
    address_street: str | None = Field(None, max_length=200)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zip: str | None = Field(None, max_length=10)

    # Dados bancários
    bank_code: str | None = Field(None, max_length=10)
    bank_name: str | None = Field(None, max_length=100)
    bank_agency: str | None = Field(None, max_length=10)
    bank_account: str | None = Field(None, max_length=20)
    pix_key: str | None = Field(None, max_length=100)
    pix_key_type: str | None = Field(None, max_length=20)

    # Condições comerciais
    payment_terms: PaymentTerms | None = None
    credit_limit: float | None = None
    discount_percentage: float | None = None

    # Retenções fiscais
    withhold_iss: bool | None = None
    withhold_ir: bool | None = None
    withhold_pis: bool | None = None
    withhold_cofins: bool | None = None
    withhold_csll: bool | None = None
    withhold_inss: bool | None = None

    # Tags e observações
    tags: list[str] | None = None
    notes: str | None = None


class SupplierResponse(SupplierBase):
    """Schema de resposta para fornecedor."""

    id: UUID
    condominio_id: UUID
    code: str | None = None
    status: SupplierStatus
    is_qualified: bool = False
    qualified_at: datetime | None = None
    is_blocked: bool = False
    blocked_reason: str | None = None
    blocked_at: datetime | None = None
    rating: str | None = None
    rating_count: int = 0
    full_address: str | None = None
    bank_info: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class SupplierListResponse(BaseModel):
    """Schema de lista de fornecedores."""

    id: UUID
    code: str | None = None
    name: str
    trade_name: str | None = None
    supplier_type: str
    category: str | None = None
    status: str
    cpf_cnpj: str | None = None
    email: str | None = None
    phone: str | None = None
    is_qualified: bool = False
    is_blocked: bool = False
    rating: str | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class SupplierFilter(BaseModel):
    """Filtros para busca de fornecedores."""

    search: str | None = None  # Busca em nome, cpf_cnpj, email
    supplier_type: SupplierType | None = None
    category: SupplierCategory | None = None
    status: SupplierStatus | None = None
    is_qualified: bool | None = None
    is_blocked: bool | None = None
    city: str | None = None
    state: str | None = None
    tags: list[str] | None = None


class SupplierStats(BaseModel):
    """Estatísticas de fornecedores."""

    total: int = 0
    ativos: int = 0
    inativos: int = 0
    bloqueados: int = 0
    qualificados: int = 0
    por_tipo: dict = Field(default_factory=dict)
    por_categoria: dict = Field(default_factory=dict)


class SupplierBlockRequest(BaseModel):
    """Request para bloquear fornecedor."""

    reason: str = Field(..., min_length=5, max_length=500)


class SupplierQualifyRequest(BaseModel):
    """Request para qualificar fornecedor."""

    notes: str | None = Field(None, max_length=500)
