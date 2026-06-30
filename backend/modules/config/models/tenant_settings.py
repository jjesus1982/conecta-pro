"""
TenantSettings Model - Configurações por Tenant
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=too-many-instance-attributes

import re
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class SettingCategory(StrEnum):
    """Categoria de configuração."""

    GERAL = "geral"
    SEGURANCA = "seguranca"
    NOTIFICACAO = "notificacao"
    INTEGRACAO = "integracao"
    FINANCEIRO = "financeiro"
    OPERACIONAL = "operacional"
    APARENCIA = "aparencia"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    API = "api"
    BACKUP = "backup"
    AUDITORIA = "auditoria"


class SettingType(StrEnum):
    """Tipo de valor da configuração."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"
    PASSWORD = "password"  # noqa: S105
    EMAIL = "email"
    URL = "url"
    DATE = "date"
    DATETIME = "datetime"
    COLOR = "color"
    FILE = "file"


class TenantSettings(Base):
    """Model de Configurações do Tenant."""

    __tablename__ = "tenant_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    # Identificação da configuração
    chave = Column(String(100), nullable=False)  # Ex: "email.smtp_host"
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Categoria e tipo
    category = Column(
        Enum(SettingCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SettingCategory.GERAL,
    )
    setting_type = Column(
        Enum(SettingType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SettingType.STRING
    )

    # Valor
    valor = Column(Text, nullable=True)  # Valor atual
    valor_default = Column(Text, nullable=True)  # Valor padrão
    valor_json = Column(JSONB, nullable=True)  # Para tipos complexos

    # Validação
    required = Column(Boolean, default=False, nullable=False)
    validation_regex = Column(String(500), nullable=True)
    min_value = Column(Integer, nullable=True)
    max_value = Column(Integer, nullable=True)
    allowed_values = Column(JSONB, nullable=True)  # Lista de valores permitidos

    # UI
    label = Column(String(200), nullable=True)
    placeholder = Column(String(200), nullable=True)
    help_text = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    visible = Column(Boolean, default=True, nullable=False)
    editable = Column(Boolean, default=True, nullable=False)
    group = Column(String(100), nullable=True)  # Agrupamento na UI

    # Segurança
    encrypted = Column(Boolean, default=False, nullable=False)
    sensitive = Column(Boolean, default=False, nullable=False)  # Não mostrar em logs
    requires_restart = Column(Boolean, default=False, nullable=False)

    # Histórico
    last_modified_by = Column(UUID(as_uuid=True), nullable=True)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    history = Column(JSONB, nullable=True)  # Histórico de alterações

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Controle
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow, nullable=True)

    __table_args__ = (
        Index("ix_tenant_settings_tenant_chave", "tenant_id", "chave", unique=True),
        Index("ix_tenant_settings_category", "category"),
        Index("ix_tenant_settings_group", "group"),
    )

    def __repr__(self) -> str:
        return f"<TenantSettings {self.chave}>"

    # ==================== Propriedades ====================

    @property
    def typed_value(self) -> Any:
        """Retorna valor convertido para o tipo correto."""
        if self.valor is None:
            return self.valor_default

        if self.setting_type == SettingType.INTEGER:
            return int(self.valor) if self.valor else None
        if self.setting_type == SettingType.FLOAT:
            return float(self.valor) if self.valor else None
        if self.setting_type == SettingType.BOOLEAN:
            return self.valor.lower() in ("true", "1", "yes", "sim")
        if self.setting_type in [SettingType.JSON, SettingType.LIST]:
            return self.valor_json
        return self.valor

    @property
    def display_value(self) -> str:
        """Retorna valor para exibição (mascarando sensíveis)."""
        if self.sensitive or self.encrypted:
            if self.valor:
                return "********"
            return ""
        return self.valor or ""

    @property
    def is_default(self) -> bool:
        """Verifica se está usando valor padrão."""
        return self.valor is None or self.valor == self.valor_default

    @property
    def has_value(self) -> bool:
        """Verifica se tem valor definido."""
        return self.valor is not None and self.valor != ""

    # ==================== Métodos ====================

    def set_value(self, value: Any, modified_by: UUID = None) -> None:
        """Define valor da configuração."""
        old_value = self.valor

        if self.setting_type in [SettingType.JSON, SettingType.LIST]:
            self.valor_json = value
            self.valor = None
        elif self.setting_type == SettingType.BOOLEAN:
            self.valor = "true" if value else "false"
        else:
            self.valor = str(value) if value is not None else None

        self._add_to_history(old_value, self.valor, modified_by)
        self.last_modified_by = modified_by
        self.last_modified_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def reset_to_default(self, modified_by: UUID = None) -> None:
        """Reseta para valor padrão."""
        old_value = self.valor
        self.valor = self.valor_default
        self.valor_json = None
        self._add_to_history(old_value, self.valor_default, modified_by)
        self.last_modified_by = modified_by
        self.last_modified_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def _add_to_history(self, old_value: str, new_value: str, modified_by: UUID = None) -> None:
        """Adiciona entrada ao histórico."""
        if self.history is None:
            self.history = []

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "old_value": old_value if not self.sensitive else "***",
            "new_value": new_value if not self.sensitive else "***",
            "modified_by": str(modified_by) if modified_by else None,
        }
        self.history = [*self.history[-49:], entry]  # Mantém últimas 50

    # pylint: disable=too-many-return-statements,too-many-branches
    def validate_value(self, value: Any) -> tuple:
        """Valida um valor. Retorna (is_valid, error_message)."""
        if self.required and (value is None or value == ""):
            return False, "Campo obrigatório"

        if value is None:
            return True, None

        # Validação por tipo
        if self.setting_type == SettingType.INTEGER:
            try:
                int_val = int(value)
                if self.min_value is not None and int_val < self.min_value:
                    return False, f"Valor mínimo: {self.min_value}"
                if self.max_value is not None and int_val > self.max_value:
                    return False, f"Valor máximo: {self.max_value}"
            except ValueError:
                return False, "Deve ser um número inteiro"

        if self.setting_type == SettingType.FLOAT:
            try:
                float(value)
            except ValueError:
                return False, "Deve ser um número"

        if self.setting_type == SettingType.EMAIL:
            if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", str(value)):
                return False, "Email inválido"

        if self.setting_type == SettingType.URL:
            if not re.match(r"^https?://", str(value)):
                return False, "URL inválida"

        # Validação por regex
        if self.validation_regex:
            if not re.match(self.validation_regex, str(value)):
                return False, "Formato inválido"

        # Validação por lista de valores permitidos
        if self.allowed_values and value not in self.allowed_values:
            return False, f"Valor deve ser um de: {', '.join(map(str, self.allowed_values))}"

        return True, None

    def make_visible(self) -> None:
        """Torna configuração visível na UI."""
        self.visible = True
        self.updated_at = datetime.utcnow()

    def make_hidden(self) -> None:
        """Oculta configuração da UI."""
        self.visible = False
        self.updated_at = datetime.utcnow()

    def make_editable(self) -> None:
        """Torna configuração editável."""
        self.editable = True
        self.updated_at = datetime.utcnow()

    def make_readonly(self) -> None:
        """Torna configuração somente leitura."""
        self.editable = False
        self.updated_at = datetime.utcnow()

    def mark_sensitive(self) -> None:
        """Marca como configuração sensível."""
        self.sensitive = True
        self.updated_at = datetime.utcnow()

    def unmark_sensitive(self) -> None:
        """Remove marcação de sensível."""
        self.sensitive = False
        self.updated_at = datetime.utcnow()

    @classmethod
    def create_setting(
        cls,
        tenant_id: UUID,
        chave: str,
        nome: str,
        category: SettingCategory,
        setting_type: SettingType,
        valor_default: str = None,
        **kwargs,
    ) -> "TenantSettings":
        """Factory method para criar configuração."""
        return cls(
            tenant_id=tenant_id,
            chave=chave,
            nome=nome,
            category=category,
            setting_type=setting_type,
            valor_default=valor_default,
            **kwargs,
        )
