"""Model para regras de cobranca automatica."""

import uuid
from sqlalchemy import Integer
from datetime import date, datetime, time
from enum import StrEnum

from dateutil.relativedelta import relativedelta
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.models import Base


class BillingType(StrEnum):
    """Tipo de cobranca."""

    TAXA_CONDOMINIAL = "taxa_condominial"  # Taxa mensal
    TAXA_EXTRA = "taxa_extra"  # Taxa extra
    RESERVA = "reserva"  # Reserva de areas
    MULTA = "multa"  # Multa
    ACORDO = "acordo"  # Acordo de pagamento
    AGUA = "agua"  # Consumo de agua
    GAS = "gas"  # Consumo de gas
    FUNDO_RESERVA = "fundo_reserva"  # Fundo de reserva
    RATEIO_EXTRA = "rateio_extra"  # Rateio extraordinario


class BillingFrequency(StrEnum):
    """Frequencia de cobranca."""

    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"
    AVULSO = "avulso"  # Cobranca unica


class NotificationType(StrEnum):
    """Tipo de notificacao."""

    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PUSH = "push"


class BillingRuleStatus(StrEnum):
    """Status da regra."""

    ATIVA = "ativa"
    INATIVA = "inativa"
    PAUSADA = "pausada"
    CANCELADA = "cancelada"


