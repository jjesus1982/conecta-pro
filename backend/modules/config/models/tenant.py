"""
Tenant Model - Inquilinos do Sistema Multi-tenant
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-many-instance-attributes

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class TenantStatus(StrEnum):
    """Status do tenant."""

    ATIVO = "active"
    INATIVO = "inactive"
    SUSPENSO = "suspended"
    BLOQUEADO = "blocked"
    TRIAL = "trial"
    CANCELADO = "cancelled"


class TenantPlan(StrEnum):
    """Plano do tenant."""

    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class TenantType(StrEnum):
    """Tipo de tenant."""

    EMPRESA = "empresa"
    CONDOMINIO = "condominio"
    FRANQUIA = "franquia"
    PARCEIRO = "parceiro"
    INTERNO = "interno"


class Tenant(Base):
    """Model de Tenant - Inquilino do sistema."""

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    nome_fantasia = Column(String(200), nullable=True)
    descricao = Column(Text, nullable=True)

    # Tipo e status
    # values_callable: o DB guarda o .value (ex: 'active'), não o nome do membro (ATIVO).
    # Sem isso o SQLAlchemy mapeia pelo NOME e dá LookupError ao ler 'active'.
    tenant_type = Column(
        Enum(TenantType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TenantType.EMPRESA,
    )
    status = Column(
        Enum(TenantStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TenantStatus.TRIAL,
    )
    plan = Column(
        Enum(TenantPlan, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TenantPlan.FREE,
    )

    # Documentos
    cnpj = Column(String(18), nullable=True, unique=True)
    inscricao_estadual = Column(String(20), nullable=True)
    inscricao_municipal = Column(String(20), nullable=True)

    # Contato
    email = Column(String(255), nullable=False)
    telefone = Column(String(20), nullable=True)
    celular = Column(String(20), nullable=True)
    website = Column(String(255), nullable=True)

    # Endereço (JSONB: logradouro, numero, complemento, bairro, cidade, estado, cep)
    endereco = Column(JSONB, nullable=True)

    # Responsável
    responsavel_nome = Column(String(200), nullable=True)
    responsavel_email = Column(String(255), nullable=True)
    responsavel_telefone = Column(String(20), nullable=True)

    # Configurações de acesso
    dominio_personalizado = Column(String(255), nullable=True, unique=True)
    subdominio = Column(String(100), nullable=True, unique=True)
    logo_url = Column(String(500), nullable=True)
    favicon_url = Column(String(500), nullable=True)
    tema = Column(JSONB, nullable=True)  # {cores, fontes, etc}

    # Limites do plano
    max_usuarios = Column(Integer, nullable=False, default=5)
    max_storage_gb = Column(Integer, nullable=False, default=1)
    max_api_calls_month = Column(Integer, nullable=False, default=10000)
    usuarios_ativos = Column(Integer, nullable=False, default=0)
    storage_usado_mb = Column(Integer, nullable=False, default=0)
    api_calls_mes = Column(Integer, nullable=False, default=0)

    # Datas de controle
    data_inicio = Column(DateTime(timezone=True), nullable=True)
    data_fim = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspension_reason = Column(Text, nullable=True)

    # Billing
    billing_email = Column(String(255), nullable=True)
    billing_cycle = Column(String(20), nullable=True)  # mensal, anual
    next_billing_date = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)

    # Recursos habilitados
    features_enabled = Column(JSONB, nullable=True)  # Lista de features ativas
    modules_enabled = Column(JSONB, nullable=True)  # Lista de módulos ativos
    integrations_enabled = Column(JSONB, nullable=True)  # Lista de integrações ativas

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Controle
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_tenants_status", "status"),
        Index("ix_tenants_plan", "plan"),
        Index("ix_tenants_tenant_type", "tenant_type"),
        Index("ix_tenants_cnpj", "cnpj"),
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.codigo}: {self.nome}>"

    # ==================== Propriedades ====================

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == TenantStatus.ATIVO and self.ativo

    @property
    def is_trial(self) -> bool:
        """Verifica se está em trial."""
        return self.status == TenantStatus.TRIAL

    @property
    def is_suspended(self) -> bool:
        """Verifica se está suspenso."""
        return self.status in [TenantStatus.SUSPENSO, TenantStatus.BLOQUEADO]

    @property
    def trial_expired(self) -> bool:
        """Verifica se trial expirou."""
        if not self.trial_ends_at:
            return False
        return datetime.utcnow() > self.trial_ends_at

    @property
    def storage_usage_percent(self) -> float:
        """Percentual de uso de storage."""
        if self.max_storage_gb <= 0:
            return 0.0
        max_mb = self.max_storage_gb * 1024
        return round((self.storage_usado_mb / max_mb) * 100, 2)

    @property
    def users_usage_percent(self) -> float:
        """Percentual de uso de usuários."""
        if self.max_usuarios <= 0:
            return 0.0
        return round((self.usuarios_ativos / self.max_usuarios) * 100, 2)

    @property
    def api_usage_percent(self) -> float:
        """Percentual de uso de API calls."""
        if self.max_api_calls_month <= 0:
            return 0.0
        return round((self.api_calls_mes / self.max_api_calls_month) * 100, 2)

    @property
    def full_domain(self) -> str | None:
        """Retorna domínio completo."""
        if self.dominio_personalizado:
            return self.dominio_personalizado
        if self.subdominio:
            return f"{self.subdominio}.conectamais.com.br"
        return None

    # ==================== Métodos ====================

    def activate(self) -> None:
        """Ativa o tenant."""
        self.status = TenantStatus.ATIVO
        self.suspended_at = None
        self.suspension_reason = None
        self.updated_at = datetime.utcnow()

    def suspend(self, reason: str = None) -> None:
        """Suspende o tenant."""
        self.status = TenantStatus.SUSPENSO
        self.suspended_at = datetime.utcnow()
        self.suspension_reason = reason
        self.updated_at = datetime.utcnow()

    def block(self, reason: str = None) -> None:
        """Bloqueia o tenant."""
        self.status = TenantStatus.BLOQUEADO
        self.suspended_at = datetime.utcnow()
        self.suspension_reason = reason
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        """Cancela o tenant."""
        self.status = TenantStatus.CANCELADO
        self.ativo = False
        self.data_fim = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def upgrade_plan(self, new_plan: TenantPlan, limits: dict = None) -> None:
        """Atualiza plano do tenant."""
        self.plan = new_plan
        if limits:
            if "max_usuarios" in limits:
                self.max_usuarios = limits["max_usuarios"]
            if "max_storage_gb" in limits:
                self.max_storage_gb = limits["max_storage_gb"]
            if "max_api_calls_month" in limits:
                self.max_api_calls_month = limits["max_api_calls_month"]
        self.updated_at = datetime.utcnow()

    def increment_users(self, count: int = 1) -> bool:
        """Incrementa contador de usuários. Retorna False se exceder limite."""
        if self.usuarios_ativos + count > self.max_usuarios:
            return False
        self.usuarios_ativos += count
        return True

    def decrement_users(self, count: int = 1) -> None:
        """Decrementa contador de usuários."""
        self.usuarios_ativos = max(0, self.usuarios_ativos - count)

    def add_storage_usage(self, mb: int) -> bool:
        """Adiciona uso de storage. Retorna False se exceder limite."""
        max_mb = self.max_storage_gb * 1024
        if self.storage_usado_mb + mb > max_mb:
            return False
        self.storage_usado_mb += mb
        return True

    def increment_api_calls(self, count: int = 1) -> bool:
        """Incrementa contador de API calls. Retorna False se exceder limite."""
        if self.api_calls_mes + count > self.max_api_calls_month:
            return False
        self.api_calls_mes += count
        return True

    def reset_api_calls(self) -> None:
        """Reseta contador de API calls (início do mês)."""
        self.api_calls_mes = 0
        self.updated_at = datetime.utcnow()

    def enable_feature(self, feature: str) -> None:
        """Habilita uma feature."""
        if self.features_enabled is None:
            self.features_enabled = []
        if feature not in self.features_enabled:
            self.features_enabled = [*self.features_enabled, feature]
            self.updated_at = datetime.utcnow()

    def disable_feature(self, feature: str) -> None:
        """Desabilita uma feature."""
        if self.features_enabled and feature in self.features_enabled:
            self.features_enabled = [f for f in self.features_enabled if f != feature]
            self.updated_at = datetime.utcnow()

    def has_feature(self, feature: str) -> bool:
        """Verifica se feature está habilitada."""
        return self.features_enabled and feature in self.features_enabled

    def enable_module(self, module: str) -> None:
        """Habilita um módulo."""
        if self.modules_enabled is None:
            self.modules_enabled = []
        if module not in self.modules_enabled:
            self.modules_enabled = [*self.modules_enabled, module]
            self.updated_at = datetime.utcnow()

    def disable_module(self, module: str) -> None:
        """Desabilita um módulo."""
        if self.modules_enabled and module in self.modules_enabled:
            self.modules_enabled = [m for m in self.modules_enabled if m != module]
            self.updated_at = datetime.utcnow()

    def has_module(self, module: str) -> bool:
        """Verifica se módulo está habilitado."""
        return self.modules_enabled and module in self.modules_enabled

    def set_theme(self, theme_config: dict) -> None:
        """Define configuração de tema."""
        self.tema = theme_config
        self.updated_at = datetime.utcnow()

    def set_address(
        self, logradouro: str, numero: str, bairro: str, cidade: str, estado: str, cep: str, complemento: str = None
    ) -> None:
        """Define endereço do tenant."""
        self.endereco = {
            "logradouro": logradouro,
            "numero": numero,
            "complemento": complemento,
            "bairro": bairro,
            "cidade": cidade,
            "estado": estado,
            "cep": cep,
        }
        self.updated_at = datetime.utcnow()

    def convert_from_trial(self, plan: TenantPlan = TenantPlan.STARTER) -> None:
        """Converte de trial para plano pago."""
        if self.status == TenantStatus.TRIAL:
            self.status = TenantStatus.ATIVO
            self.plan = plan
            self.trial_ends_at = None
            self.data_inicio = datetime.utcnow()
            self.updated_at = datetime.utcnow()

    def extend_trial(self, days: int) -> None:
        """Estende período de trial."""
        if self.trial_ends_at:
            self.trial_ends_at = self.trial_ends_at + timedelta(days=days)
        else:
            self.trial_ends_at = datetime.utcnow() + timedelta(days=days)
        self.updated_at = datetime.utcnow()
