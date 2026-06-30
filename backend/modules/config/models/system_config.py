"""
SystemConfig Model - Configurações Globais do Sistema
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-many-instance-attributes

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class ConfigScope(StrEnum):
    """Escopo da configuração."""

    GLOBAL = "global"  # Aplica a todo o sistema
    DEFAULT = "default"  # Valor padrão para novos tenants
    SYSTEM = "system"  # Configuração interna do sistema
    SECURITY = "security"  # Configurações de segurança


class ConfigPriority(StrEnum):
    """Prioridade da configuração."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class SystemConfig(Base):
    """Model de Configurações Globais do Sistema."""

    __tablename__ = "system_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    chave = Column(String(100), unique=True, nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Escopo e prioridade
    scope = Column(
        Enum(ConfigScope, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ConfigScope.GLOBAL
    )
    priority = Column(
        Enum(ConfigPriority, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConfigPriority.NORMAL,
    )

    # Valor
    valor = Column(Text, nullable=True)
    valor_json = Column(JSONB, nullable=True)
    valor_type = Column(String(20), nullable=False, default="string")

    # Validação
    required = Column(Boolean, default=False, nullable=False)
    validation_schema = Column(JSONB, nullable=True)  # JSON Schema para validação
    allowed_values = Column(JSONB, nullable=True)

    # Comportamento
    cacheable = Column(Boolean, default=True, nullable=False)
    cache_ttl_seconds = Column(Integer, default=3600, nullable=False)
    requires_restart = Column(Boolean, default=False, nullable=False)
    # Indica se pode ser sobrescrito por tenant
    override_allowed = Column(Boolean, default=True, nullable=False)

    # Segurança
    encrypted = Column(Boolean, default=False, nullable=False)
    sensitive = Column(Boolean, default=False, nullable=False)
    admin_only = Column(Boolean, default=False, nullable=False)
    audit_changes = Column(Boolean, default=True, nullable=False)

    # UI
    category = Column(String(100), nullable=True)
    group = Column(String(100), nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    visible = Column(Boolean, default=True, nullable=False)
    editable = Column(Boolean, default=True, nullable=False)
    help_url = Column(String(500), nullable=True)

    # Histórico
    version = Column(Integer, default=1, nullable=False)
    last_modified_by = Column(UUID(as_uuid=True), nullable=True)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    history = Column(JSONB, nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Controle
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow, nullable=True)

    __table_args__ = (
        Index("ix_system_configs_scope", "scope"),
        Index("ix_system_configs_category", "category"),
        Index("ix_system_configs_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<SystemConfig {self.chave}>"

    # ==================== Propriedades ====================

    @property
    def typed_value(self) -> Any:
        """Retorna valor convertido para o tipo correto."""
        if self.valor_type == "json":
            return self.valor_json
        if self.valor_type == "integer":
            return int(self.valor) if self.valor else None
        if self.valor_type == "float":
            return float(self.valor) if self.valor else None
        if self.valor_type == "boolean":
            return self.valor.lower() in ("true", "1", "yes") if self.valor else False
        if self.valor_type == "list":
            return self.valor_json if self.valor_json else []
        return self.valor

    @property
    def display_value(self) -> str:
        """Retorna valor para exibição."""
        if self.sensitive or self.encrypted:
            return "********" if self.valor else ""
        if self.valor_type == "json":
            return str(self.valor_json)
        return self.valor or ""

    @property
    def is_global(self) -> bool:
        """Verifica se é configuração global."""
        return self.scope == ConfigScope.GLOBAL

    @property
    def is_security(self) -> bool:
        """Verifica se é configuração de segurança."""
        return self.scope == ConfigScope.SECURITY

    @property
    def can_override(self) -> bool:
        """Verifica se pode ser sobrescrito por tenant."""
        return self.override_allowed and self.scope != ConfigScope.SYSTEM

    # ==================== Métodos ====================

    def set_value(self, value: Any, modified_by: UUID = None) -> None:
        """Define valor da configuração."""
        old_value = self.valor or str(self.valor_json)

        if self.valor_type in ["json", "list"]:
            self.valor_json = value
            self.valor = None
        elif self.valor_type == "boolean":
            self.valor = "true" if value else "false"
        else:
            self.valor = str(value) if value is not None else None

        self.version += 1
        self._add_to_history(old_value, str(value), modified_by)
        self.last_modified_by = modified_by
        self.last_modified_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def _add_to_history(self, old_value: str, new_value: str, modified_by: UUID = None) -> None:
        """Adiciona entrada ao histórico."""
        if not self.audit_changes:
            return

        if self.history is None:
            self.history = []

        entry = {
            "version": self.version,
            "timestamp": datetime.utcnow().isoformat(),
            "old_value": old_value if not self.sensitive else "***",
            "new_value": new_value if not self.sensitive else "***",
            "modified_by": str(modified_by) if modified_by else None,
        }
        self.history = [*self.history[-99:], entry]  # Mantém últimas 100

    # pylint: disable=too-many-return-statements
    def validate_value(self, value: Any) -> tuple:
        """Valida um valor. Retorna (is_valid, error_message)."""
        if self.required and (value is None or value == ""):
            return False, "Campo obrigatório"

        if value is None:
            return True, None

        # Validação por tipo
        if self.valor_type == "integer":
            try:
                int(value)
            except ValueError:
                return False, "Deve ser um número inteiro"

        if self.valor_type == "float":
            try:
                float(value)
            except ValueError:
                return False, "Deve ser um número"

        if self.valor_type == "boolean":
            if str(value).lower() not in ("true", "false", "1", "0", "yes", "no"):
                return False, "Deve ser verdadeiro ou falso"

        # Validação por lista de valores permitidos
        if self.allowed_values and value not in self.allowed_values:
            return False, f"Valor deve ser um de: {', '.join(map(str, self.allowed_values))}"

        return True, None

    def enable_caching(self, ttl_seconds: int = 3600) -> None:
        """Habilita cache para a configuração."""
        self.cacheable = True
        self.cache_ttl_seconds = ttl_seconds
        self.updated_at = datetime.utcnow()

    def disable_caching(self) -> None:
        """Desabilita cache para a configuração."""
        self.cacheable = False
        self.updated_at = datetime.utcnow()

    def make_admin_only(self) -> None:
        """Restringe a apenas administradores."""
        self.admin_only = True
        self.updated_at = datetime.utcnow()

    def allow_all_users(self) -> None:
        """Permite acesso a todos os usuários."""
        self.admin_only = False
        self.updated_at = datetime.utcnow()

    def prevent_override(self) -> None:
        """Impede sobrescrita por tenant."""
        self.override_allowed = False
        self.updated_at = datetime.utcnow()

    def allow_override(self) -> None:
        """Permite sobrescrita por tenant."""
        self.override_allowed = True
        self.updated_at = datetime.utcnow()

    def mark_sensitive(self) -> None:
        """Marca como configuração sensível."""
        self.sensitive = True
        self.encrypted = True
        self.updated_at = datetime.utcnow()

    @classmethod
    def create_config(
        cls, chave: str, nome: str, valor_type: str = "string", scope: ConfigScope = ConfigScope.GLOBAL, **kwargs
    ) -> "SystemConfig":
        """Factory method para criar configuração."""
        return cls(chave=chave, nome=nome, valor_type=valor_type, scope=scope, **kwargs)
