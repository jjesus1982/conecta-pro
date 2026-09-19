"""
Schemas Pydantic para Gestão de Contratos.

Validação e serialização de dados para:
- Contratos recorrentes e pontuais
- Templates e cláusulas
- Aditivos e renovações
- SLA e relatórios
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.crm.models.contract import (
    AddendumType,
    AdjustmentIndex,
    ContractStatus,
    ContractType,
    ServiceType,
)

# ============== Contract Schemas ==============


class ContractBase(BaseModel):
    """Campos base do contrato."""

    name: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    contract_type: ContractType = ContractType.RECURRING
    monthly_value: Decimal = Field(..., ge=0)
    total_value: Decimal | None = Field(None, ge=0)
    setup_fee: Decimal = Field(default=Decimal("0"), ge=0)
    start_date: date
    end_date: date | None = None
    grace_period_days: int = Field(default=0, ge=0)
    notice_period_days: int = Field(default=30, ge=0)

    # Renovação
    auto_renewal: bool = True
    renewal_period_months: int = Field(default=12, ge=1, le=60)
    renewal_notification_days: int = Field(default=30, ge=0)

    # Reajuste
    adjustment_enabled: bool = True
    adjustment_index: AdjustmentIndex | None = None
    adjustment_fixed_percent: Decimal | None = Field(None, ge=0, le=100)
    adjustment_base_date: date | None = None

    # SLA
    has_sla: bool = False
    sla_config: dict[str, Any] | None = None

    # Assinatura
    signature_required: bool = True
    signature_provider: str | None = Field(None, max_length=50)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date | None, info) -> date | None:
        """Valida que data fim é posterior à data início."""
        if v is not None and "start_date" in info.data:
            if v <= info.data["start_date"]:
                raise ValueError("Data de término deve ser posterior à data de início")
        return v

    @field_validator("adjustment_fixed_percent")
    @classmethod
    def validate_fixed_percent(cls, v: Decimal | None, info) -> Decimal | None:
        """Valida percentual fixo quando índice é FIXED."""
        if info.data.get("adjustment_index") == AdjustmentIndex.FIXED and v is None:
            raise ValueError("Percentual fixo é obrigatório quando índice é FIXED")
        return v


class ContractCreate(ContractBase):
    """Schema para criar contrato."""

    client_id: str = Field(..., min_length=36, max_length=36)
    opportunity_id: str | None = Field(None, min_length=36, max_length=36)
    proposal_id: str | None = Field(None, min_length=36, max_length=36)
    template_id: str | None = Field(None, min_length=36, max_length=36)
    content: str | None = None
    clauses: list[dict[str, Any] | str] | None = None  # no banco há modelos com cláusulas em texto (08/09/2026)
    commercial_manager_id: str | None = Field(None, min_length=36, max_length=36)
    account_manager_id: str | None = Field(None, min_length=36, max_length=36)


class ContractCreateFromOpportunity(BaseModel):
    """Schema para criar contrato a partir de opportunity."""

    opportunity_id: str = Field(..., min_length=36, max_length=36)
    template_id: str | None = Field(None, min_length=36, max_length=36)
    start_date: date
    end_date: date | None = None
    monthly_value: Decimal | None = Field(None, ge=0)
    adjustment_index: AdjustmentIndex | None = None


class ContractCreateFromProposal(BaseModel):
    """Schema para criar contrato a partir de proposta aceita."""

    proposal_id: str = Field(..., min_length=36, max_length=36)
    template_id: str | None = Field(None, min_length=36, max_length=36)
    start_date: date
    end_date: date | None = None


class ContractUpdate(BaseModel):
    """Schema para atualizar contrato."""

    name: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = None
    monthly_value: Decimal | None = Field(None, ge=0)
    total_value: Decimal | None = Field(None, ge=0)
    setup_fee: Decimal | None = Field(None, ge=0)
    end_date: date | None = None
    grace_period_days: int | None = Field(None, ge=0)
    notice_period_days: int | None = Field(None, ge=0)

    # Renovação
    auto_renewal: bool | None = None
    renewal_period_months: int | None = Field(None, ge=1, le=60)
    renewal_notification_days: int | None = Field(None, ge=0)

    # Reajuste
    adjustment_enabled: bool | None = None
    adjustment_index: AdjustmentIndex | None = None
    adjustment_fixed_percent: Decimal | None = Field(None, ge=0, le=100)

    # SLA
    has_sla: bool | None = None
    sla_config: dict[str, Any] | None = None

    # Responsáveis
    commercial_manager_id: str | None = Field(None, min_length=36, max_length=36)
    account_manager_id: str | None = Field(None, min_length=36, max_length=36)


class ContractStatusUpdate(BaseModel):
    """Schema para atualizar status do contrato."""

    status: ContractStatus
    reason: str | None = None


class ContractRenewal(BaseModel):
    """Schema para renovação de contrato."""

    new_end_date: date
    adjustment_percent: Decimal | None = Field(None, ge=0, le=100)
    new_monthly_value: Decimal | None = Field(None, ge=0)


class ContractItemResponse(BaseModel):
    """Resposta de item do contrato."""

    id: str
    # ⭐ `str`, NÃO o enum ServiceType. Medido em 11/09/2026: o enum declara `security`,
    # `remote_gatehouse`, `electronic_security`… e a tabela guarda `manutencao_cftv`,
    # `maodeobra`, `portaria_remota`, `portaria_mao_de_obra` — INTERSEÇÃO ZERO. O enum
    # nunca bateu com a realidade, e por causa dele `GET /crm/contracts/{id}` respondia 500
    # em TODO contrato que tem item: 5 de 19, e os 14 que passavam só passavam por estarem
    # vazios. `obter_contrato` estava quebrada desde sempre, e o relatório de campo de
    # agosto já dizia "historicamente também: obter_contrato -> 500".
    #
    # Além disso a coluna carrega, no contrato de valor ÚNICO, o PAPEL da parcela
    # (entrada · parcela · retida) — que o render lê para montar a Cláusula 3.2. Um enum
    # aqui transforma cada novo tipo de serviço em contrato ilegível.
    service_type: str
    service_name: str
    description: str | None = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", mode="before")
    @classmethod
    def stringify_item_uuid(cls, v: Any) -> str:
        # o ORM devolve UUID; `id: str` recusava com string_type. Mesmo validador que o
        # contrato-pai já tinha e que o item nunca ganhou.
        return str(v) if v is not None else ""

    @field_validator("service_type", mode="before")
    @classmethod
    def stringify_service_type(cls, v: Any) -> str:
        # aceita tanto o Enum (se algum dia voltar a ser) quanto a string crua da coluna
        return getattr(v, "value", None) or str(v or "")


class ContractResponse(BaseModel):
    """Resposta resumida do contrato."""

    id: str
    contract_number: str
    name: str
    contract_type: ContractType
    status: ContractStatus
    client_id: str
    # Quem é o cliente, NA PRÓPRIA LINHA. Relatório de campo do Jordan (11/09/2026): a
    # listagem devolvia número, tipo, valor e status — e não dizia de quem era o contrato.
    # Para saber, o agente chamava `obter_contrato` em cada um: 19 chamadas para responder
    # "quais contratos são do Maiápolis". Opcionais porque o contrato pode não ter cliente
    # vinculado, e nesse caso a linha diz isso em vez de inventar.
    client_name: str | None = None
    client_document: str | None = None
    # De qual MODELO este contrato depende. Sem este campo, quem quer saber "alterar este
    # modelo afeta quem?" não tinha como perguntar pela listagem — e uma guarda construída
    # sobre a ausência dele responde "ninguém" e libera a escrita. Aconteceu em 11/09/2026.
    template_id: str | None = None
    monthly_value: Decimal
    total_value: Decimal
    start_date: date
    end_date: date | None = None
    auto_renewal: bool
    adjustment_enabled: bool
    has_sla: bool
    created_at: datetime
    updated_at: datetime | None = None

    # Propriedades calculadas
    is_active_contract: bool = False
    is_expiring_soon: bool = False
    days_until_end: int | None = None
    needs_adjustment: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", "client_id", mode="before")
    @classmethod
    def stringify_uuid(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("template_id", mode="before")
    @classmethod
    def stringify_template_uuid(cls, v: Any) -> str | None:
        # `None` de verdade, não "": contrato SEM modelo é um estado real, e "" faria a
        # comparação `template_id == alvo` dar falso-negativo silencioso do mesmo jeito.
        return str(v) if v is not None else None


class ContractDetailResponse(ContractResponse):
    """Resposta detalhada do contrato."""

    description: str | None = None
    opportunity_id: str | None = None
    proposal_id: str | None = None

    @field_validator("opportunity_id", "proposal_id", mode="before")
    @classmethod
    def stringify_optional_uuid(cls, v: Any) -> str | None:
        return str(v) if v is not None else None

    setup_fee: Decimal
    grace_period_days: int
    notice_period_days: int
    renewal_period_months: int
    renewal_notification_days: int
    adjustment_index: AdjustmentIndex | None = None
    adjustment_fixed_percent: Decimal | None = None
    adjustment_base_date: date | None = None
    last_adjustment_date: date | None = None
    next_adjustment_date: date | None = None
    sla_config: dict[str, Any] | None = None
    content: str | None = None
    clauses: list[dict[str, Any] | str] | None = None  # no banco há modelos com cláusulas em texto (08/09/2026)
    signature_required: bool
    signature_provider: str | None = None
    signed_at: datetime | None = None
    signed_by_client: str | None = None
    signed_by_company: str | None = None
    pdf_file_path: str | None = None
    # ⭐ 18/09/2026 — R8-2: o congelamento existia e era INVISÍVEL de fora. Eu media
    # `conteudo_hash` do lado de dentro e `obter_contrato` não devolvia — e comparar hash era
    # o propósito da coisa. Trava que funciona e ninguém consegue auditar é meia trava:
    # quem consome não tem como saber se o documento que ele lê é o que foi congelado.
    conteudo_hash: str | None = None
    emitido_em: datetime | None = None
    emitido_por: str | None = None
    commercial_manager_id: str | None = None
    account_manager_id: str | None = None
    created_by: str | None = None

    # Itens do contrato
    items: list[ContractItemResponse] = []


class ContractFilter(BaseModel):
    """Filtros para listagem de contratos."""

    status: ContractStatus | None = None
    contract_type: ContractType | None = None
    client_id: str | None = None
    commercial_manager_id: str | None = None
    account_manager_id: str | None = None
    is_expiring_soon: bool | None = None
    needs_adjustment: bool | None = None
    has_sla: bool | None = None
    min_value: Decimal | None = Field(None, ge=0)
    max_value: Decimal | None = Field(None, ge=0)
    start_date_from: date | None = None
    start_date_to: date | None = None
    end_date_from: date | None = None
    end_date_to: date | None = None
    search: str | None = None


class ContractListResponse(BaseModel):
    """Resposta paginada de contratos."""

    items: list[ContractResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ContractStats(BaseModel):
    """Estatísticas de contratos."""

    total_contracts: int
    active_contracts: int
    total_monthly_revenue: Decimal
    average_contract_value: Decimal
    expiring_soon: int
    needs_adjustment: int
    by_status: dict[str, int]
    by_type: dict[str, int]


# ============== Contract Item Schemas ==============


class ContractItemCreate(BaseModel):
    """Schema para criar item do contrato."""

    service_type: ServiceType
    service_name: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(..., ge=0)
    notes: str | None = None


class ContractItemUpdate(BaseModel):
    """Schema para atualizar item do contrato."""

    service_type: ServiceType | None = None
    service_name: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = None
    quantity: int | None = Field(None, ge=1)
    unit_price: Decimal | None = Field(None, ge=0)
    notes: str | None = None


# ============== Contract Addendum Schemas ==============


class ContractAddendumCreate(BaseModel):
    """Schema para criar aditivo."""

    addendum_type: AddendumType
    effective_date: date
    description: str = Field(..., min_length=10)
    reason: str | None = None

    # Valores (para reajuste)
    new_value: Decimal | None = Field(None, ge=0)
    adjustment_percent: Decimal | None = Field(None, ge=-100, le=100)
    adjustment_index: AdjustmentIndex | None = None

    @field_validator("new_value", "adjustment_percent")
    @classmethod
    def validate_adjustment_values(cls, v, info):
        """Valida valores de reajuste."""
        if info.data.get("addendum_type") == AddendumType.ADJUSTMENT:
            if info.field_name == "new_value" and v is None:
                if info.data.get("adjustment_percent") is None:
                    raise ValueError("Reajuste requer novo_valor ou percentual_reajuste")
        return v


class ContractAddendumResponse(BaseModel):
    """Resposta de aditivo."""

    id: str
    contract_id: str
    addendum_number: str
    addendum_type: AddendumType
    previous_value: Decimal | None = None
    new_value: Decimal | None = None
    adjustment_percent: Decimal | None = None
    adjustment_index: AdjustmentIndex | None = None
    effective_date: date
    description: str
    reason: str | None = None
    signed: bool
    signed_at: datetime | None = None
    pdf_file_path: str | None = None
    created_at: datetime
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContractAddendumSign(BaseModel):
    """Schema para assinar aditivo."""

    signature_document_id: str = Field(..., min_length=1, max_length=100)


# ============== Contract Template Schemas ==============


class ContractTemplateCreate(BaseModel):
    """Schema para criar template."""

    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = None
    service_type: ServiceType | None = None
    content_template: str = Field(..., min_length=100)
    clauses: list[dict[str, Any] | str] | None = None  # no banco há modelos com cláusulas em texto (08/09/2026)
    variables: list[str] | None = None


class ContractTemplateUpdate(BaseModel):
    """Schema para atualizar template."""

    name: str | None = Field(None, min_length=3, max_length=100)
    description: str | None = None
    service_type: ServiceType | None = None
    content_template: str | None = Field(None, min_length=100)
    clauses: list[dict[str, Any] | str] | None = None  # no banco há modelos com cláusulas em texto (08/09/2026)
    variables: list[str] | None = None


class ContractTemplateApprove(BaseModel):
    """Schema para aprovar template."""

    notes: str | None = None


class ContractTemplateResponse(BaseModel):
    """Resposta de template."""

    id: str
    name: str
    description: str | None = None
    # service_type aceita qualquer string — dados históricos ('admissao', 'ferias') pré-enum §20.7 H-T4-1
    service_type: str | None = None
    content_template: str
    clauses: list[dict[str, Any] | str] | None = None  # no banco há modelos com cláusulas em texto (08/09/2026)
    variables: list[str] | None = None
    version: int
    approved_by_legal: bool
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", mode="before")
    @classmethod
    def stringify_id(cls, v: Any) -> str:
        """Converte UUID para str — model usa UUID(as_uuid=True)."""
        return str(v) if v is not None else v

    @field_validator("variables", mode="before")
    @classmethod
    def normalize_variables(cls, v: Any) -> list[str] | None:
        """Aceita list[str] ou dict{required:[...]} — dados históricos §20.7."""
        if v is None:
            return None
        if isinstance(v, list):
            return [str(i) for i in v]
        if isinstance(v, dict):
            # {"required": [...]} ou qualquer dict
            items = v.get("required") or v.get("variables") or []
            if isinstance(items, list):
                return [str(i) for i in items]
            return list(v.keys())
        return None


class ContractTemplateListResponse(BaseModel):
    """Resposta de lista de templates."""

    items: list[ContractTemplateResponse]
    total: int


# ============== Contract SLA Report Schemas ==============


class SLAIndicatorResult(BaseModel):
    """Resultado de um indicador de SLA."""

    name: str
    target: Decimal
    actual: Decimal
    achieved: bool
    weight: Decimal = Field(default=Decimal("1"))


class ContractSLAReportCreate(BaseModel):
    """Schema para criar relatório de SLA."""

    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    indicators: list[SLAIndicatorResult]
    overall_score: Decimal = Field(..., ge=0, le=150)
    penalty_applied: bool = False
    penalty_percent: Decimal | None = Field(None, ge=0, le=100)
    penalty_amount: Decimal | None = Field(None, ge=0)


class ContractSLAReportResponse(BaseModel):
    """Resposta de relatório de SLA."""

    id: str
    contract_id: str
    year: int
    month: int
    indicators: list[dict[str, Any]]
    overall_score: Decimal
    penalty_applied: bool
    penalty_percent: Decimal
    penalty_amount: Decimal
    status: str
    period_label: str
    is_target_met: bool
    generated_at: datetime
    generated_by: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContractSLAReportApprove(BaseModel):
    """Schema para aprovar relatório de SLA."""

    disputed: bool = False
    dispute_reason: str | None = None
