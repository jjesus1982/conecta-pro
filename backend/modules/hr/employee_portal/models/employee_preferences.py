"""Model para preferências do funcionário no portal."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class ThemePreference(StrEnum):
    """Preferência de tema."""

    LIGHT = "light"  # Claro
    DARK = "dark"  # Escuro
    SYSTEM = "system"  # Seguir sistema
    HIGH_CONTRAST = "high_contrast"  # Alto contraste


class LanguagePreference(StrEnum):
    """Preferência de idioma."""

    PT_BR = "pt_BR"  # Português (Brasil)
    EN_US = "en_US"  # Inglês (EUA)
    ES = "es"  # Espanhol


class EmployeePreferences(Base):
    """Preferências do funcionário no portal."""

    __tablename__ = "employee_preferences"

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

    # Aparência
    theme = Column(String(20), default=ThemePreference.SYSTEM.value)
    language = Column(String(10), default=LanguagePreference.PT_BR.value)
    font_size = Column(String(10), default="medium")  # small, medium, large
    compact_mode = Column(Boolean, default=False)  # Modo compacto
    animations_enabled = Column(Boolean, default=True)

    # Notificações - Portal
    notifications_enabled = Column(Boolean, default=True)
    notification_sound = Column(Boolean, default=True)
    notification_badge = Column(Boolean, default=True)  # Badge no ícone

    # Notificações - Email
    email_notifications_enabled = Column(Boolean, default=True)
    email_payslip = Column(Boolean, default=True)  # Aviso de contracheque
    email_documents = Column(Boolean, default=True)  # Novos documentos
    email_vacation = Column(Boolean, default=True)  # Status de férias
    email_announcements = Column(Boolean, default=True)  # Comunicados
    email_birthday = Column(Boolean, default=True)  # Aniversários
    email_digest = Column(Boolean, default=False)  # Resumo diário
    email_digest_time = Column(String(5), default="08:00")  # Horário do digest

    # Notificações - Push
    push_notifications_enabled = Column(Boolean, default=True)
    push_payslip = Column(Boolean, default=True)
    push_documents = Column(Boolean, default=True)
    push_vacation = Column(Boolean, default=True)
    push_announcements = Column(Boolean, default=True)
    push_time_entry = Column(Boolean, default=True)  # Lembretes de ponto
    push_quiet_hours = Column(Boolean, default=True)  # Modo silencioso
    push_quiet_start = Column(String(5), default="22:00")
    push_quiet_end = Column(String(5), default="07:00")

    # Notificações - SMS
    sms_notifications_enabled = Column(Boolean, default=False)
    sms_urgent_only = Column(Boolean, default=True)  # Apenas urgentes

    # Notificações - WhatsApp
    whatsapp_notifications_enabled = Column(Boolean, default=False)
    whatsapp_phone = Column(String(20), nullable=True)

    # Dashboard
    dashboard_layout = Column(String(20), default="default")
    dashboard_widgets = Column(JSONB, default=list)
    # ["payslip", "vacation", "time_entry", "documents", "notifications"]
    default_page = Column(String(50), default="dashboard")

    # Contracheque
    payslip_auto_download = Column(Boolean, default=False)
    payslip_notification_day = Column(Boolean, default=True)

    # Férias
    vacation_reminder_days = Column(JSONB, default=list)  # [30, 15, 7, 1]
    vacation_balance_notification = Column(Boolean, default=True)

    # Ponto
    time_entry_reminder = Column(Boolean, default=True)
    time_entry_reminder_times = Column(JSONB, default=list)  # ["08:00", "12:00", ...]
    time_entry_geofence_reminder = Column(Boolean, default=True)

    # Privacidade
    show_birthday = Column(Boolean, default=True)  # Mostrar aniversário
    show_photo = Column(Boolean, default=True)  # Mostrar foto
    show_department = Column(Boolean, default=True)  # Mostrar departamento
    show_position = Column(Boolean, default=True)  # Mostrar cargo
    allow_colleague_contact = Column(Boolean, default=True)  # Contato de colegas

    # Segurança
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_method = Column(String(20), nullable=True)  # app, sms, email
    session_timeout_minutes = Column(Boolean, default=True)
    remember_device = Column(Boolean, default=True)

    # Acessibilidade
    screen_reader_mode = Column(Boolean, default=False)
    keyboard_navigation = Column(Boolean, default=True)
    reduce_motion = Column(Boolean, default=False)
    color_blind_mode = Column(String(20), nullable=True)  # protanopia, deuteranopia

    # Dispositivos confiáveis
    trusted_devices = Column(JSONB, default=list)
    # [{"device_id": "...", "name": "iPhone", "last_used": "..."}]

    # Últimas configurações
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    last_login_device = Column(String(200), nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "condominio_id",
            "employee_id",
            name="uq_employee_preferences",
        ),
        Index("ix_preferences_employee", "employee_id"),
    )

    def __repr__(self) -> str:
        return f"<EmployeePreferences {self.employee_id}>"

    @property
    def is_dark_theme(self) -> bool:
        """Verifica se usa tema escuro."""
        return self.theme == ThemePreference.DARK.value

    @property
    def notification_channels(self) -> list:
        """Retorna canais de notificação ativos."""
        channels = []
        if self.notifications_enabled:
            channels.append("portal")
        if self.email_notifications_enabled:
            channels.append("email")
        if self.push_notifications_enabled:
            channels.append("push")
        if self.sms_notifications_enabled:
            channels.append("sms")
        if self.whatsapp_notifications_enabled:
            channels.append("whatsapp")
        return channels

    def get_widget_order(self) -> list:
        """Retorna ordem dos widgets no dashboard."""
        if self.dashboard_widgets:
            return self.dashboard_widgets
        return [
            "payslip_summary",
            "vacation_balance",
            "time_entry_today",
            "pending_documents",
            "recent_notifications",
        ]

    def to_client_config(self) -> dict:
        """Retorna configurações para o frontend."""
        return {
            "theme": self.theme,
            "language": self.language,
            "font_size": self.font_size,
            "compact_mode": self.compact_mode,
            "animations_enabled": self.animations_enabled,
            "notifications_enabled": self.notifications_enabled,
            "notification_sound": self.notification_sound,
            "dashboard_layout": self.dashboard_layout,
            "dashboard_widgets": self.get_widget_order(),
            "default_page": self.default_page,
            "accessibility": {
                "screen_reader_mode": self.screen_reader_mode,
                "keyboard_navigation": self.keyboard_navigation,
                "reduce_motion": self.reduce_motion,
                "color_blind_mode": self.color_blind_mode,
            },
        }

    def to_notification_preferences(self) -> dict:
        """Retorna preferências de notificação."""
        return {
            "channels": self.notification_channels,
            "email": {
                "enabled": self.email_notifications_enabled,
                "payslip": self.email_payslip,
                "documents": self.email_documents,
                "vacation": self.email_vacation,
                "announcements": self.email_announcements,
                "birthday": self.email_birthday,
                "digest": self.email_digest,
                "digest_time": self.email_digest_time,
            },
            "push": {
                "enabled": self.push_notifications_enabled,
                "payslip": self.push_payslip,
                "documents": self.push_documents,
                "vacation": self.push_vacation,
                "announcements": self.push_announcements,
                "time_entry": self.push_time_entry,
                "quiet_hours": {
                    "enabled": self.push_quiet_hours,
                    "start": self.push_quiet_start,
                    "end": self.push_quiet_end,
                },
            },
            "sms": {
                "enabled": self.sms_notifications_enabled,
                "urgent_only": self.sms_urgent_only,
            },
            "whatsapp": {
                "enabled": self.whatsapp_notifications_enabled,
                "phone": self.whatsapp_phone,
            },
        }
