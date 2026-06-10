"""
Schemas Pydantic para Proposal.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from modules.crm.models.proposal import (
    ApprovalAction,
    DiscountType,
    ProposalStatus,
    ProposalType,
)

# ============== ProposalItem Schemas ==============


class ProposalItemBase(BaseModel):
    """Schema base para item de proposta."""

    code: str | None = Field(None, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    unit: str = Field(default="un", max_length=20)
    quantity: float = Field(default=1.0, ge=0)
    unit_price: float = Field(default=0.0, ge=0)
    discount_percent: float = Field(default=0.0, ge=0, le=100)
    is_optional: bool = False


class ProposalItemCreate(ProposalItemBase):
    """Schema para criacao de item."""

    sort_order: int = 0


class ProposalItemUpdate(BaseModel):
    """Schema para atualizacao de item."""

    code: str | None = Field(None, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    unit: str | None = Field(None, max_length=20)
    quantity: float | None = Field(None, ge=0)
    unit_price: float | None = Field(None, ge=0)
    discount_percent: float | None = Field(None, ge=0, le=100)
    is_optional: bool | None = None
    sort_order: int | None = None


class ProposalItemResponse(ProposalItemBase):
    """Schema de resposta para item."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    proposal_id: str
    total: float
    subtotal: float
    discount_amount: float
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============== ProposalTemplate Schemas ==============


class ProposalTemplateBase(BaseModel):
    """Schema base para template."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    default_title: str | None = Field(None, max_length=255)
    default_description: str | None = None
    terms_conditions: str | None = None
    payment_terms: str | None = None
    validity_days: int = Field(default=30, ge=1, le=365)
    proposal_type: ProposalType = ProposalType.SERVICE


class ProposalTemplateCreate(ProposalTemplateBase):
    """Schema para criacao de template."""

    header_html: str | None = None
    footer_html: str | None = None
    css_styles: str | None = None
    is_default: bool = False


class ProposalTemplateUpdate(BaseModel):
    """Schema para atualizacao de template."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    default_title: str | None = Field(None, max_length=255)
    default_description: str | None = None
    terms_conditions: str | None = None
    payment_terms: str | None = None
    validity_days: int | None = Field(None, ge=1, le=365)
    proposal_type: ProposalType | None = None
    header_html: str | None = None
    footer_html: str | None = None
    css_styles: str | None = None
    is_default: bool | None = None


class ProposalTemplateResponse(ProposalTemplateBase):
    """Schema de resposta para template."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    header_html: str | None
    footer_html: str | None
    css_styles: str | None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============== Proposal Schemas ==============


class ProposalBase(BaseModel):
    """Schema base para proposta."""

    @field_validator("client_email", mode="before")
    @classmethod
    def _empty_email_to_none(cls, v):
        # EmailStr rejeita string vazia; normaliza ""/espacos -> None (campo opcional)
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    proposal_type: ProposalType = ProposalType.SERVICE

    # Cliente
    client_name: str = Field(..., min_length=1, max_length=255)
    client_email: EmailStr | None = None
    client_phone: str | None = Field(None, max_length=20)
    client_company: str | None = Field(None, max_length=255)
    client_document: str | None = Field(None, max_length=20)
    client_address: str | None = None

    # Condicoes
    terms_conditions: str | None = None
    payment_terms: str | None = None
    payment_conditions: str | None = Field(None, max_length=255)
    installments: int = Field(default=1, ge=1, le=120)
    notes: str | None = None

    # Datas
    valid_until: date | None = None


class ProposalCreate(ProposalBase):
    """Schema para criacao de proposta."""

    opportunity_id: str | None = None
    template_id: str | None = None

    # Desconto global
    discount_type: DiscountType | None = None
    discount_value: float = Field(default=0.0, ge=0)
    discount_reason: str | None = Field(None, max_length=255)
    taxes: float = Field(default=0.0, ge=0)

    # Itens (opcional na criacao)
    items: list[ProposalItemCreate] = []


class ProposalCreateFromOpportunity(BaseModel):
    """Schema para criar proposta a partir de opportunity."""

    opportunity_id: str
    template_id: str | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    valid_until: date | None = None
    items: list[ProposalItemCreate] = []


class ProposalUpdate(BaseModel):
    """Schema para atualizacao de proposta."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    proposal_type: ProposalType | None = None

    # Cliente
    client_name: str | None = Field(None, min_length=1, max_length=255)
    client_email: EmailStr | None = None
    client_phone: str | None = Field(None, max_length=20)
    client_company: str | None = Field(None, max_length=255)
    client_document: str | None = Field(None, max_length=20)
    client_address: str | None = None

    # Condicoes
    terms_conditions: str | None = None
    payment_terms: str | None = None
    payment_conditions: str | None = Field(None, max_length=255)
    installments: int | None = Field(None, ge=1, le=120)
    notes: str | None = None

    # Datas
    valid_until: date | None = None

    # Desconto
    discount_type: DiscountType | None = None
    discount_value: float | None = Field(None, ge=0)
    discount_reason: str | None = Field(None, max_length=255)
    taxes: float | None = Field(None, ge=0)


