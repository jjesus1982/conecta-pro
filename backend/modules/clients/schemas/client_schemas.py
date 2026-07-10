"""
Client Schemas - Pydantic Models
Sprint 30: Cadastro de Clientes/Condomínios

NOTA: Sincronizado com os models reais em 29/03/2026.
Enums foram substituídos por strings para corresponder ao banco de dados.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Valores válidos (correspondem aos enums do banco)
# =============================================================================

ClientTypeValues = Literal["pf", "pj", "condominium", "holding", "franchise", "government", "other"]
ClientStatusValues = Literal["prospect", "active", "suspended", "blocked", "cancelled", "defaulter", "churned"]
ClientSegmentValues = Literal["small", "medium", "large", "enterprise", "vip", "strategic"]
DocumentTypeValues = Literal["cpf", "cnpj", "passport", "rg", "other"]

CondominiumTypeValues = Literal[
    "residential", "commercial", "mixed", "industrial", "horizontal", "vertical", "subdivision"
]
CondominiumStatusValues = Literal["active", "inactive", "implementing", "suspended", "closed"]
AdministrationTypeValues = Literal["propria", "administradora", "sindico_profissional", "autogestao"]

UnitTypeValues = Literal[
    "apartment",
    "house",
    "store",
    "office",
    "warehouse",
    "parking",
    "storage",
    "penthouse",
    "duplex",
    "triplex",
    "garden",
    "rooftop",
    "common_area",
    "commercial",
]
UnitStatusValues = Literal["available", "occupied", "vacant", "renovation", "blocked", "reserved", "defaulter"]

ContractServiceTypeValues = Literal[
    "portaria_remota",
    "controle_acesso",
    "cftv",
    "alarme",
    "cerca_eletrica",
    "monitoramento_24h",
    "app_morador",
    "assembleia_virtual",
    "manutencao",
    "limpeza",
    "jardinagem",
    "administracao",
    "consultoria",
    "integracao",
    "suporte",
]
ServiceStatusValues = Literal["pending", "implantation", "active", "suspended", "cancelled", "finished"]

IntegrationTypeValues = Literal[
    "guardian", "plus", "erp_external", "banking", "nfe", "whatsapp", "email", "sms", "webhook"
]
SyncStatusValues = Literal["pending", "syncing", "synced", "error", "disabled"]
SyncDirectionValues = Literal["push", "pull", "bidirectional"]


# =============================================================================
# CLIENT SCHEMAS
# =============================================================================


# A tela do CRM envia o vocabulário PT (empresa/condominio/residencial/pessoa_fisica);
# a API fala EN (pj/condominium/pf). Traduzimos ANTES da validação para os dois conviverem.
_TIPO_PT_PARA_EN = {
    "empresa": "pj",
    "condominio": "condominium",
    "condomínio": "condominium",
    "residencial": "condominium",
    "pessoa_fisica": "pf",
    "orgao_publico": "government",
}


def _traduz_tipo_cliente(v):
    if isinstance(v, str):
        return _TIPO_PT_PARA_EN.get(v.strip().lower(), v)
    return v


class ClientBase(BaseModel):
    """Base schema for Client."""

    client_type: ClientTypeValues = Field(default="pj", alias="type")

    _trad_tipo = field_validator("client_type", mode="before")(_traduz_tipo_cliente)
    segment: ClientSegmentValues | None = None
    name: str = Field(..., min_length=2, max_length=200, alias="legal_name")
    trading_name: str | None = Field(None, max_length=200, alias="trade_name")
    document_type: DocumentTypeValues = Field(default="cnpj")
    document_number: str = Field(..., min_length=11, max_length=20)
    state_registration: str | None = Field(None, max_length=30)
    municipal_registration: str | None = Field(None, max_length=30)

    # Endereço
    address_street: str | None = Field(None, max_length=255)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)

    # Contatos
    phone: str | None = Field(None, max_length=20)
    mobile: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)

    # Contatos financeiro/técnico
    financial_contact_name: str | None = Field(None, max_length=200)
    financial_contact_email: str | None = Field(None, max_length=255)
    financial_contact_phone: str | None = Field(None, max_length=20)
    technical_contact_name: str | None = Field(None, max_length=200)
    technical_contact_email: str | None = Field(None, max_length=255)
    technical_contact_phone: str | None = Field(None, max_length=20)

    # Dados financeiros
    payment_terms: int | None = Field(None, ge=0, le=365)
    credit_limit: Decimal | None = Field(None, ge=0)
    billing_day: int | None = Field(None, ge=1, le=31)

    # Responsáveis
    sales_rep_id: UUID | None = None
    account_manager_id: UUID | None = None

    # Configurações
    tags: dict | list | None = None
    notes: str | None = None
    is_vip: bool = False

    model_config = {"populate_by_name": True}

    @field_validator("document_number")
    @classmethod
    def validate_document(cls, v: str) -> str:
        """Valida e formata documento."""
        return re.sub(r"\D", "", v)

    @field_validator("address_zipcode")
    @classmethod
    def validate_zipcode(cls, v: str | None) -> str | None:
        """Valida CEP."""
        if v:
            return re.sub(r"\D", "", v)
        return v


class ClientCreate(ClientBase):
    """Schema for creating a client."""


class ClientUpdate(BaseModel):
    """Schema for updating a client."""

    client_type: ClientTypeValues | None = Field(None, alias="type")

    _trad_tipo_upd = field_validator("client_type", mode="before")(_traduz_tipo_cliente)
    status: ClientStatusValues | None = None
    segment: ClientSegmentValues | None = None
    name: str | None = Field(None, min_length=2, max_length=200, alias="legal_name")
    trading_name: str | None = Field(None, max_length=200, alias="trade_name")
    document_number: str | None = Field(None, max_length=20)
    state_registration: str | None = Field(None, max_length=30)
    municipal_registration: str | None = Field(None, max_length=30)

    address_street: str | None = Field(None, max_length=255)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)

    phone: str | None = Field(None, max_length=20)
    mobile: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)

    financial_contact_name: str | None = Field(None, max_length=200)
    financial_contact_email: str | None = Field(None, max_length=255)
    financial_contact_phone: str | None = Field(None, max_length=20)
    technical_contact_name: str | None = Field(None, max_length=200)
    technical_contact_email: str | None = Field(None, max_length=255)
    technical_contact_phone: str | None = Field(None, max_length=20)

    payment_terms: int | None = Field(None, ge=0, le=365)
    credit_limit: Decimal | None = Field(None, ge=0)
    billing_day: int | None = Field(None, ge=1, le=31)

    sales_rep_id: UUID | None = None
    account_manager_id: UUID | None = None

    tags: dict | list | None = None
    notes: str | None = None
    is_vip: bool | None = None

    model_config = {"populate_by_name": True}


class ClientResponse(BaseModel):
    """Schema for client response."""

    id: UUID
    code: str
    client_type: str | None = Field(None, alias="type")
    status: str | None = None
    segment: str | None = None
    name: str | None = Field(None, alias="legal_name")
    trading_name: str | None = Field(None, alias="trade_name")
    document_type: str | None = None
    document_number: str | None = None
    formatted_document: str | None = None
    display_name: str | None = None
    full_address: str | None = None

    address_street: str | None = None
    address_number: str | None = None
    address_complement: str | None = None
    address_neighborhood: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zipcode: str | None = None

    phone: str | None = None
    email: str | None = None
    financial_contact_name: str | None = None

    payment_terms: int | None = None
    credit_limit: Decimal | None = None
    is_defaulter: bool = False
    total_debt: Decimal | None = None

    total_contracts: int | None = 0
    active_contracts: int | None = 0
    total_revenue: Decimal | None = None
    satisfaction_score: float | None = None
    health_score: float | None = None

    plus_enabled: bool = False
    guardian_enabled: bool = False

    is_active: bool = True
    is_vip: bool = False
    tags: dict | list | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ClientListResponse(BaseModel):
    """Schema for client list response."""

    id: UUID
    code: str
    client_type: str | None = Field(None, alias="type")
    status: str | None = None
    name: str | None = Field(None, alias="legal_name")
    trading_name: str | None = Field(None, alias="trade_name")
    display_name: str | None = None
    document_number: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    phone: str | None = None
    email: str | None = None
    is_defaulter: bool = False
    active_contracts: int | None = 0
    health_score: float | None = None
    is_vip: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ClientStats(BaseModel):
    """Schema for client statistics."""

    total_clients: int = 0
    active_clients: int = 0
    inactive_clients: int = 0
    defaulter_clients: int = 0
    vip_clients: int = 0
    by_type: dict = Field(default_factory=dict)
    by_status: dict = Field(default_factory=dict)
    by_segment: dict = Field(default_factory=dict)
    total_revenue: Decimal = Decimal("0")
    average_contracts_per_client: float = 0.0


class ClientFilter(BaseModel):
    """Schema for filtering clients."""

    client_type: str | None = Field(None, alias="type")
    status: str | None = None
    segment: str | None = None
    is_defaulter: bool | None = None
    is_vip: bool | None = None
    plus_enabled: bool | None = None
    city: str | None = None
    state: str | None = None
    sales_rep_id: UUID | None = None
    search: str | None = None

    model_config = {"populate_by_name": True}


# =============================================================================
# CONDOMINIUM SCHEMAS
# =============================================================================


class CondominiumBase(BaseModel):
    """Base schema for Condominium."""

    name: str = Field(..., min_length=2, max_length=200)
    condominium_type: CondominiumTypeValues = Field(default="residential", alias="type")
    administration_type: AdministrationTypeValues | None = None
    cnpj: str | None = Field(None, max_length=18)

    address_street: str = Field(..., min_length=2, max_length=255)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str = Field(..., min_length=2, max_length=100)
    address_state: str = Field(..., min_length=2, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None

    syndic_name: str | None = Field(None, max_length=200)
    syndic_phone: str | None = Field(None, max_length=20)
    syndic_email: str | None = Field(None, max_length=255)

    total_units: int = Field(default=0, ge=0)
    total_towers: int | None = Field(None, ge=0)
    total_floors: int | None = Field(None, ge=0)
    total_parking_spaces: int | None = Field(None, ge=0)

    has_pool: bool = False
    has_gym: bool = False
    has_party_room: bool = False
    has_playground: bool = False
    has_24h_security: bool = False
    has_cctv: bool = False
    has_access_control: bool = False

    tags: dict | list | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True}


class CondominiumCreate(CondominiumBase):
    """Schema for creating a condominium."""

    client_id: UUID


class CondominiumUpdate(BaseModel):
    """Schema for updating a condominium."""

    name: str | None = Field(None, min_length=2, max_length=200)
    condominium_type: CondominiumTypeValues | None = Field(None, alias="type")
    status: CondominiumStatusValues | None = None
    administration_type: AdministrationTypeValues | None = None
    cnpj: str | None = Field(None, max_length=18)

    address_street: str | None = Field(None, max_length=255)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)

    syndic_name: str | None = Field(None, max_length=200)
    syndic_phone: str | None = Field(None, max_length=20)
    syndic_email: str | None = Field(None, max_length=255)
    syndic_mandate_start: date | None = None
    syndic_mandate_end: date | None = None

    total_units: int | None = Field(None, ge=0)
    total_towers: int | None = Field(None, ge=0)

    has_pool: bool | None = None
    has_gym: bool | None = None
    has_party_room: bool | None = None
    has_24h_security: bool | None = None
    has_cctv: bool | None = None
    has_access_control: bool | None = None

    tags: dict | list | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True}


class CondominiumResponse(BaseModel):
    """Schema for condominium response."""

    id: UUID
    code: str | None = None
    client_id: UUID | None = None
    name: str | None = None
    condominium_type: str | None = None
    status: str | None = None
    administration_type: str | None = None
    cnpj: str | None = None
    full_address: str | None = None
    address_city: str | None = None
    address_state: str | None = None

    syndic_name: str | None = None
    syndic_phone: str | None = None
    syndic_mandate_active: bool | None = None

    total_units: int | None = 0
    occupied_units: int | None = 0
    occupancy_rate: float | None = 0.0
    total_towers: int | None = None

    security_level: str | None = None
    amenities_count: int | None = 0

    plus_enabled: bool | None = False
    is_active: bool | None = True
    is_premium: bool | None = False

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CondominiumListResponse(BaseModel):
    """Schema for condominium list response."""

    id: UUID
    code: str | None = None
    client_id: UUID | None = None
    name: str | None = None
    condominium_type: str | None = None
    status: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    total_units: int | None = 0
    occupancy_rate: float | None = 0.0
    security_level: str | None = None
    is_premium: bool | None = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CondominiumStats(BaseModel):
    """Schema for condominium statistics."""

    total_condominiums: int = 0
    active_condominiums: int = 0
    total_units: int = 0
    occupied_units: int = 0
    average_occupancy_rate: float = 0.0
    by_type: dict = Field(default_factory=dict)
    by_status: dict = Field(default_factory=dict)
    by_city: dict = Field(default_factory=dict)


# =============================================================================
# UNIT SCHEMAS
# =============================================================================


class UnitBase(BaseModel):
    """Base schema for Unit."""

    unit_number: str = Field(..., min_length=1, max_length=20, alias="number")
    block: str | None = Field(None, max_length=50)
    tower: str | None = Field(None, max_length=50)
    floor: int | None = None
    unit_type: UnitTypeValues = Field(default="apartment", alias="type")

    private_area: float | None = Field(None, ge=0, alias="area_m2")
    bedrooms: int | None = Field(None, ge=0)
    bathrooms: int | None = Field(None, ge=0)
    parking_spaces: int | None = Field(None, ge=0, alias="parking_spots")

    owner_name: str | None = Field(None, max_length=200)
    owner_document: str | None = Field(None, max_length=20)
    owner_phone: str | None = Field(None, max_length=20)
    owner_email: str | None = Field(None, max_length=255)

    condominium_fee: Decimal | None = Field(None, ge=0, alias="monthly_fee")
    extra_fee: Decimal | None = Field(None, ge=0)

    notes: str | None = None
    tags: dict | list | None = None

    model_config = {"populate_by_name": True}


class UnitCreate(UnitBase):
    """Schema for creating a unit."""

    condominium_id: UUID


class UnitUpdate(BaseModel):
    """Schema for updating a unit."""

    unit_number: str | None = Field(None, max_length=20, alias="number")
    block: str | None = Field(None, max_length=50)
    tower: str | None = Field(None, max_length=50)
    floor: int | None = None
    unit_type: UnitTypeValues | None = Field(None, alias="type")
    status: UnitStatusValues | None = None

    private_area: float | None = Field(None, ge=0, alias="area_m2")
    bedrooms: int | None = Field(None, ge=0)
    bathrooms: int | None = Field(None, ge=0)
    parking_spaces: int | None = Field(None, ge=0, alias="parking_spots")

    owner_name: str | None = Field(None, max_length=200)
    owner_document: str | None = Field(None, max_length=20)
    owner_phone: str | None = Field(None, max_length=20)
    owner_email: str | None = Field(None, max_length=255)

    resident_name: str | None = Field(None, max_length=200)
    resident_phone: str | None = Field(None, max_length=20)
    resident_email: str | None = Field(None, max_length=255)
    resident_type: str | None = Field(None, max_length=20)

    condominium_fee: Decimal | None = Field(None, ge=0, alias="monthly_fee")
    extra_fee: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    tags: dict | list | None = None

    model_config = {"populate_by_name": True}


class UnitResponse(BaseModel):
    """Schema for unit response."""

    id: UUID
    code: str | None = None
    condominium_id: UUID
    unit_number: str | None = Field(None, alias="number")
    block: str | None = None
    tower: str | None = None
    floor: int | None = None
    unit_type: str | None = Field(None, alias="type")
    status: str | None = None
    display_name: str | None = None
    short_name: str | None = None

    private_area: float | None = Field(None, alias="area_m2")
    bedrooms: int | None = None
    parking_spaces: int | None = Field(None, alias="parking_spots")

    owner_name: str | None = None
    resident_name: str | None = None
    current_resident: str | None = None
    is_tenant: bool = False
    is_occupied: bool = False

    condominium_fee: Decimal | None = Field(None, alias="monthly_fee")
    total_fee: Decimal | None = None
    is_defaulter: bool = False
    debt_amount: Decimal | None = None

    has_access_credentials: bool = False
    total_authorized_persons: int = 0
    total_vehicles: int = 0

    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class UnitListResponse(BaseModel):
    """Schema for unit list response."""

    id: UUID
    code: str | None = None
    unit_number: str | None = Field(None, alias="number")
    block: str | None = None
    tower: str | None = None
    unit_type: str | None = Field(None, alias="type")
    status: str | None = None
    display_name: str | None = None
    current_resident: str | None = None
    is_occupied: bool = False
    is_defaulter: bool = False
    condominium_fee: Decimal | None = Field(None, alias="monthly_fee")

    model_config = {"from_attributes": True, "populate_by_name": True}


class UnitStats(BaseModel):
    """Schema for unit statistics."""

    total_units: int = 0
    occupied_units: int = 0
    available_units: int = 0
    defaulter_units: int = 0
    occupancy_rate: float = 0.0
    by_type: dict = Field(default_factory=dict)
    by_status: dict = Field(default_factory=dict)
    total_monthly_fees: Decimal = Decimal("0")


# =============================================================================
# CLIENT CONTRACT SCHEMAS
# =============================================================================


class ClientContractBase(BaseModel):
    """Base schema for ClientContract."""

    service_type: ContractServiceTypeValues
    description: str | None = Field(None, max_length=500)
    monthly_value: Decimal | None = Field(None, ge=0)
    implantation_value: Decimal | None = Field(None, ge=0)
    discount_percentage: float | None = Field(None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    sla_response_time: int | None = Field(None, ge=0)
    sla_resolution_time: int | None = Field(None, ge=0)
    auto_renewal: bool = False
    notes: str | None = None


class ClientContractCreate(ClientContractBase):
    """Schema for creating a client contract."""

    client_id: UUID
    contract_number: str | None = None
    condominium_id: UUID | None = None


class ClientContractUpdate(BaseModel):
    """Schema for updating a client contract."""

    service_type: ContractServiceTypeValues | None = None
    status: ServiceStatusValues | None = None
    description: str | None = Field(None, max_length=500)
    monthly_value: Decimal | None = Field(None, ge=0)
    discount_percentage: float | None = Field(None, ge=0, le=100)
    end_date: date | None = None
    sla_response_time: int | None = Field(None, ge=0)
    sla_resolution_time: int | None = Field(None, ge=0)
    notes: str | None = None
    auto_renewal: bool | None = None


class ClientContractResponse(BaseModel):
    """Schema for client contract response."""

    id: UUID
    client_id: UUID
    contract_number: str | None = None
    condominium_id: UUID | None = None
    service_type: str | None = None
    status: str | None = None
    description: str | None = None
    monthly_value: Decimal | None = None
    final_value: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    days_until_end: int | None = None
    is_expiring_soon: bool = False
    is_electronic_security_service: bool = False
    is_plus_service: bool = False
    is_active: bool = True
    is_main_service: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# INTEGRATION SETTINGS SCHEMAS
# =============================================================================


class IntegrationSettingsBase(BaseModel):
    """Base schema for IntegrationSettings."""

    integration_type: IntegrationTypeValues
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    sync_direction: SyncDirectionValues = Field(default="bidirectional")
    api_url: str | None = Field(None, max_length=500)
    sync_interval_minutes: int | None = Field(None, ge=1)
    notes: str | None = None


class IntegrationSettingsCreate(IntegrationSettingsBase):
    """Schema for creating integration settings."""

    client_id: UUID
    condominium_id: UUID | None = None
    api_key: str | None = Field(None, max_length=255)
    api_secret: str | None = Field(None, max_length=255)
    webhook_url: str | None = Field(None, max_length=500)
    webhook_secret: str | None = Field(None, max_length=255)


class IntegrationSettingsUpdate(BaseModel):
    """Schema for updating integration settings."""

    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    sync_direction: SyncDirectionValues | None = None
    api_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=255)
    api_secret: str | None = Field(None, max_length=255)
    webhook_url: str | None = Field(None, max_length=500)
    sync_interval_minutes: int | None = Field(None, ge=1)
    notes: str | None = None
    enabled: bool | None = Field(None, alias="is_enabled")

    model_config = {"populate_by_name": True}


class IntegrationSettingsResponse(BaseModel):
    """Schema for integration settings response."""

    id: UUID
    client_id: UUID
    condominium_id: UUID | None = None
    integration_type: str | None = None
    name: str | None = None
    description: str | None = None
    sync_status: str | None = None
    sync_direction: str | None = None
    api_url: str | None = None
    external_client_id: str | None = None
    webhook_url: str | None = None
    sync_interval_minutes: int | None = None
    last_sync_at: datetime | None = None
    last_sync_success_at: datetime | None = None
    last_sync_error: str | None = None
    success_rate: float = 0.0
    total_syncs: int = 0
    records_synced: int = 0
    is_configured: bool = False
    is_enabled: bool = False
    is_active: bool = True
    auto_sync: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