class BillingRule(Base):
    """Regra de cobranca automatica."""

    __tablename__ = "billing_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    billing_type = Column(String(30), nullable=False, default=BillingType.TAXA_CONDOMINIAL.value)
    status = Column(String(20), nullable=False, default=BillingRuleStatus.ATIVA.value)

    # Categoria de receita
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receivable_categories.id"),
        nullable=True,
    )

    # Valor
    base_value = Column(Numeric(15, 2), nullable=False)  # Valor base
    value_type = Column(String(20), default="fixo")  # fixo, percentual, por_m2
    reference_field = Column(String(50), nullable=True)  # area_privativa, fracao_ideal

    # Frequencia
    frequency = Column(String(20), nullable=False, default=BillingFrequency.MENSAL.value)
    due_day = Column(Integer, default=10)  # Dia de vencimento
    generation_day = Column(Integer, default=1)  # Dia de geracao

    # Periodo de vigencia
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    # Juros e multa
    apply_interest = Column(Boolean, default=True)
    interest_rate = Column(Numeric(8, 4), default=1)  # % ao mes
    apply_penalty = Column(Boolean, default=True)
    penalty_rate = Column(Numeric(8, 4), default=2)  # %
    grace_days = Column(Integer, default=0)  # Dias de carencia

    # Desconto por pontualidade
    apply_discount = Column(Boolean, default=False)
    discount_rate = Column(Numeric(8, 4), default=0)  # %
    discount_days = Column(Integer, default=0)  # Dias antes do vencimento

    # Geracao de boleto
    auto_generate_boleto = Column(Boolean, default=True)
    boleto_days_before = Column(Integer, default=5)  # Dias antes do vencimento
    boleto_expiration_days = Column(Integer, default=30)  # Validade apos vencimento

    # Geracao de PIX
    auto_generate_pix = Column(Boolean, default=True)
    pix_expiration_hours = Column(Integer, default=24)  # Horas de validade

    # Notificacoes
    notifications_enabled = Column(Boolean, default=True)
    notification_channels = Column(ARRAY(String), default=["email", "push"])
    # Dias antes do vencimento para notificar
    notify_before_days = Column(ARRAY(Integer), default=[7, 3, 1])
    # Dias apos vencimento para notificar
    notify_after_days = Column(JSONB, default=[1, 3, 7, 15, 30])

    # Horario de envio de notificacoes
    notification_time = Column(Time, default=time(9, 0))

    # Templates de notificacao
    notification_templates = Column(JSONB, default=dict)
    # {"email_before": "template_id", "email_after": "template_id", ...}

    # Filtros de aplicacao (quais unidades)
    apply_to_all = Column(Boolean, default=True)
    unit_filter = Column(JSONB, default=dict)
    # {"blocos": ["A", "B"], "tipos": ["apartamento"], "exclude_units": []}

    # Ultima execucao
    last_run_at = Column(DateTime, nullable=True)
    last_run_result = Column(JSONB, default=dict)
    # {"success": 100, "errors": 2, "total": 102, "details": []}
    next_run_at = Column(DateTime, nullable=True)

    # Estatisticas
    total_generated = Column(Integer, default=0)  # Total de cobrancas geradas
    total_collected = Column(Numeric(15, 2), default=0)  # Total arrecadado
    collection_rate = Column(Numeric(8, 4), default=0)  # Taxa de arrecadacao %

    # Observacoes
    notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_billing_rules_type", "billing_type"),
        Index("ix_billing_rules_status", "status"),
        Index("ix_billing_rules_condominio", "condominio_id"),
        Index(
            "ix_billing_rules_condominio_status",
            "condominio_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<BillingRule {self.name}>"

    @property
    def is_active(self) -> bool:
        """Verifica se esta ativa."""
        if self.status != BillingRuleStatus.ATIVA.value:
            return False
        today = date.today()
        if self.end_date and today > self.end_date:
            return False
        if today < self.start_date:
            return False
        return True

    @property
    def should_run_today(self) -> bool:
        """Verifica se deve rodar hoje."""
        if not self.is_active:
            return False
        return date.today().day == self.generation_day

    def calculate_due_date(self, reference_date: date | None = None) -> date:
        """Calcula data de vencimento."""
        if reference_date is None:
            reference_date = date.today()

        # Proximo mes
        if reference_date.month == 12:
            due_month = 1
            due_year = reference_date.year + 1
        else:
            due_month = reference_date.month + 1
            due_year = reference_date.year

        # Ajusta dia de vencimento
        day = min(self.due_day, 28)  # Evita problemas com meses curtos

        return date(due_year, due_month, day)

    def calculate_value(self, unit_data: dict | None = None) -> float:
        """Calcula valor da cobranca."""
        if self.value_type == "fixo":
            return float(self.base_value)

        if self.value_type == "percentual" and unit_data:
            reference = unit_data.get(self.reference_field, 0)
            return float(self.base_value) * reference / 100

        if self.value_type == "por_m2" and unit_data:
            area = unit_data.get("area_privativa", 0)
            return float(self.base_value) * area

        return float(self.base_value)

    def pause(self, reason: str | None = None) -> None:
        """Pausa a regra."""
        self.status = BillingRuleStatus.PAUSADA.value

    def resume(self) -> None:
        """Retoma a regra."""
        self.status = BillingRuleStatus.ATIVA.value

    def activate(self) -> None:
        """Ativa a regra (retoma execucao)."""
        self.status = BillingRuleStatus.ATIVA.value
        self.ativo = True

    def deactivate(self) -> None:
        """Desativa a regra."""
        self.status = BillingRuleStatus.INATIVA.value
        self.ativo = False

    def register_run(
        self,
        success_count: int,
        error_count: int,
        details: list | None = None,
    ) -> None:
        """Registra execucao da regra."""
        self.last_run_at = datetime.utcnow()
        self.last_run_result = {
            "success": success_count,
            "errors": error_count,
            "total": success_count + error_count,
            "details": details or [],
        }
        self.total_generated += success_count
        self._calculate_next_run()

    def _calculate_next_run(self) -> None:
        """Calcula proxima execucao."""
        today = date.today()
        if self.generation_day > today.day:
            next_date = today.replace(day=self.generation_day)
        else:
            next_month = today + relativedelta(months=1)
            next_date = next_month.replace(day=self.generation_day)

        self.next_run_at = datetime.combine(
            next_date,
            self.notification_time or time(9, 0),
        )

    def to_dict(self) -> dict:
        """Converte para dicionario."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "billing_type": self.billing_type,
            "status": self.status,
            "base_value": float(self.base_value),
            "value_type": self.value_type,
            "frequency": self.frequency,
            "due_day": self.due_day,
            "generation_day": self.generation_day,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "interest_rate": float(self.interest_rate),
            "penalty_rate": float(self.penalty_rate),
            "grace_days": self.grace_days,
            "auto_generate_boleto": self.auto_generate_boleto,
            "auto_generate_pix": self.auto_generate_pix,
            "notifications_enabled": self.notifications_enabled,
            "is_active": self.is_active,
            "total_generated": self.total_generated,
            "total_collected": float(self.total_collected),
            "collection_rate": float(self.collection_rate),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
        }