class ProposalStatusUpdate(BaseModel):
    """Schema para atualizacao de status."""

    status: ProposalStatus
    notes: str | None = None


class ProposalSend(BaseModel):
    """Schema para enviar proposta."""

    recipient_email: EmailStr | None = None  # Se diferente do client_email
    subject: str | None = None
    message: str | None = None
    cc_emails: list[str] = []


class ProposalApprovalRequest(BaseModel):
    """Schema para solicitar aprovacao."""

    action: ApprovalAction
    comments: str | None = None


class ProposalClientResponse(BaseModel):
    """Schema para resposta do cliente."""

    accepted: bool
    feedback: str | None = None
    signature: str | None = None  # Base64 da assinatura


class ProposalResponse(BaseModel):
    """Schema de resposta para proposta."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    number: str
    version: int
    parent_id: str | None

    # Relacionamentos
    opportunity_id: str | None
    template_id: str | None

    # Cliente
    client_name: str
    client_email: str | None = None
    client_phone: str | None
    client_company: str | None
    client_document: str | None
    client_address: str | None

    # Conteudo
    title: str
    description: str | None
    proposal_type: ProposalType
    terms_conditions: str | None
    notes: str | None

    # Valores
    subtotal: float
    discount_type: DiscountType | None
    discount_value: float
    discount_reason: str | None
    discount_amount: float
    taxes: float
    total: float

    # Pagamento
    payment_terms: str | None
    payment_conditions: str | None
    installments: int

    # Datas
    issue_date: date
    valid_until: date | None
    sent_at: datetime | None
    viewed_at: datetime | None
    responded_at: datetime | None

    # Status
    status: ProposalStatus
    rejection_reason: str | None

    # Responsaveis
    created_by_id: str | None
    approved_by_id: str | None
    approved_at: datetime | None

    # Propriedades calculadas
    is_draft: bool
    is_pending: bool
    is_approved: bool
    is_sent: bool
    is_closed: bool
    is_accepted: bool
    is_expired: bool
    days_until_expiry: int | None
    item_count: int

    # Controle
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProposalDetailResponse(ProposalResponse):
    """Schema de resposta detalhada com itens."""

    items: list[ProposalItemResponse] = []


class ProposalListResponse(BaseModel):
    """Schema de resposta para lista de propostas."""

    items: list[ProposalResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProposalFilter(BaseModel):
    """Schema para filtros de busca."""

    status: ProposalStatus | None = None
    proposal_type: ProposalType | None = None
    opportunity_id: str | None = None
    created_by_id: str | None = None
    is_expired: bool | None = None
    min_value: float | None = None
    max_value: float | None = None
    client_name: str | None = None
    search: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class ProposalStats(BaseModel):
    """Estatisticas de propostas."""

    total_proposals: int
    draft_count: int
    pending_count: int
    sent_count: int
    accepted_count: int
    rejected_count: int
    expired_count: int
    total_value: float
    accepted_value: float
    pending_value: float
    acceptance_rate: float  # Percentual
    avg_proposal_value: float
    avg_response_time_days: float
    by_status: dict[str, int]
    by_type: dict[str, int]


# ============== Approval Schemas ==============


class ProposalApprovalResponse(BaseModel):
    """Schema de resposta para aprovacao."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    proposal_id: str
    user_id: str | None
    action: ApprovalAction
    comments: str | None
    created_at: datetime
