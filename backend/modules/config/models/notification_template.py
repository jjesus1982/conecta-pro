"""
NotificationTemplate Model - Templates de Notificação
Sprint 35: Configurações e Multi-tenant
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class ConfigNotificationChannel(StrEnum):
    """Canal de notificação (usado nos templates de configuração).

    Renomeado de NotificationChannel para evitar colisão de nome com o modelo
    SQLAlchemy NotificationChannel (modules.notifications.models.notification_channel),
    que mapeia a tabela 'notification_channels'.  Exportado como 'NotificationChannel'
    via modules/config/models/__init__.py para compatibilidade retroativa.
    """

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    TELEGRAM = "telegram"


class NotificationType(StrEnum):
    """Tipo de notificação."""

    TRANSACIONAL = "transacional"  # Confirmações, recibos
    ALERTA = "alerta"  # Alertas de sistema
    MARKETING = "marketing"  # Campanhas
    OPERACIONAL = "operacional"  # Atualizações operacionais
    SEGURANCA = "seguranca"  # Alertas de segurança
    LEMBRETE = "lembrete"  # Lembretes
    SISTEMA = "sistema"  # Notificações do sistema


class TemplateStatus(StrEnum):
    """Status do template."""

    RASCUNHO = "rascunho"
    ATIVO = "ativo"
    INATIVO = "inativo"
    ARQUIVADO = "arquivado"


class ConfigNotificationTemplate(Base):
    """Model de Template de Notificação (config module).

    Classe renomeada para evitar conflito de registry SQLAlchemy com
    modules.notifications.models.NotificationTemplate (mesma tabela).
    Exportada como 'NotificationTemplate' via models/__init__.py.
    """

    __tablename__ = "notification_templates"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # None = global
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), nullable=True, index=True)

    # Identificação
    codigo = Column(String(100), nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # NOTA: coluna 'channel' removida deste model para evitar conflito de mapper
    # com o relationship 'channel' do notifications module (mesma tabela, extend_existing=True).
    # O canal é acessado via channel_id / relationship do notifications module.
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=NotificationType.TRANSACIONAL,
    )
    status = Column(
        Enum(TemplateStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TemplateStatus.RASCUNHO,
    )

    # Conteúdo - Email
    email_subject = Column(String(500), nullable=True)
    email_body_html = Column(Text, nullable=True)
    email_body_text = Column(Text, nullable=True)
    email_from_name = Column(String(200), nullable=True)
    email_from_address = Column(String(255), nullable=True)
    email_reply_to = Column(String(255), nullable=True)

    # Conteúdo - SMS/WhatsApp
    sms_body = Column(Text, nullable=True)
    whatsapp_template_id = Column(String(100), nullable=True)
    whatsapp_components = Column(JSONB, nullable=True)

    # Conteúdo - Push
    push_title = Column(String(200), nullable=True)
    push_body = Column(Text, nullable=True)
    push_icon = Column(String(500), nullable=True)
    push_image = Column(String(500), nullable=True)
    push_action_url = Column(String(500), nullable=True)
    push_data = Column(JSONB, nullable=True)

    # Conteúdo - In-App
    in_app_title = Column(String(200), nullable=True)
    in_app_body = Column(Text, nullable=True)
    in_app_icon = Column(String(100), nullable=True)
    in_app_action = Column(JSONB, nullable=True)

    # Conteúdo - Slack/Webhook
    slack_channel = Column(String(100), nullable=True)
    webhook_url = Column(String(500), nullable=True)
    webhook_payload = Column(JSONB, nullable=True)

    # Variáveis disponíveis
    available_variables = Column(JSONB, nullable=True)
    # Ex: [{"name": "nome", "description": "Nome do usuário", "required": true}]

    # Personalização
    language = Column(String(10), default="pt-BR", nullable=False)
    locale = Column(String(10), nullable=True)
    timezone = Column(String(50), nullable=True)

    # Design
    layout_template = Column(String(100), nullable=True)  # Template base do layout
    css_custom = Column(Text, nullable=True)
    header_image = Column(String(500), nullable=True)
    footer_text = Column(Text, nullable=True)

    # Anexos
    attachments = Column(JSONB, nullable=True)
    # Ex: [{"name": "contrato.pdf", "path": "/templates/contrato.pdf"}]

    # Configurações de envio
    priority = Column(Integer, default=3, nullable=False)  # 1=alta, 5=baixa
    send_delay_minutes = Column(Integer, default=0, nullable=False)
    batch_size = Column(Integer, default=100, nullable=False)
    rate_limit_per_hour = Column(Integer, nullable=True)

    # Regras de envio
    send_conditions = Column(JSONB, nullable=True)  # Condições para envio
    exclude_conditions = Column(JSONB, nullable=True)  # Condições para exclusão
    quiet_hours_start = Column(String(5), nullable=True)  # "22:00"
    quiet_hours_end = Column(String(5), nullable=True)  # "08:00"
    allowed_days = Column(JSONB, nullable=True)  # [0, 1, 2, 3, 4] = seg-sex

    # Tracking
    track_opens = Column(Boolean, default=True, nullable=False)
    track_clicks = Column(Boolean, default=True, nullable=False)
    track_delivery = Column(Boolean, default=True, nullable=False)

    # Métricas
    sent_count = Column(Integer, default=0, nullable=False)
    delivered_count = Column(Integer, default=0, nullable=False)
    opened_count = Column(Integer, default=0, nullable=False)
    clicked_count = Column(Integer, default=0, nullable=False)
    bounced_count = Column(Integer, default=0, nullable=False)
    unsubscribed_count = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Versionamento
    version = Column(Integer, default=1, nullable=False)
    parent_template_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadados
    category = Column(String(100), nullable=True)
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Controle
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_notification_templates_tenant_codigo", "tenant_id", "codigo"),
        Index("ix_notification_templates_notification_type", "notification_type"),
        Index("ix_notification_templates_status", "status"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.codigo}>"

    # ==================== Propriedades ====================

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == TemplateStatus.ATIVO and self.ativo

    @property
    def is_global(self) -> bool:
        """Verifica se é template global."""
        return self.tenant_id is None

    @property
    def open_rate(self) -> float:
        """Taxa de abertura (%)."""
        if self.delivered_count == 0:
            return 0.0
        return round((self.opened_count / self.delivered_count) * 100, 2)

    @property
    def click_rate(self) -> float:
        """Taxa de cliques (%)."""
        if self.opened_count == 0:
            return 0.0
        return round((self.clicked_count / self.opened_count) * 100, 2)

    @property
    def delivery_rate(self) -> float:
        """Taxa de entrega (%)."""
        if self.sent_count == 0:
            return 0.0
        return round((self.delivered_count / self.sent_count) * 100, 2)

    @property
    def bounce_rate(self) -> float:
        """Taxa de bounce (%)."""
        if self.sent_count == 0:
            return 0.0
        return round((self.bounced_count / self.sent_count) * 100, 2)

    # ==================== Métodos ====================

    def activate(self) -> None:
        """Ativa o template."""
        self.status = TemplateStatus.ATIVO
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o template."""
        self.status = TemplateStatus.INATIVO
        self.updated_at = datetime.utcnow()

    def archive(self) -> None:
        """Arquiva o template."""
        self.status = TemplateStatus.ARQUIVADO
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def increment_version(self) -> None:
        """Incrementa versão do template."""
        self.version += 1
        self.updated_at = datetime.utcnow()

    def record_send(self) -> None:
        """Registra envio."""
        self.sent_count += 1
        self.last_sent_at = datetime.utcnow()

    def record_delivery(self) -> None:
        """Registra entrega."""
        self.delivered_count += 1

    def record_open(self) -> None:
        """Registra abertura."""
        self.opened_count += 1

    def record_click(self) -> None:
        """Registra clique."""
        self.clicked_count += 1

    def record_bounce(self) -> None:
        """Registra bounce."""
        self.bounced_count += 1

    def record_unsubscribe(self) -> None:
        """Registra unsubscribe."""
        self.unsubscribed_count += 1

    def render(self, variables: dict) -> dict:
        """Renderiza template com variáveis (detecta canal pelo conteúdo)."""
        result = {}

        if self.email_subject or self.email_body_html:
            result = {
                "subject": self._replace_variables(self.email_subject, variables),
                "body_html": self._replace_variables(self.email_body_html, variables),
                "body_text": self._replace_variables(self.email_body_text, variables),
                "from_name": self.email_from_name,
                "from_address": self.email_from_address,
                "reply_to": self.email_reply_to,
            }
        elif self.sms_body:
            result = {"body": self._replace_variables(self.sms_body, variables)}
        elif self.push_title or self.push_body:
            result = {
                "title": self._replace_variables(self.push_title, variables),
                "body": self._replace_variables(self.push_body, variables),
                "icon": self.push_icon,
                "image": self.push_image,
                "action_url": self._replace_variables(self.push_action_url, variables),
                "data": self.push_data,
            }
        elif self.in_app_title or self.in_app_body:
            result = {
                "title": self._replace_variables(self.in_app_title, variables),
                "body": self._replace_variables(self.in_app_body, variables),
                "icon": self.in_app_icon,
                "action": self.in_app_action,
            }

        return result

    def _replace_variables(self, text: str, variables: dict) -> str:
        """Substitui variáveis no texto."""
        if not text:
            return text

        result = text
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else "")

        return result

    def validate_variables(self, variables: dict) -> tuple:
        """Valida variáveis. Retorna (is_valid, missing_variables)."""
        if not self.available_variables:
            return True, []

        missing = []
        for var in self.available_variables:
            if var.get("required") and var.get("name") not in variables:
                missing.append(var.get("name"))

        return len(missing) == 0, missing

    def set_quiet_hours(self, start: str, end: str) -> None:
        """Define horário de silêncio."""
        self.quiet_hours_start = start
        self.quiet_hours_end = end
        self.updated_at = datetime.utcnow()

    def set_allowed_days(self, days: list[int]) -> None:
        """Define dias permitidos (0=domingo, 6=sábado)."""
        self.allowed_days = days
        self.updated_at = datetime.utcnow()

    def add_variable(self, name: str, description: str, required: bool = False, default_value: str = None) -> None:
        """Adiciona variável disponível."""
        if self.available_variables is None:
            self.available_variables = []

        variable = {"name": name, "description": description, "required": required, "default_value": default_value}
        self.available_variables = [*self.available_variables, variable]
        self.updated_at = datetime.utcnow()

    def clone(self, new_codigo: str = None) -> "ConfigNotificationTemplate":
        """Clona o template."""
        clone = ConfigNotificationTemplate(
            tenant_id=self.tenant_id,
            codigo=new_codigo or f"{self.codigo}_copy",
            nome=f"{self.nome} (Cópia)",
            descricao=self.descricao,
            channel_id=self.channel_id,
            notification_type=self.notification_type,
            status=TemplateStatus.RASCUNHO,
            email_subject=self.email_subject,
            email_body_html=self.email_body_html,
            email_body_text=self.email_body_text,
            sms_body=self.sms_body,
            push_title=self.push_title,
            push_body=self.push_body,
            in_app_title=self.in_app_title,
            in_app_body=self.in_app_body,
            available_variables=self.available_variables,
            language=self.language,
            parent_template_id=self.id,
        )
        return clone

    def reset_metrics(self) -> None:
        """Reseta métricas do template."""
        self.sent_count = 0
        self.delivered_count = 0
        self.opened_count = 0
        self.clicked_count = 0
        self.bounced_count = 0
        self.unsubscribed_count = 0
        self.last_sent_at = None
        self.updated_at = datetime.utcnow()
