"""
Contract Alert Model - AI Contract Analysis

Model para alertas de contratos (vencimento, renovacao, riscos).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class AlertType(StrEnum):
    """Tipo de alerta."""

    EXPIRY = "expiry"  # Vencimento
    RENEWAL = "renewal"  # Renovacao
    PAYMENT = "payment"  # Pagamento
    ADJUSTMENT = "adjustment"  # Reajuste
    RISK = "risk"  # Risco identificado
    COMPLIANCE = "compliance"  # Problema de conformidade
    DEADLINE = "deadline"  # Prazo
    NOTICE = "notice"  # Aviso previo
    REVIEW = "review"  # Revisao necessaria
    ACTION_REQUIRED = "action_required"  # Acao requerida
    MISSING_DOCUMENT = "missing_document"  # Documento faltando
    ANOMALY = "anomaly"  # Anomalia detectada


class AlertStatus(StrEnum):
    """Status do alerta."""

    PENDING = "pending"  # Pendente
    ACKNOWLEDGED = "acknowledged"  # Reconhecido
    IN_PROGRESS = "in_progress"  # Em andamento
    RESOLVED = "resolved"  # Resolvido
    DISMISSED = "dismissed"  # Dispensado
    ESCALATED = "escalated"  # Escalado


class AlertPriority(StrEnum):
    """Prioridade do alerta."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class ContractAlert(Base):
    """
    Model para alertas de contrato.

    Armazena alertas gerados pela analise de contratos.
    """

    __tablename__ = "contract_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relacionamento com analise
    analysis_id = Column(
        UUID(as_uuid=True), ForeignKey("contract_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Referencia ao contrato
    contract_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contract_number = Column(String(50))

    # Tipo e status
    alert_type = Column(Enum(AlertType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    status = Column(
        Enum(AlertStatus, values_callable=lambda x: [e.value for e in x]),
        default=AlertStatus.PENDING,
        nullable=False,
        index=True,
    )
    priority = Column(
        Enum(AlertPriority, values_callable=lambda x: [e.value for e in x]),
        default=AlertPriority.MEDIUM,
        nullable=False,
        index=True,
    )

    # Descricao
    title = Column(String(300), nullable=False)
    description = Column(Text)
    recommendation = Column(Text)  # Acao recomendada

    # Datas
    trigger_date = Column(Date, nullable=False)  # Data que dispara o alerta
    due_date = Column(Date)  # Data limite para acao
    reference_date = Column(Date)  # Data de referencia (vencimento, etc)

    # Dias de antecedencia
    days_before = Column(Integer, default=30)  # Quantos dias antes do evento
    days_remaining = Column(Integer)  # Dias restantes ate o evento

    # Referencia a clausula (se aplicavel)
    clause_id = Column(UUID(as_uuid=True))
    clause_number = Column(String(20))

    # Valores (se aplicavel)
    monetary_value = Column(String(50))
    percentage_value = Column(String(20))

    # Destinatarios
    assigned_to = Column(UUID(as_uuid=True))  # Responsavel
    notify_users = Column(JSONB, default=list)  # Lista de usuarios a notificar
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime)

    # Metadados do alerta
    source = Column(String(50), default="ai_analysis")  # Origem do alerta
    confidence = Column(Integer, default=100)  # Confianca no alerta (0-100)
    auto_generated = Column(Boolean, default=True)

    # Acoes tomadas
    actions_taken = Column(JSONB, default=list)
    # Ex: [{"action": "notified", "by": "user_id", "at": "2025-01-05"}]

    # Resolucao
    resolved_by = Column(UUID(as_uuid=True))
    resolved_at = Column(DateTime)
    resolution_notes = Column(Text)

    # Recorrencia
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50))  # daily, weekly, monthly, yearly
    next_occurrence = Column(Date)

    # Escalation
    escalated_to = Column(UUID(as_uuid=True))
    escalated_at = Column(DateTime)
    escalation_reason = Column(Text)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_read = Column(Boolean, default=False)
    is_snoozed = Column(Boolean, default=False)
    snooze_until = Column(DateTime)

    # Relacionamento
    analysis = relationship("ContractAnalysis", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<ContractAlert {self.alert_type.value}: {self.title}>"

    @property
    def is_overdue(self) -> bool:
        """Verifica se o alerta esta atrasado."""
        if not self.due_date:
            return False
        return date.today() > self.due_date

    @property
    def is_urgent(self) -> bool:
        """Verifica se e urgente."""
        return self.priority in (AlertPriority.URGENT, AlertPriority.CRITICAL)

    @property
    def requires_action(self) -> bool:
        """Verifica se requer acao."""
        return self.status in (AlertStatus.PENDING, AlertStatus.ACKNOWLEDGED) and self.is_active

    def acknowledge(self, user_id: uuid.UUID) -> None:
        """Marca alerta como reconhecido."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.is_read = True
        self.actions_taken = self.actions_taken or []
        self.actions_taken.append(
            {
                "action": "acknowledged",
                "by": str(user_id),
                "at": datetime.utcnow().isoformat(),
            }
        )

    def resolve(self, user_id: uuid.UUID, notes: str = None) -> None:
        """Resolve o alerta."""
        self.status = AlertStatus.RESOLVED
        self.resolved_by = user_id
        self.resolved_at = datetime.utcnow()
        self.resolution_notes = notes
        self.actions_taken = self.actions_taken or []
        self.actions_taken.append(
            {
                "action": "resolved",
                "by": str(user_id),
                "at": datetime.utcnow().isoformat(),
                "notes": notes,
            }
        )
