"""
Schemas Pydantic para o módulo de Configurações e Multi-tenant
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-few-public-methods

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# ==================== Tenant Schemas ====================


class TenantBase(BaseModel):
    """Schema base para Tenant."""

    codigo: str = Field(..., min_length=1, max_length=50)
    nome: str = Field(..., min_length=1, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)
    descricao: str | None = None
    tenant_type: str | None = Field(default="empresa")
    cnpj: str | None = Field(None, max_length=18)
    email: EmailStr
    telefone: str | None = Field(None, max_length=20)
    celular: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=255)


class TenantCreate(TenantBase):
    """Schema para criação de Tenant."""

    plan: str = Field(default="free")
    max_usuarios: int = Field(default=5, ge=1)
    max_storage_gb: int = Field(default=1, ge=1)
    trial_days: int | None = Field(default=14, ge=0)


class TenantUpdate(BaseModel):
    """Schema para atualização de Tenant."""

    nome: str | None = Field(None, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)
    descricao: str | None = None
    email: EmailStr | None = None
    telefone: str | None = Field(None, max_length=20)
    celular: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=255)
    logo_url: str | None = Field(None, max_length=500)
    tema: dict[str, Any] | None = None


class TenantPlanUpdate(BaseModel):
    """Schema para atualização de plano."""

    plan: str
    max_usuarios: int | None = Field(None, ge=1)
    max_storage_gb: int | None = Field(None, ge=1)
    max_api_calls_month: int | None = Field(None, ge=1000)


class TenantAddressUpdate(BaseModel):
    """Schema para atualização de endereço."""

    logradouro: str = Field(..., max_length=200)
    numero: str = Field(..., max_length=20)
    complemento: str | None = Field(None, max_length=100)
    bairro: str = Field(..., max_length=100)
    cidade: str = Field(..., max_length=100)
    estado: str = Field(..., max_length=2)
    cep: str = Field(..., max_length=10)


class TenantResponse(TenantBase):
    """Schema de resposta para Tenant."""

    id: UUID
    status: str | None = None
    plan: str | None = None
    max_usuarios: int
    max_storage_gb: int
    max_api_calls_month: int
    usuarios_ativos: int
    storage_usado_mb: int
    api_calls_mes: int
    dominio_personalizado: str | None
    subdominio: str | None
    logo_url: str | None
    data_inicio: datetime | None
    trial_ends_at: datetime | None
    features_enabled: list[str] | None
    modules_enabled: list[str] | None
    ativo: bool
    created_at: datetime

    class Config:
        """Configuração do schema."""

        from_attributes = True


class TenantList(BaseModel):
    """Schema para listagem de Tenants."""

    items: list[TenantResponse]
    total: int
    skip: int
    limit: int


class TenantFilter(BaseModel):
    """Schema para filtro de Tenants."""

    status: str | None = None
    plan: str | None = None
    tenant_type: str | None = None
    search: str | None = None


# ==================== TenantSettings Schemas ====================


class TenantSettingsBase(BaseModel):
    """Schema base para TenantSettings."""

    chave: str = Field(..., max_length=100)
    nome: str = Field(..., max_length=200)
    descricao: str | None = None
    category: str = Field(default="geral")
    setting_type: str = Field(default="string")


class TenantSettingsCreate(TenantSettingsBase):
    """Schema para criação de TenantSettings."""

    tenant_id: UUID
    valor: str | None = None
    valor_default: str | None = None
    required: bool = False
    visible: bool = True
    editable: bool = True
    group: str | None = None


class TenantSettingsUpdate(BaseModel):
    """Schema para atualização de TenantSettings."""

    valor: str | None = None
    nome: str | None = Field(None, max_length=200)
    descricao: str | None = None
    visible: bool | None = None
    editable: bool | None = None


class TenantSettingsValueUpdate(BaseModel):
    """Schema para atualização de valor."""

    valor: Any


class TenantSettingsResponse(TenantSettingsBase):
    """Schema de resposta para TenantSettings."""

    id: UUID
    tenant_id: UUID
    valor: str | None
    valor_default: str | None
    required: bool
    visible: bool
    editable: bool
    group: str | None
    display_order: int
    sensitive: bool
    last_modified_at: datetime | None
    ativo: bool
    created_at: datetime

    class Config:
        """Configuração do schema."""

        from_attributes = True


class TenantSettingsList(BaseModel):
    """Schema para listagem de TenantSettings."""

    items: list[TenantSettingsResponse]
    total: int


class TenantSettingsFilter(BaseModel):
    """Schema para filtro de TenantSettings."""

    category: str | None = None
    group: str | None = None
    visible: bool | None = None


# ==================== SystemConfig Schemas ====================


class SystemConfigBase(BaseModel):
    """Schema base para SystemConfig."""

    chave: str = Field(..., max_length=100)
    nome: str = Field(..., max_length=200)
    descricao: str | None = None
    scope: str = Field(default="global")
    valor_type: str = Field(default="string")


class SystemConfigCreate(SystemConfigBase):
    """Schema para criação de SystemConfig."""

    valor: str | None = None
    priority: str = Field(default="normal")
    cacheable: bool = True
    cache_ttl_seconds: int = Field(default=3600, ge=0)
    override_allowed: bool = True
    admin_only: bool = False
    category: str | None = None
    group: str | None = None


class SystemConfigUpdate(BaseModel):
    """Schema para atualização de SystemConfig."""

    valor: str | None = None
    nome: str | None = Field(None, max_length=200)
    descricao: str | None = None
    cacheable: bool | None = None
    cache_ttl_seconds: int | None = Field(None, ge=0)
    visible: bool | None = None
    editable: bool | None = None


class SystemConfigValueUpdate(BaseModel):
    """Schema para atualização de valor."""

    valor: Any


class SystemConfigResponse(SystemConfigBase):
    """Schema de resposta para SystemConfig."""

    id: UUID
    valor: str | None
    priority: str
    cacheable: bool
    cache_ttl_seconds: int
    requires_restart: bool
    override_allowed: bool
    admin_only: bool
    category: str | None
    group: str | None
    display_order: int
    visible: bool
    editable: bool
    version: int
    last_modified_at: datetime | None
    ativo: bool
    created_at: datetime

    class Config:
        """Configuração do schema."""

        from_attributes = True


class SystemConfigList(BaseModel):
    """Schema para listagem de SystemConfig."""

    items: list[SystemConfigResponse]
    total: int


class SystemConfigFilter(BaseModel):
    """Schema para filtro de SystemConfig."""

    scope: str | None = None
    category: str | None = None
    priority: str | None = None
    admin_only: bool | None = None


# ==================== FeatureFlag Schemas ====================


class FeatureFlagBase(BaseModel):
    """Schema base para FeatureFlag."""

    codigo: str = Field(..., max_length=100)
    nome: str = Field(..., max_length=200)
    descricao: str | None = None
    flag_type: str = Field(default="release")


class FeatureFlagCreate(FeatureFlagBase):
    """Schema para criação de FeatureFlag."""

    status: str = Field(default="inativo")
    rollout_strategy: str = Field(default="none")
    rollout_percentage: float = Field(default=0, ge=0, le=100)
    category: str | None = None
    owner_team: str | None = None
    jira_ticket: str | None = None


class FeatureFlagUpdate(BaseModel):
    """Schema para atualização de FeatureFlag."""

    nome: str | None = Field(None, max_length=200)
    descricao: str | None = None
    category: str | None = None
    owner_team: str | None = None
    jira_ticket: str | None = None
    documentation_url: str | None = None


class FeatureFlagRolloutUpdate(BaseModel):
    """Schema para atualização de rollout."""

    rollout_strategy: str
    rollout_percentage: float | None = Field(None, ge=0, le=100)


class FeatureFlagGradualRollout(BaseModel):
    """Schema para rollout gradual."""

    start_percentage: float = Field(..., ge=0, le=100)
    end_percentage: float = Field(..., ge=0, le=100)
    duration_days: int = Field(..., ge=1, le=365)


class FeatureFlagTenantToggle(BaseModel):
    """Schema para toggle de tenant."""

    tenant_id: str
    enabled: bool


class FeatureFlagUserToggle(BaseModel):
    """Schema para toggle de usuário."""

    user_id: str
    enabled: bool


class FeatureFlagEvaluate(BaseModel):
    """Schema para avaliação de flag."""

    tenant_id: str | None = None
    user_id: str | None = None
    attributes: dict[str, Any] | None = None


class FeatureFlagEvaluateResponse(BaseModel):
    """Schema de resposta para avaliação."""

    enabled: bool
    variant: str | None = None


class FeatureFlagResponse(FeatureFlagBase):
    """Schema de resposta para FeatureFlag."""

    id: UUID
    status: str
    rollout_strategy: str
    rollout_percentage: float
    enabled_tenants: list[str] | None
    disabled_tenants: list[str] | None
    enabled_users: list[str] | None
    disabled_users: list[str] | None
    gradual_start_date: datetime | None
    gradual_end_date: datetime | None
    variants: list[dict[str, Any]] | None
    scheduled_enable_at: datetime | None
    scheduled_disable_at: datetime | None
    expires_at: datetime | None
    evaluation_count: int
    enabled_count: int
    disabled_count: int
    category: str | None
    owner_team: str | None
    ativo: bool
    created_at: datetime

    class Config:
        """Configuração do schema."""

        from_attributes = True


class FeatureFlagList(BaseModel):
    """Schema para listagem de FeatureFlag."""

    items: list[FeatureFlagResponse]
    total: int
    skip: int
    limit: int


class FeatureFlagFilter(BaseModel):
    """Schema para filtro de FeatureFlag."""

    status: str | None = None
    flag_type: str | None = None
    category: str | None = None
    owner_team: str | None = None


# ==================== NotificationTemplate Schemas ====================


class NotificationTemplateBase(BaseModel):
    """Schema base para NotificationTemplate."""

    codigo: str = Field(..., max_length=100)
    nome: str = Field(..., max_length=200)
    descricao: str | None = None
    channel: str = Field(default="email")
    notification_type: str = Field(default="transacional")


class NotificationTemplateCreate(NotificationTemplateBase):
    """Schema para criação de NotificationTemplate."""

    tenant_id: UUID | None = None
    email_subject: str | None = Field(None, max_length=500)
    email_body_html: str | None = None
    email_body_text: str | None = None
    sms_body: str | None = None
    push_title: str | None = Field(None, max_length=200)
    push_body: str | None = None
    in_app_title: str | None = Field(None, max_length=200)
    in_app_body: str | None = None
    language: str = Field(default="pt-BR")
    category: str | None = None


class NotificationTemplateUpdate(BaseModel):
    """Schema para atualização de NotificationTemplate."""

    nome: str | None = Field(None, max_length=200)
    descricao: str | None = None
    email_subject: str | None = Field(None, max_length=500)
    email_body_html: str | None = None
    email_body_text: str | None = None
    sms_body: str | None = None
    push_title: str | None = Field(None, max_length=200)
    push_body: str | None = None
    in_app_title: str | None = Field(None, max_length=200)
    in_app_body: str | None = None
    priority: int | None = Field(None, ge=1, le=5)
    category: str | None = None


class NotificationTemplateRender(BaseModel):
    """Schema para renderização de template."""

    variables: dict[str, Any]


class NotificationTemplateRenderResponse(BaseModel):
    """Schema de resposta para renderização."""

    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    title: str | None = None
    body: str | None = None


class NotificationTemplateResponse(NotificationTemplateBase):
    """Schema de resposta para NotificationTemplate."""

    id: UUID
    tenant_id: UUID | None
    status: str
    email_subject: str | None
    email_from_name: str | None
    email_from_address: str | None
    sms_body: str | None
    push_title: str | None
    push_body: str | None
    in_app_title: str | None
    in_app_body: str | None
    available_variables: list[dict[str, Any]] | None
    language: str
    priority: int
    track_opens: bool
    track_clicks: bool
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    version: int
    category: str | None
    ativo: bool
    created_at: datetime

    class Config:
        """Configuração do schema."""

        from_attributes = True


class NotificationTemplateList(BaseModel):
    """Schema para listagem de NotificationTemplate."""

    items: list[NotificationTemplateResponse]
    total: int
    skip: int
    limit: int


class NotificationTemplateFilter(BaseModel):
    """Schema para filtro de NotificationTemplate."""

    channel: str | None = None
    notification_type: str | None = None
    status: str | None = None
    category: str | None = None
    tenant_id: UUID | None = None


# ==================== Dashboard Schemas ====================


class ConfigDashboard(BaseModel):
    """Schema para dashboard de configurações."""

    total_tenants: int
    active_tenants: int
    trial_tenants: int
    suspended_tenants: int
    total_configs: int
    total_feature_flags: int
    active_feature_flags: int
    total_notification_templates: int
    recent_tenants: list[dict[str, Any]]
    feature_flags_stats: dict[str, Any]


class TenantDashboard(BaseModel):
    """Schema para dashboard do tenant."""

    tenant: TenantResponse
    settings_count: int
    feature_flags_enabled: int
    notification_templates: int
    storage_usage_percent: float
    users_usage_percent: float
    api_usage_percent: float
