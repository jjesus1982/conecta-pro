"""Model para notificações do funcionário."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class NotificationType(StrEnum):
    """Tipo de notificação."""

    # Folha de pagamento
    PAYSLIP_AVAILABLE = "payslip_available"  # Novo contracheque
    PAYSLIP_RECTIFIED = "payslip_rectified"  # Contracheque retificado
    PAYMENT_SCHEDULED = "payment_scheduled"  # Pagamento agendado

    # Férias
    VACATION_APPROVED = "vacation_approved"  # Férias aprovadas
    VACATION_REJECTED = "vacation_rejected"  # Férias rejeitadas
    VACATION_REMINDER = "vacation_reminder"  # Lembrete de férias
    VACATION_EXPIRING = "vacation_expiring"  # Período vencendo

    # Documentos
    DOCUMENT_AVAILABLE = "document_available"  # Novo documento
    DOCUMENT_REQUIRES_SIGNATURE = "document_requires_signature"  # Assinatura requerida
    DOCUMENT_REQUIRES_ACK = "document_requires_ack"  # Ciência requerida
    DOCUMENT_EXPIRING = "document_expiring"  # Documento expirando

    # Ponto
    TIME_ENTRY_MISSING = "time_entry_missing"  # Batida faltando
    TIME_ENTRY_REJECTED = "time_entry_rejected"  # Ajuste rejeitado
    TIME_ENTRY_APPROVED = "time_entry_approved"  # Ajuste aprovado
    OVERTIME_ALERT = "overtime_alert"  # Alerta de hora extra

    # Banco de horas
    BANK_HOURS_BALANCE = "bank_hours_balance"  # Saldo de banco de horas
    BANK_HOURS_EXPIRING = "bank_hours_expiring"  # Horas expirando

    # RH
    BIRTHDAY_GREETING = "birthday_greeting"  # Aniversário
    ANNIVERSARY_GREETING = "anniversary_greeting"  # Aniversário de empresa
    TRAINING_AVAILABLE = "training_available"  # Treinamento disponível
    TRAINING_REMINDER = "training_reminder"  # Lembrete de treinamento

    # Sistema
    PASSWORD_EXPIRING = "password_expiring"  # Senha expirando  # noqa: S105
    PROFILE_INCOMPLETE = "profile_incomplete"  # Perfil incompleto
    SYSTEM_MAINTENANCE = "system_maintenance"  # Manutenção do sistema

    # Comunicados
    ANNOUNCEMENT = "announcement"  # Comunicado geral
    POLICY_UPDATE = "policy_update"  # Atualização de política

    # Genérico
    INFO = "info"  # Informativo
    WARNING = "warning"  # Aviso
    ALERT = "alert"  # Alerta
    SUCCESS = "success"  # Sucesso


class NotificationPriority(StrEnum):
    """Prioridade da notificação."""

    LOW = "low"  # Baixa
    NORMAL = "normal"  # Normal
    HIGH = "high"  # Alta
    URGENT = "urgent"  # Urgente


class NotificationChannel(StrEnum):
    """Canal de entrega da notificação."""

    PORTAL = "portal"  # Apenas no portal
    EMAIL = "email"  # E-mail
    PUSH = "push"  # Push notification (app)
    SMS = "sms"  # SMS
    WHATSAPP = "whatsapp"  # WhatsApp


class EmployeeNotification(Base):
    """Notificação para funcionário no portal."""

    __tablename__ = "employee_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Tipo e prioridade
    notification_type = Column(String(50), nullable=False, index=True)
    priority = Column(
        String(20),
        nullable=False,
        default=NotificationPriority.NORMAL.value,
    )

    # Conteúdo
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    short_message = Column(String(200), nullable=True)  # Para push/SMS

    # Ícone e estilo
    icon = Column(String(50), nullable=True)  # Nome do ícone
    color = Column(String(20), nullable=True)  # Cor do badge
    image_url = Column(String(500), nullable=True)  # Imagem opcional

    # Link de ação
    action_url = Column(String(500), nullable=True)  # URL para redirecionar
    action_label = Column(String(50), nullable=True)  # Texto do botão
    action_type = Column(String(30), nullable=True)  # Tipo: view, download, approve

    # Referência ao objeto
    reference_type = Column(String(50), nullable=True)  # payslip, document, vacation
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    # Canais de entrega
    channels = Column(JSONB, default=list)  # ["portal", "email", "push"]

    # Status de entrega por canal
    delivered_channels = Column(JSONB, default=dict)
    # {
    #   "portal": {"delivered_at": "...", "viewed_at": "..."},
    #   "email": {"sent_at": "...", "opened_at": "..."},
    #   "push": {"sent_at": "...", "clicked_at": "..."}
    # }

    # Visualização no portal
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)

    # Interação
    clicked_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)

    # E-mail
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime, nullable=True)
    email_opened = Column(Boolean, default=False)
    email_opened_at = Column(DateTime, nullable=True)
    email_clicked = Column(Boolean, default=False)
    email_clicked_at = Column(DateTime, nullable=True)

    # Push notification
    push_sent = Column(Boolean, default=False)
    push_sent_at = Column(DateTime, nullable=True)
    push_received = Column(Boolean, default=False)
    push_received_at = Column(DateTime, nullable=True)
    push_clicked = Column(Boolean, default=False)
    push_clicked_at = Column(DateTime, nullable=True)

    # SMS
    sms_sent = Column(Boolean, default=False)
    sms_sent_at = Column(DateTime, nullable=True)
    sms_delivered = Column(Boolean, default=False)
    sms_delivered_at = Column(DateTime, nullable=True)

    # Agendamento
    scheduled_at = Column(DateTime, nullable=True)  # Envio agendado
    expires_at = Column(DateTime, nullable=True)  # Expira em

    # Repetição
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50), nullable=True)  # daily, weekly, monthly
    next_occurrence = Column(DateTime, nullable=True)

    # Dados extras
    extra_data = Column(JSONB, default=dict)
    # Dados adicionais para personalização ou templates

    # Status
    is_active = Column(Boolean, default=True)
    is_archived = Column(Boolean, default=False)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_notification_employee_unread", "employee_id", "is_read"),
        Index("ix_notification_type_priority", "notification_type", "priority"),
        Index("ix_notification_scheduled", "scheduled_at"),
        Index("ix_notification_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EmployeeNotification {self.notification_type} - {self.title[:30]}>"

    @property
    def is_unread(self) -> bool:
        """Verifica se não foi lida."""
        return not self.is_read

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_pending_delivery(self) -> bool:
        """Verifica se há canais pendentes de entrega."""
        if not self.channels:
            return False
        for channel in self.channels:
            if channel == "email" and not self.email_sent:
                return True
            if channel == "push" and not self.push_sent:
                return True
            if channel == "sms" and not self.sms_sent:
                return True
        return False

    def mark_as_read(self) -> None:
        """Marca como lida."""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()

    def mark_as_clicked(self) -> None:
        """Marca como clicada."""
        self.clicked_at = datetime.utcnow()
        self.mark_as_read()

    def dismiss(self) -> None:
        """Descarta a notificação."""
        self.dismissed_at = datetime.utcnow()
        self.is_active = False

    def to_summary(self) -> dict:
        """Retorna resumo para listagem."""
        return {
            "id": str(self.id),
            "notification_type": self.notification_type,
            "priority": self.priority,
            "title": self.title,
            "short_message": self.short_message or self.message[:100],
            "icon": self.icon,
            "color": self.color,
            "action_url": self.action_url,
            "action_label": self.action_label,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }

    def to_push_payload(self) -> dict:
        """Retorna payload para push notification."""
        return {
            "notification_id": str(self.id),
            "title": self.title,
            "body": self.short_message or self.message[:150],
            "icon": self.icon,
            "click_action": self.action_url,
            "data": {
                "type": self.notification_type,
                "reference_type": self.reference_type,
                "reference_id": str(self.reference_id) if self.reference_id else None,
            },
        }
