"""
FeatureFlag Model - Feature Flags
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-many-instance-attributes

import hashlib
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class FlagStatus(StrEnum):
    """Status da feature flag."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    GRADUAL = "gradual"  # Rollout gradual
    BETA = "beta"  # Disponível apenas para beta testers
    DEPRECATED = "deprecated"


class FlagType(StrEnum):
    """Tipo de feature flag."""

    RELEASE = "release"  # Nova funcionalidade
    EXPERIMENT = "experiment"  # Experimento/A/B test
    OPERATIONAL = "operational"  # Toggle operacional
    PERMISSION = "permission"  # Controle de permissão


class RolloutStrategy(StrEnum):
    """Estratégia de rollout."""

    ALL = "all"  # Todos
    NONE = "none"  # Nenhum
    PERCENTAGE = "percentage"  # Percentual de usuários
    TENANT_LIST = "tenant_list"  # Lista de tenants específicos
    USER_LIST = "user_list"  # Lista de usuários específicos
    ATTRIBUTE = "attribute"  # Baseado em atributo
    GRADUAL = "gradual"  # Rollout gradual por tempo


class FeatureFlag(Base):
    """Model de Feature Flag."""

    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    codigo = Column(String(100), unique=True, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Status e tipo
    status = Column(
        Enum(FlagStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=FlagStatus.INATIVO
    )
    flag_type = Column(
        Enum(FlagType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=FlagType.RELEASE
    )

    # Rollout
    rollout_strategy = Column(
        Enum(RolloutStrategy, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RolloutStrategy.NONE,
    )
    rollout_percentage = Column(Float, default=0, nullable=False)  # 0-100

    # Listas de inclusão/exclusão
    enabled_tenants = Column(JSONB, nullable=True)  # Lista de tenant IDs
    disabled_tenants = Column(JSONB, nullable=True)  # Lista de tenant IDs bloqueados
    enabled_users = Column(JSONB, nullable=True)  # Lista de user IDs
    disabled_users = Column(JSONB, nullable=True)  # Lista de user IDs bloqueados

    # Condições baseadas em atributos
    attribute_conditions = Column(JSONB, nullable=True)
    # Ex: {"plan": ["professional", "enterprise"], "country": ["BR", "US"]}

    # Rollout gradual
    gradual_start_date = Column(DateTime(timezone=True), nullable=True)
    gradual_end_date = Column(DateTime(timezone=True), nullable=True)
    gradual_start_percentage = Column(Float, default=0, nullable=True)
    gradual_end_percentage = Column(Float, default=100, nullable=True)

    # Variantes (para A/B testing)
    variants = Column(JSONB, nullable=True)
    # Ex: [{"name": "control", "weight": 50}, {"name": "variant_a", "weight": 50}]
    default_variant = Column(String(100), nullable=True)

    # Dependências
    depends_on = Column(JSONB, nullable=True)  # Lista de flags que devem estar ativas
    conflicts_with = Column(JSONB, nullable=True)  # Lista de flags que não podem estar ativas

    # Datas de controle
    scheduled_enable_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_disable_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Métricas
    evaluation_count = Column(Integer, default=0, nullable=False)
    enabled_count = Column(Integer, default=0, nullable=False)
    disabled_count = Column(Integer, default=0, nullable=False)
    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)

    # Responsável
    owner_id = Column(UUID(as_uuid=True), nullable=True)
    owner_team = Column(String(100), nullable=True)

    # Metadados
    category = Column(String(100), nullable=True)
    tags = Column(JSONB, nullable=True)
    jira_ticket = Column(String(50), nullable=True)
    documentation_url = Column(String(500), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Controle
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_feature_flags_status", "status"),
        Index("ix_feature_flags_flag_type", "flag_type"),
        Index("ix_feature_flags_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<FeatureFlag {self.codigo}: {self.status.value}>"

    # ==================== Propriedades ====================

    @property
    def is_enabled(self) -> bool:
        """Verifica se está globalmente habilitada."""
        return self.status == FlagStatus.ATIVO and self.ativo

    @property
    def is_gradual(self) -> bool:
        """Verifica se está em rollout gradual."""
        return self.status == FlagStatus.GRADUAL

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def current_rollout_percentage(self) -> float:
        """Calcula percentual atual de rollout (considerando gradual)."""
        if self.rollout_strategy != RolloutStrategy.GRADUAL:
            return self.rollout_percentage

        if not self.gradual_start_date or not self.gradual_end_date:
            return self.rollout_percentage

        now = datetime.utcnow()
        if now < self.gradual_start_date:
            return self.gradual_start_percentage or 0
        if now > self.gradual_end_date:
            return self.gradual_end_percentage or 100

        # Calcula percentual proporcional ao tempo
        total_duration = (self.gradual_end_date - self.gradual_start_date).total_seconds()
        elapsed = (now - self.gradual_start_date).total_seconds()
        progress = elapsed / total_duration

        start_pct = self.gradual_start_percentage or 0
        end_pct = self.gradual_end_percentage or 100
        return start_pct + (end_pct - start_pct) * progress

    @property
    def enabled_rate(self) -> float:
        """Taxa de habilitação (%)."""
        total = self.enabled_count + self.disabled_count
        if total == 0:
            return 0.0
        return round((self.enabled_count / total) * 100, 2)

    # ==================== Métodos de Avaliação ====================

    # pylint: disable=too-many-return-statements,too-many-branches
    def evaluate(self, tenant_id: str = None, user_id: str = None, attributes: dict = None) -> tuple:
        """
        Avalia se a flag está habilitada para o contexto.
        Retorna (is_enabled, variant)
        """
        self.evaluation_count += 1
        self.last_evaluated_at = datetime.utcnow()

        # Verificação básica
        if not self.ativo or self.is_expired:
            self._record_evaluation(False)
            return False, None

        if self.status == FlagStatus.INATIVO:
            self._record_evaluation(False)
            return False, None

        if self.status == FlagStatus.DEPRECATED:
            self._record_evaluation(False)
            return False, None

        # Verifica bloqueios explícitos
        if tenant_id and self.disabled_tenants:
            if tenant_id in self.disabled_tenants:
                self._record_evaluation(False)
                return False, None

        if user_id and self.disabled_users:
            if user_id in self.disabled_users:
                self._record_evaluation(False)
                return False, None

        # Verifica inclusões explícitas
        if self.rollout_strategy == RolloutStrategy.TENANT_LIST:
            enabled = tenant_id and self.enabled_tenants and tenant_id in self.enabled_tenants
            self._record_evaluation(enabled)
            return enabled, self._get_variant(tenant_id or user_id)

        if self.rollout_strategy == RolloutStrategy.USER_LIST:
            enabled = user_id and self.enabled_users and user_id in self.enabled_users
            self._record_evaluation(enabled)
            return enabled, self._get_variant(user_id)

        # Status ATIVO com ALL
        if self.status == FlagStatus.ATIVO:
            if self.rollout_strategy == RolloutStrategy.ALL:
                self._record_evaluation(True)
                return True, self._get_variant(tenant_id or user_id)

            if self.rollout_strategy == RolloutStrategy.NONE:
                self._record_evaluation(False)
                return False, None

        # Rollout por percentual
        if self.rollout_strategy in [RolloutStrategy.PERCENTAGE, RolloutStrategy.GRADUAL]:
            percentage = self.current_rollout_percentage
            identifier = tenant_id or user_id or str(uuid4())
            enabled = self._is_in_percentage(identifier, percentage)
            self._record_evaluation(enabled)
            return enabled, self._get_variant(identifier)

        # Rollout por atributo
        if self.rollout_strategy == RolloutStrategy.ATTRIBUTE:
            enabled = self._evaluate_attributes(attributes)
            self._record_evaluation(enabled)
            return enabled, self._get_variant(tenant_id or user_id)

        self._record_evaluation(False)
        return False, None

    def _is_in_percentage(self, identifier: str, percentage: float) -> bool:
        """Verifica se identificador está dentro do percentual."""
        hash_input = f"{self.codigo}:{identifier}".encode()
        hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16)
        bucket = hash_value % 100
        return bucket < percentage

    def _evaluate_attributes(self, attributes: dict) -> bool:
        """Avalia condições baseadas em atributos."""
        if not self.attribute_conditions or not attributes:
            return False

        for key, allowed_values in self.attribute_conditions.items():
            if key not in attributes:
                return False
            if attributes[key] not in allowed_values:
                return False
        return True

    def _get_variant(self, identifier: str) -> str | None:
        """Determina variante para o identificador."""
        if not self.variants:
            return self.default_variant

        hash_input = f"{self.codigo}:variant:{identifier}".encode()
        hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16)
        bucket = hash_value % 100

        cumulative = 0
        for variant in self.variants:
            cumulative += variant.get("weight", 0)
            if bucket < cumulative:
                return variant.get("name")

        return self.default_variant

    def _record_evaluation(self, enabled: bool) -> None:
        """Registra resultado da avaliação."""
        if enabled:
            self.enabled_count += 1
        else:
            self.disabled_count += 1

    # ==================== Métodos de Controle ====================

    def enable(self) -> None:
        """Habilita a flag para todos."""
        self.status = FlagStatus.ATIVO
        self.rollout_strategy = RolloutStrategy.ALL
        self.rollout_percentage = 100
        self.updated_at = datetime.utcnow()

    def disable(self) -> None:
        """Desabilita a flag."""
        self.status = FlagStatus.INATIVO
        self.rollout_strategy = RolloutStrategy.NONE
        self.rollout_percentage = 0
        self.updated_at = datetime.utcnow()

    def deprecate(self) -> None:
        """Marca como deprecated."""
        self.status = FlagStatus.DEPRECATED
        self.updated_at = datetime.utcnow()

    def set_percentage(self, percentage: float) -> None:
        """Define rollout por percentual."""
        self.status = FlagStatus.ATIVO
        self.rollout_strategy = RolloutStrategy.PERCENTAGE
        self.rollout_percentage = min(100, max(0, percentage))
        self.updated_at = datetime.utcnow()

    def start_gradual_rollout(self, start_percentage: float, end_percentage: float, duration_days: int) -> None:
        """Inicia rollout gradual."""
        self.status = FlagStatus.GRADUAL
        self.rollout_strategy = RolloutStrategy.GRADUAL
        self.gradual_start_date = datetime.utcnow()
        self.gradual_end_date = datetime.utcnow() + timedelta(days=duration_days)
        self.gradual_start_percentage = start_percentage
        self.gradual_end_percentage = end_percentage
        self.updated_at = datetime.utcnow()

    def enable_for_tenant(self, tenant_id: str) -> None:
        """Habilita para tenant específico."""
        if self.enabled_tenants is None:
            self.enabled_tenants = []
        if tenant_id not in self.enabled_tenants:
            self.enabled_tenants = [*self.enabled_tenants, tenant_id]
        self.rollout_strategy = RolloutStrategy.TENANT_LIST
        self.status = FlagStatus.ATIVO
        self.updated_at = datetime.utcnow()

    def disable_for_tenant(self, tenant_id: str) -> None:
        """Desabilita para tenant específico."""
        if self.disabled_tenants is None:
            self.disabled_tenants = []
        if tenant_id not in self.disabled_tenants:
            self.disabled_tenants = [*self.disabled_tenants, tenant_id]
        self.updated_at = datetime.utcnow()

    def enable_for_user(self, user_id: str) -> None:
        """Habilita para usuário específico."""
        if self.enabled_users is None:
            self.enabled_users = []
        if user_id not in self.enabled_users:
            self.enabled_users = [*self.enabled_users, user_id]
        self.rollout_strategy = RolloutStrategy.USER_LIST
        self.status = FlagStatus.ATIVO
        self.updated_at = datetime.utcnow()

    def schedule_enable(self, at: datetime) -> None:
        """Agenda habilitação."""
        self.scheduled_enable_at = at
        self.updated_at = datetime.utcnow()

    def schedule_disable(self, at: datetime) -> None:
        """Agenda desabilitação."""
        self.scheduled_disable_at = at
        self.updated_at = datetime.utcnow()

    def set_expiration(self, at: datetime) -> None:
        """Define data de expiração."""
        self.expires_at = at
        self.updated_at = datetime.utcnow()

    def add_variant(self, name: str, weight: float) -> None:
        """Adiciona variante para A/B testing."""
        if self.variants is None:
            self.variants = []
        self.variants = [*self.variants, {"name": name, "weight": weight}]
        if not self.default_variant:
            self.default_variant = name
        self.updated_at = datetime.utcnow()

    def reset_metrics(self) -> None:
        """Reseta métricas de avaliação."""
        self.evaluation_count = 0
        self.enabled_count = 0
        self.disabled_count = 0
        self.updated_at = datetime.utcnow()
