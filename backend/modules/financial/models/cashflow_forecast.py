"""Model para previsoes de fluxo de caixa.

ALINHADO AO SCHEMA REAL da tabela ``cashflow_forecasts`` (2026-06).
Apenas as colunas que EXISTEM no banco sao mapeadas como ``Column``. Os campos
que o schema de resposta (``CashFlowForecastResponse``) ainda exige, mas que NAO
existem no banco, sao expostos como atributos de compatibilidade derivados das
colunas reais (preenchidos no ``@orm.reconstructor`` apos o load).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    orm,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm.attributes import set_committed_value

from core.models import Base


class ForecastPeriodType(StrEnum):
    """Tipo de periodo da previsao (labels reais do enum forecastperiodtype)."""

    DIARIO = "diario"
    SEMANAL = "semanal"
    QUINZENAL = "quinzenal"
    MENSAL = "mensal"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class ForecastStatus(StrEnum):
    """Status da previsao (labels reais do enum forecaststatus)."""

    RASCUNHO = "rascunho"
    ATIVA = "ativo"
    REVISADA = "revisado"
    CONCLUIDA = "encerrado"
    ARQUIVADA = "arquivado"


class ForecastConfidence(StrEnum):
    """Nivel de confianca da previsao (labels reais do enum forecastconfidence)."""

    MUITO_BAIXA = "muito_baixa"
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    MUITO_ALTA = "muito_alta"


_CONFIDENCE_LEVEL = {
    ForecastConfidence.MUITO_BAIXA.value: 20,
    ForecastConfidence.BAIXA.value: 50,
    ForecastConfidence.MEDIA.value: 65,
    ForecastConfidence.ALTA.value: 80,
    ForecastConfidence.MUITO_ALTA.value: 95,
}


class CashFlowForecast(Base):
    """Previsao de fluxo de caixa (mapeada 1:1 com o schema real)."""

    __tablename__ = "cashflow_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    name = Column(String(100), nullable=False)

    # Periodo (status/period_type/confidence sao enums nativos no banco; mapeados
    # como String e comparados via cast(...) no repository para evitar
    # "operator does not exist: <enum> = character varying")
    period_type = Column(String(20), nullable=False, default=ForecastPeriodType.MENSAL.value)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    status = Column(String(20), nullable=False, default=ForecastStatus.RASCUNHO.value)
    confidence = Column(String(20), nullable=True)

    # Valores previstos / realizados / variacoes (colunas reais)
    expected_inflows = Column(Numeric(15, 2), default=Decimal("0"))
    expected_outflows = Column(Numeric(15, 2), default=Decimal("0"))
    expected_balance = Column(Numeric(15, 2), default=Decimal("0"))

    actual_inflows = Column(Numeric(15, 2), nullable=True)
    actual_outflows = Column(Numeric(15, 2), nullable=True)
    actual_balance = Column(Numeric(15, 2), nullable=True)

    variance_inflows = Column(Numeric(15, 2), nullable=True)
    variance_outflows = Column(Numeric(15, 2), nullable=True)
    variance_balance = Column(Numeric(15, 2), nullable=True)
    variance_percentage = Column(Numeric(8, 2), nullable=True)

    pessimistic_balance = Column(Numeric(15, 2), nullable=True)
    optimistic_balance = Column(Numeric(15, 2), nullable=True)

    # IA
    is_ai_generated = Column(Boolean, default=False)
    ai_model_version = Column(String(50), nullable=True)
    ai_accuracy_score = Column(Numeric(8, 2), nullable=True)

    # JSONB
    risks = Column(JSONB, default=list)
    opportunities = Column(JSONB, default=list)
    alerts = Column(JSONB, default=list)
    assumptions = Column(JSONB, default=list)

    # Observacoes
    notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_cashflow_forecasts_condominio", "condominio_id"),
        Index("ix_cashflow_forecasts_period", "period_start", "period_end"),
        Index("ix_cashflow_forecasts_status", "status"),
    )

    # ── Atributos de compatibilidade (NAO mapeados) ───────────────────────────
    # Valores default a nivel de classe; sobrescritos por instancia no
    # reconstructor (load) ou via kwargs do construtor (ex.: CashFlowAIService).
    description: str | None = None
    reference: str | None = None
    forecast_date: date | None = None
    expected_opening_balance: Decimal = Decimal("0")
    expected_closing_balance: Decimal = Decimal("0")
    expected_net_flow: Decimal = Decimal("0")
    expected_receivables: Decimal = Decimal("0")
    expected_other_income: Decimal = Decimal("0")
    expected_payables: Decimal = Decimal("0")
    expected_other_expenses: Decimal = Decimal("0")
    actual_closing_balance: Decimal | None = None
    balance_variance: Decimal | None = None
    confidence_level: int = 50
    confidence_category: str = ForecastConfidence.MEDIA.value
    ai_generated: bool = False
    has_negative_balance_alert: bool = False
    target_balance: Decimal | None = None
    inflows_breakdown: dict | None = None
    outflows_breakdown: dict | None = None
    scenarios: dict | None = None
    ai_factors: dict | None = None

    @orm.reconstructor
    def _init_compat_on_load(self) -> None:
        """Deriva atributos de compatibilidade a partir das colunas reais."""
        self.description = self.notes
        self.reference = None
        self.forecast_date = self.period_start
        self.expected_opening_balance = Decimal("0")
        self.expected_closing_balance = self.expected_balance or Decimal("0")
        self.expected_net_flow = (self.expected_inflows or Decimal("0")) - (self.expected_outflows or Decimal("0"))
        self.actual_closing_balance = self.actual_balance
        self.balance_variance = self.variance_balance
        self.confidence_level = _CONFIDENCE_LEVEL.get(self.confidence, 50)
        self.confidence_category = self.confidence or ForecastConfidence.MEDIA.value
        self.ai_generated = bool(self.is_ai_generated)
        self.has_negative_balance_alert = bool(self.expected_balance is not None and self.expected_balance < 0)
        # Coalesce de JSONB nullable -> lista (response exige list[dict]).
        # set_committed_value evita marcar a coluna como "dirty" num simples GET.
        if self.risks is None:
            set_committed_value(self, "risks", [])
        if self.opportunities is None:
            set_committed_value(self, "opportunities", [])
        if self.alerts is None:
            set_committed_value(self, "alerts", [])

    def __repr__(self) -> str:
        return f"<CashFlowForecast {self.name} - {self.period_start}>"

    @property
    def is_active(self) -> bool:
        """Verifica se esta ativa."""
        return self.status == ForecastStatus.ATIVA.value

    # ── Calculos / mutadores ───────────────────────────────────────────────────
    def update_actuals(
        self,
        inflows: Decimal | None = None,
        outflows: Decimal | None = None,
        balance: Decimal | None = None,
    ) -> None:
        """Atualiza valores realizados e recalcula variacoes (colunas reais)."""
        if inflows is not None:
            self.actual_inflows = inflows
        if outflows is not None:
            self.actual_outflows = outflows
        if balance is not None:
            self.actual_balance = balance

        if self.actual_inflows is not None:
            self.variance_inflows = self.actual_inflows - (self.expected_inflows or Decimal("0"))
        if self.actual_outflows is not None:
            self.variance_outflows = self.actual_outflows - (self.expected_outflows or Decimal("0"))
        if self.actual_balance is not None:
            self.variance_balance = self.actual_balance - (self.expected_balance or Decimal("0"))
            if self.expected_balance and self.expected_balance != 0:
                self.variance_percentage = Decimal(
                    str(float(self.variance_balance / self.expected_balance * 100))
                )
            else:
                self.variance_percentage = Decimal("0")

        # Mantem atributos de compatibilidade coerentes
        self.actual_closing_balance = self.actual_balance
        self.balance_variance = self.variance_balance

    def calculate_expected_values(self) -> None:
        """Calcula valores esperados a partir dos atributos de compatibilidade."""
        self.expected_inflows = (self.expected_receivables or Decimal("0")) + (
            self.expected_other_income or Decimal("0")
        )
        self.expected_outflows = (self.expected_payables or Decimal("0")) + (
            self.expected_other_expenses or Decimal("0")
        )
        self.expected_net_flow = self.expected_inflows - self.expected_outflows
        self.expected_closing_balance = (self.expected_opening_balance or Decimal("0")) + self.expected_net_flow
        self.expected_balance = self.expected_closing_balance

    def update_confidence(self, level: int) -> None:
        """Atualiza nivel/categoria de confianca."""
        level = max(0, min(100, int(level)))
        self.confidence_level = level
        if level < 40:
            category = ForecastConfidence.MUITO_BAIXA.value
        elif level < 60:
            category = ForecastConfidence.BAIXA.value
        elif level < 75:
            category = ForecastConfidence.MEDIA.value
        elif level < 90:
            category = ForecastConfidence.ALTA.value
        else:
            category = ForecastConfidence.MUITO_ALTA.value
        self.confidence_category = category
        self.confidence = category

    def mark_as_ai_generated(self, model_version: str) -> None:
        """Marca como gerada por IA."""
        self.is_ai_generated = True
        self.ai_generated = True
        self.ai_model_version = model_version

    def add_risk(
        self,
        risk_type: str,
        probability: float,
        impact: Decimal,
        mitigation: str,
    ) -> None:
        """Adiciona risco identificado."""
        data = list(self.risks or [])
        data.append(
            {
                "id": str(uuid.uuid4()),
                "type": risk_type,
                "probability": probability,
                "impact": float(impact),
                "mitigation": mitigation,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        self.risks = data

    def add_opportunity(
        self,
        opportunity_type: str,
        probability: float,
        value: Decimal,
        action: str,
    ) -> None:
        """Adiciona oportunidade identificada."""
        data = list(self.opportunities or [])
        data.append(
            {
                "id": str(uuid.uuid4()),
                "type": opportunity_type,
                "probability": probability,
                "value": float(value),
                "action": action,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        self.opportunities = data

    def add_alert(
        self,
        alert_type: str,
        alert_date: date,
        amount: Decimal,
        severity: str,
        message: str,
    ) -> None:
        """Adiciona alerta."""
        data = list(self.alerts or [])
        data.append(
            {
                "id": str(uuid.uuid4()),
                "type": alert_type,
                "date": alert_date.isoformat(),
                "amount": float(amount),
                "severity": severity,
                "message": message,
            }
        )
        self.alerts = data
        if alert_type == "saldo_negativo":
            self.has_negative_balance_alert = True
