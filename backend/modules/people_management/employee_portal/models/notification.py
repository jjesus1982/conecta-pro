"""
Model para notificacoes do Portal do Funcionario.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class PortalNotificationType(enum.StrEnum):
    """Tipos de notificacao do portal."""

    DOCUMENT_PENDING = "document_pending"
    SCHEDULE_UPDATE = "schedule_update"
    PAYSLIP_AVAILABLE = "payslip_available"
    WARNING_ISSUED = "warning_issued"
    GENERAL = "general"
    SYSTEM = "system"


class PortalNotification(Base):
    """Notificacao enviada ao funcionario via portal.

    Attributes:
        id: Identificador unico.
        employee_id: FK para o funcionario.
        notification_type: Tipo da notificacao.
        title: Titulo da notificacao.
        message: Mensagem completa.
        is_read: Se foi lida.
        read_at: Data/hora da leitura.
        created_at: Data/hora de criacao.
    """

    __tablename__ = "portal_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = Column(
        # values_callable força o SQLAlchemy a usar os VALORES (lowercase:
        # 'schedule_update', ...) do StrEnum ao ler/gravar, e não os NOMES
        # uppercase. Sem isso, carregar uma linha real do banco (valor lowercase)
        # lança "'schedule_update' is not among the defined enum values" e a
        # consulta inteira de notificações falha.
        Enum(
            PortalNotificationType,
            name="portal_notification_type_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=PortalNotificationType.GENERAL,
    )
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
