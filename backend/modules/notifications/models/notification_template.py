"""NotificationTemplate Model - Templates de Notificação.

Sprint 36 - Notification Hub.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class TemplateStatus(StrEnum):
    """Status do template."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class TemplateCategory(StrEnum):
    """Categoria do template."""

    TRANSACTIONAL = "transactional"
    MARKETING = "marketing"
    SYSTEM = "system"
    ALERT = "alert"
    REMINDER = "reminder"
    WELCOME = "welcome"
    CONFIRMATION = "confirmation"
    NOTIFICATION = "notification"
    REPORT = "report"
    SURVEY = "survey"


class NotificationTemplate(Base):
    """Modelo de template de notificação multi-canal."""

    __tablename__ = "notification_templates"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    name = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    category = Column(
        Enum(TemplateCategory, values_callable=lambda x: [e.value for e in x]),
        default=TemplateCategory.NOTIFICATION,
        index=True,
    )
    status = Column(
        Enum(TemplateStatus, values_callable=lambda x: [e.value for e in x]), default=TemplateStatus.DRAFT, index=True
    )

    # Canal
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), index=True)

    # Conteúdo - Email
    email_subject = Column(String(500))
    email_body_html = Column(Text)
    email_body_text = Column(Text)
    email_from_name = Column(String(100))
    email_from_address = Column(String(200))
    email_reply_to = Column(String(200))
    email_cc = Column(ARRAY(String), default=[])
    email_bcc = Column(ARRAY(String), default=[])
    email_attachments = Column(JSONB, default=[])  # [{name, url, content_type}]

    # Conteúdo - WhatsApp
    whatsapp_template_name = Column(String(200))  # Nome do template aprovado
    whatsapp_template_namespace = Column(String(200))
    whatsapp_language = Column(String(10), default="pt_BR")
    whatsapp_header = Column(JSONB)  # {type: text|image|video|document, content}
    whatsapp_body = Column(Text)
    whatsapp_footer = Column(String(60))
    whatsapp_buttons = Column(JSONB, default=[])  # [{type, text, url|phone}]
    whatsapp_variables = Column(ARRAY(String), default=[])

    # Conteúdo - SMS
    sms_body = Column(String(160))
    sms_unicode = Column(Boolean, default=False)
    sms_flash = Column(Boolean, default=False)

    # Conteúdo - Push
    push_title = Column(String(100))
    push_body = Column(String(500))
    push_image_url = Column(String(500))
    push_icon_url = Column(String(500))
    push_action_url = Column(String(500))
    push_data = Column(JSONB, default=dict)
    push_badge_count = Column(Integer)
    push_sound = Column(String(50))
    push_android_config = Column(JSONB, default=dict)
    push_ios_config = Column(JSONB, default=dict)

    # Conteúdo - Slack
    slack_text = Column(Text)
    slack_blocks = Column(JSONB, default=[])
    slack_attachments = Column(JSONB, default=[])

    # Conteúdo - In-App
    in_app_title = Column(String(200))
    in_app_body = Column(Text)
    in_app_icon = Column(String(50))
    in_app_color = Column(String(20))
    in_app_action_url = Column(String(500))
    in_app_action_label = Column(String(50))

    # Conteúdo - Webhook
    webhook_url = Column(String(500))
    webhook_method = Column(String(10), default="POST")
    webhook_headers = Column(JSONB, default=dict)
    webhook_body_template = Column(Text)

    # Variáveis
    variables = Column(JSONB, default=[])  # [{name, type, required, default, description}]
    sample_data = Column(JSONB, default=dict)  # Dados de exemplo para preview

    # Localização
    locale = Column(String(10), default="pt_BR")
    translations = Column(JSONB, default=dict)  # {locale: {field: value}}

    # A/B Testing
    is_variant = Column(Boolean, default=False)
    parent_template_id = Column(UUID(as_uuid=True), index=True)
    variant_name = Column(String(50))
    variant_weight = Column(Integer, default=50)  # Peso em %

    # Aprovação
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(UUID(as_uuid=True))
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)

    # Métricas
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)
    total_unsubscribed = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    total_complained = Column(Integer, default=0)
    open_rate = Column(Float)
    click_rate = Column(Float)
    conversion_rate = Column(Float)

    # Versionamento
    version = Column(Integer, default=1)
    previous_version_id = Column(UUID(as_uuid=True))

    # Metadados
    extra_data = Column(JSONB, default=dict)
    tags = Column(ARRAY(String), default=[])

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    # channel: removido — conflito com ConfigNotificationTemplate (extend_existing na mesma tabela).
    # Acesse channel via query: session.query(NotificationChannel).get(template.channel_id)
    queue_items = relationship(
        "NotificationQueue",
        back_populates="template",
        foreign_keys="NotificationQueue.template_id",
    )
    logs = relationship(
        "NotificationLog",
        back_populates="template",
        foreign_keys="NotificationLog.template_id",
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.name} ({self.category.value})>"
