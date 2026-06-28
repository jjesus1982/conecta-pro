"""Service de IA para analise de contas a receber."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.customer import Customer, CustomerStatus
from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus
from modules.financial.models.receivable_installment import (
    InstallmentStatus,
    ReceivableInstallment,
)
from modules.financial.models.receivable_payment import ReceivablePayment

logger = logging.getLogger(__name__)


@dataclass
class CustomerRiskScore:
    """Score de risco do cliente."""

    customer_id: UUID
    customer_name: str
    risk_score: float  # 0-100
    risk_level: str  # baixo, medio, alto, critico
    total_debt: Decimal
    overdue_debt: Decimal
    overdue_days_avg: float
    payment_history_score: float
    recommendations: list[str]
    # Campos expostos pelo controller
    average_delay_days: float = 0.0
    on_time_payment_rate: float = 1.0
    factors: list[str] = None  # type: ignore[assignment]


@dataclass
class CollectionPriority:
    """Prioridade de cobranca."""

    account_id: UUID
    customer_name: str
    value: Decimal
    days_overdue: int
    priority_score: float
    recommended_action: str
    contact_info: dict[str, str]
    # Campos expostos pelo controller
    customer_id: UUID | None = None
    priority_level: str = "media"
    total_due: Decimal = Decimal("0")
    risk_score: float = 0.0
    reason: str = ""


@dataclass
class CashFlowForecast:
    """Previsao de fluxo de caixa."""

    period_start: date
    period_end: date
    expected_receipts: Decimal
    probable_receipts: Decimal  # Considerando inadimplencia
    historical_collection_rate: float
    by_day: list[dict]
    # Campos expostos pelo controller
    condominio_id: UUID | None = None
    expected_income: Decimal = Decimal("0")
    probable_income: Decimal = Decimal("0")
    at_risk_income: Decimal = Decimal("0")
    monthly_breakdown: list[dict] = None  # type: ignore[assignment]
    confidence_level: str = "media"


@dataclass
class DelinquencyAnalysis:
    """Analise de inadimplencia."""

    total_customers: int
    delinquent_customers: int
    delinquency_rate: float
    total_overdue: Decimal
    aging_buckets: dict[str, dict]
    trend: str  # melhorando, estavel, piorando
    projected_losses: Decimal
    # Campos expostos pelo controller
    condominio_id: UUID | None = None
    average_days_overdue: float = 0.0
    aging_breakdown: dict[str, dict] = None  # type: ignore[assignment]
    risk_distribution: dict[str, int] = None  # type: ignore[assignment]
    recommendations: list[str] = None  # type: ignore[assignment]


class ReceivableAIService:
    """Service de IA para analise de recebiveis."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session

    async def calculate_customer_risk(  # pylint: disable=too-many-locals
        self,
        customer_id: UUID,
    ) -> CustomerRiskScore:
        """Calcula score de risco do cliente."""
        # Busca dados do cliente
        customer_result = await self.session.execute(select(Customer).where(Customer.id == customer_id))
        customer = customer_result.scalar_one_or_none()
        if not customer:
            raise ValueError("Cliente nao encontrado")

        # Busca historico de pagamentos
        payments_result = await self.session.execute(
            select(ReceivablePayment)
            .join(
                ReceivableInstallment,
                ReceivablePayment.installment_id == ReceivableInstallment.id,
            )
            .join(
                ReceivableAccount,
                ReceivableInstallment.receivable_account_id == ReceivableAccount.id,
            )
            .where(ReceivableAccount.customer_id == customer_id)
            .order_by(ReceivablePayment.payment_date.desc())
            .limit(50)
        )
        payments = list(payments_result.scalars().all())

        # Busca parcelas vencidas
        today = date.today()
        overdue_result = await self.session.execute(
            select(ReceivableInstallment)
            .join(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.customer_id == customer_id,
                    ReceivableInstallment.due_date < today,
                    ReceivableInstallment.status.notin_(
                        [InstallmentStatus.PAGA.value, InstallmentStatus.CANCELADA.value]
                    ),
                )
            )
        )
        overdue_installments = list(overdue_result.scalars().all())

        # Calcula metricas
        total_overdue_days = sum((today - inst.due_date).days for inst in overdue_installments)
        avg_overdue_days = total_overdue_days / len(overdue_installments) if overdue_installments else 0

        # Score de historico de pagamento (0-100)
        payment_score = 100.0
        if payments:
            late_payments = sum(
                1
                for p in payments
                if p.payment_date
                and hasattr(p, "installment")
                and p.installment
                and p.installment.due_date
                and p.payment_date > p.installment.due_date
            )
            payment_score = max(0, 100 - (late_payments / len(payments) * 100))

        # Calcula risk score
        risk_factors = []

        # Fator: divida vencida
        if customer.overdue_debt > 0:
            overdue_ratio = float(customer.overdue_debt / customer.total_debt) if customer.total_debt > 0 else 0
            risk_factors.append(overdue_ratio * 40)

        # Fator: dias de atraso medio
        if avg_overdue_days > 0:
            days_factor = min(avg_overdue_days / 90, 1) * 30
            risk_factors.append(days_factor)

        # Fator: historico de pagamentos
        risk_factors.append((100 - payment_score) * 0.3)

        risk_score = sum(risk_factors)
        risk_score = min(max(risk_score, 0), 100)

        # Determina nivel de risco
        if risk_score < 25:
            risk_level = "baixo"
        elif risk_score < 50:
            risk_level = "medio"
        elif risk_score < 75:
            risk_level = "alto"
        else:
            risk_level = "critico"

        # Gera recomendacoes
        recommendations = self._generate_risk_recommendations(risk_level, avg_overdue_days, customer.overdue_debt)

        # Fatores descritivos expostos na resposta
        factors: list[str] = []
        if customer.overdue_debt > 0:
            factors.append(f"Divida vencida de R$ {float(customer.overdue_debt):.2f}")
        if avg_overdue_days > 0:
            factors.append(f"Atraso medio de {round(avg_overdue_days, 1)} dias")
        if payment_score < 100:
            factors.append(f"Historico de pagamento em {round(payment_score, 1)}%")
        if not factors:
            factors.append("Sem indicadores de risco relevantes")

        return CustomerRiskScore(
            customer_id=customer_id,
            customer_name=customer.name,
            risk_score=round(risk_score, 2),
            risk_level=risk_level,
            total_debt=customer.total_debt,
            overdue_debt=customer.overdue_debt,
            overdue_days_avg=round(avg_overdue_days, 1),
            payment_history_score=round(payment_score, 2),
            recommendations=recommendations,
            average_delay_days=round(avg_overdue_days, 1),
            on_time_payment_rate=round(payment_score / 100, 4),
            factors=factors,
        )

    def _generate_risk_recommendations(
        self,
        risk_level: str,
        avg_overdue_days: float,
        overdue_debt: Decimal,
    ) -> list[str]:
        """Gera recomendacoes baseadas no risco."""
        recommendations = []

        if risk_level == "baixo":
            recommendations.append("Manter monitoramento regular")
            recommendations.append("Cliente elegivel para beneficios de pontualidade")

        elif risk_level == "medio":
            recommendations.append("Enviar lembretes de pagamento antecipados")
            recommendations.append("Considerar contato preventivo proximo ao vencimento")

        elif risk_level == "alto":
            recommendations.append("Priorizar contato de cobranca")
            recommendations.append("Oferecer renegociacao de divida")
            if avg_overdue_days > 30:
                recommendations.append("Considerar restricao de credito")

        else:  # critico
            recommendations.append("Acao de cobranca imediata necessaria")
            if overdue_debt > 1000:
                recommendations.append("Avaliar envio para protesto")
            recommendations.append("Bloquear novas operacoes")
            recommendations.append("Considerar cobranca judicial")

        return recommendations

    async def get_collection_priorities(
        self,
        condominio_id: UUID,
        limit: int = 20,
    ) -> list[CollectionPriority]:
        """Retorna lista priorizada de cobrancas."""
        today = date.today()

        # Busca contas vencidas com informacoes do cliente
        result = await self.session.execute(
            select(ReceivableAccount, Customer)
            .outerjoin(Customer, ReceivableAccount.customer_id == Customer.id)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )
            .order_by(ReceivableAccount.due_date)
        )

        priorities = []
        for account, customer in result:
            days_overdue = (today - account.due_date).days
            remaining_value = account.net_value - account.paid_value

            # Calcula score de prioridade
            priority_score = self._calculate_priority_score(remaining_value, days_overdue)

            # Determina acao recomendada
            action = self._get_recommended_action(days_overdue, remaining_value)

            # Informacoes de contato
            contact_info = {}
            if customer:
                if customer.phone:
                    contact_info["telefone"] = customer.phone
                if customer.whatsapp:
                    contact_info["whatsapp"] = customer.whatsapp
                if customer.email:
                    contact_info["email"] = customer.email

            if priority_score >= 75:
                priority_level = "critica"
            elif priority_score >= 50:
                priority_level = "alta"
            elif priority_score >= 25:
                priority_level = "media"
            else:
                priority_level = "baixa"

            priorities.append(
                CollectionPriority(
                    account_id=account.id,
                    customer_name=customer.name if customer else "N/A",
                    value=remaining_value,
                    days_overdue=days_overdue,
                    priority_score=round(priority_score, 2),
                    recommended_action=action,
                    contact_info=contact_info,
                    customer_id=account.customer_id,
                    priority_level=priority_level,
                    total_due=remaining_value,
                    risk_score=round(priority_score, 2),
                    reason=f"{days_overdue} dias em atraso, saldo de R$ {float(remaining_value):.2f}",
                )
            )

        # Ordena por score de prioridade
        priorities.sort(key=lambda x: x.priority_score, reverse=True)
        return priorities[:limit]

    def _calculate_priority_score(
        self,
        value: Decimal,
        days_overdue: int,
    ) -> float:
        """Calcula score de prioridade para cobranca."""
        # Normalizacao do valor (assume max 10000)
        value_score = min(float(value) / 10000, 1) * 50

        # Normalizacao dos dias (assume max 90 dias)
        days_score = min(days_overdue / 90, 1) * 50

        return value_score + days_score

    def _get_recommended_action(  # pylint: disable=too-many-return-statements
        self,
        days_overdue: int,
        value: Decimal,
    ) -> str:
        """Retorna acao recomendada baseada no atraso."""
        if days_overdue <= 7:
            return "Enviar lembrete por email/WhatsApp"
        elif days_overdue <= 15:
            return "Contato telefonico amigavel"
        elif days_overdue <= 30:
            return "Negociacao de pagamento"
        elif days_overdue <= 60:
            if value > 500:
                return "Notificacao extrajudicial"
            return "Intensificar cobranca"
        elif days_overdue <= 90:
            if value > 1000:
                return "Considerar protesto"
            return "Ultima tentativa de negociacao"
        else:
            if value > 2000:
                return "Protesto ou cobranca judicial"
            return "Avaliar baixa por perda"

    async def forecast_cash_flow(
        self,
        condominio_id: UUID,
        months: int = 6,
    ) -> CashFlowForecast:
        """Preve fluxo de caixa de recebiveis para os proximos N meses."""
        today = date.today()
        # Horizonte aproximado de N meses (31 dias por mes)
        end_date = today + timedelta(days=months * 31)

        # Busca parcelas a vencer no periodo
        result = await self.session.execute(
            select(ReceivableInstallment)
            .join(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableInstallment.ativo.is_(True),
                    ReceivableInstallment.due_date >= today,
                    ReceivableInstallment.due_date <= end_date,
                    ReceivableInstallment.status.in_(
                        [InstallmentStatus.PENDENTE.value, InstallmentStatus.AGENDADA.value]
                    ),
                )
            )
            .order_by(ReceivableInstallment.due_date)
        )
        installments = list(result.scalars().all())

        # Calcula taxa historica de recebimento
        collection_rate = await self._calculate_historical_collection_rate(condominio_id)
        rate_dec = Decimal(str(collection_rate))

        # Totaliza por dia (mantido para compatibilidade)
        by_day = []
        total_expected = Decimal("0")
        current_date = today
        while current_date <= end_date:
            day_total = sum(
                (inst.current_value for inst in installments if inst.due_date == current_date),
                Decimal("0"),
            )
            total_expected += day_total
            by_day.append(
                {
                    "date": current_date.isoformat(),
                    "expected": float(day_total),
                    "probable": float(day_total * rate_dec),
                }
            )
            current_date += timedelta(days=1)

        # Totaliza por mes (YYYY-MM) para o breakdown exposto no controller
        monthly_totals: dict[str, Decimal] = {}
        for inst in installments:
            key = inst.due_date.strftime("%Y-%m")
            monthly_totals[key] = monthly_totals.get(key, Decimal("0")) + (inst.current_value or Decimal("0"))

        monthly_breakdown = [
            {
                "month": key,
                "expected": float(value),
                "probable": float(value * rate_dec),
            }
            for key, value in sorted(monthly_totals.items())
        ]

        probable_total = total_expected * rate_dec

        if collection_rate >= 0.9:
            confidence_level = "alta"
        elif collection_rate >= 0.7:
            confidence_level = "media"
        else:
            confidence_level = "baixa"

        return CashFlowForecast(
            period_start=today,
            period_end=end_date,
            expected_receipts=total_expected,
            probable_receipts=probable_total,
            historical_collection_rate=round(collection_rate, 4),
            by_day=by_day,
            condominio_id=condominio_id,
            expected_income=total_expected,
            probable_income=probable_total,
            at_risk_income=total_expected - probable_total,
            monthly_breakdown=monthly_breakdown,
            confidence_level=confidence_level,
        )

    async def _calculate_historical_collection_rate(
        self,
        condominio_id: UUID,
    ) -> float:
        """Calcula taxa historica de recebimento."""
        # Ultimos 90 dias
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        # Total faturado no periodo
        billed_result = await self.session.execute(
            select(func.sum(ReceivableInstallment.original_value))
            .join(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableInstallment.due_date >= start_date,
                    ReceivableInstallment.due_date <= end_date,
                )
            )
        )
        total_billed = billed_result.scalar_one() or Decimal("0")

        # Total recebido no periodo
        received_result = await self.session.execute(
            select(func.sum(ReceivablePayment.paid_value)).where(
                and_(
                    ReceivablePayment.condominio_id == condominio_id,
                    ReceivablePayment.payment_date >= start_date,
                    ReceivablePayment.payment_date <= end_date,
                )
            )
        )
        total_received = received_result.scalar_one() or Decimal("0")

        if total_billed == 0:
            return 0.95  # Taxa padrao se nao houver historico

        rate = float(total_received / total_billed)
        return min(max(rate, 0.5), 1.0)  # Entre 50% e 100%

    async def analyze_delinquency(
        self,
        condominio_id: UUID,
    ) -> DelinquencyAnalysis:
        """Analisa inadimplencia do condominio."""
        today = date.today()

        # Total de clientes
        total_customers_result = await self.session.execute(
            select(func.count(Customer.id)).where(
                and_(
                    Customer.condominio_id == condominio_id,
                    Customer.ativo.is_(True),
                    Customer.status != CustomerStatus.INATIVO.value,
                )
            )
        )
        total_customers = total_customers_result.scalar_one() or 0

        # Clientes inadimplentes
        delinquent_result = await self.session.execute(
            select(func.count(Customer.id)).where(
                and_(
                    Customer.condominio_id == condominio_id,
                    Customer.ativo.is_(True),
                    Customer.overdue_debt > 0,
                )
            )
        )
        delinquent_customers = delinquent_result.scalar_one() or 0

        # Total vencido
        overdue_result = await self.session.execute(
            select(func.sum(ReceivableAccount.net_value - ReceivableAccount.paid_value)).where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_([ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]),
                )
            )
        )
        total_overdue = overdue_result.scalar_one() or Decimal("0")

        # Aging buckets
        aging_buckets = await self._calculate_aging_buckets(condominio_id, today)

        # Taxa de inadimplencia
        delinquency_rate = delinquent_customers / total_customers if total_customers > 0 else 0

        # Tendencia (comparando com mes anterior)
        trend = await self._calculate_trend(condominio_id)

        # Projecao de perdas (30% do vencido >90 dias)
        over_90_value = Decimal(str(aging_buckets.get(">90", {}).get("value", 0)))
        projected_losses = over_90_value * Decimal("0.3")

        # Media de dias em atraso (ponderada pelos buckets de aging)
        bucket_midpoints = {"1-7": 4, "8-15": 11, "16-30": 23, "31-60": 45, "61-90": 75, ">90": 120}
        weighted_days = sum(bucket_midpoints[k] * v.get("count", 0) for k, v in aging_buckets.items())
        total_overdue_count = sum(v.get("count", 0) for v in aging_buckets.values())
        average_days_overdue = round(weighted_days / total_overdue_count, 1) if total_overdue_count else 0.0

        # Distribuicao de risco (clientes vencidos agrupados por severidade)
        risk_distribution = {
            "baixo": aging_buckets.get("1-7", {}).get("count", 0) + aging_buckets.get("8-15", {}).get("count", 0),
            "medio": aging_buckets.get("16-30", {}).get("count", 0),
            "alto": aging_buckets.get("31-60", {}).get("count", 0),
            "critico": aging_buckets.get("61-90", {}).get("count", 0) + aging_buckets.get(">90", {}).get("count", 0),
        }

        # Recomendacoes baseadas na taxa de inadimplencia e tendencia
        recommendations: list[str] = []
        if delinquency_rate >= 0.3:
            recommendations.append("Inadimplencia elevada: priorizar acoes de cobranca ativa")
        elif delinquency_rate >= 0.1:
            recommendations.append("Inadimplencia moderada: reforcar lembretes preventivos")
        else:
            recommendations.append("Inadimplencia sob controle: manter monitoramento regular")
        if trend == "piorando":
            recommendations.append("Tendencia de piora: revisar politica de credito e cobranca")
        if risk_distribution["critico"] > 0:
            recommendations.append("Avaliar protesto/cobranca judicial para casos criticos (>60 dias)")

        return DelinquencyAnalysis(
            total_customers=total_customers,
            delinquent_customers=delinquent_customers,
            delinquency_rate=round(delinquency_rate, 4),
            total_overdue=total_overdue,
            aging_buckets=aging_buckets,
            trend=trend,
            projected_losses=projected_losses,
            condominio_id=condominio_id,
            average_days_overdue=average_days_overdue,
            aging_breakdown=aging_buckets,
            risk_distribution=risk_distribution,
            recommendations=recommendations,
        )

    async def _calculate_aging_buckets(
        self,
        condominio_id: UUID,
        reference_date: date,
    ) -> dict[str, dict]:
        """Calcula distribuicao de aging."""
        buckets = {
            "1-7": {"count": 0, "value": 0},
            "8-15": {"count": 0, "value": 0},
            "16-30": {"count": 0, "value": 0},
            "31-60": {"count": 0, "value": 0},
            "61-90": {"count": 0, "value": 0},
            ">90": {"count": 0, "value": 0},
        }

        result = await self.session.execute(
            select(ReceivableAccount).where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date < reference_date,
                    ReceivableAccount.status.notin_([ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]),
                )
            )
        )

        for account in result.scalars():
            days = (reference_date - account.due_date).days
            value = float(account.net_value - account.paid_value)

            if days <= 7:
                bucket = "1-7"
            elif days <= 15:
                bucket = "8-15"
            elif days <= 30:
                bucket = "16-30"
            elif days <= 60:
                bucket = "31-60"
            elif days <= 90:
                bucket = "61-90"
            else:
                bucket = ">90"

            buckets[bucket]["count"] += 1
            buckets[bucket]["value"] += value

        return buckets

    async def _calculate_trend(self, condominio_id: UUID) -> str:
        """Calcula tendencia de inadimplencia."""
        today = date.today()

        # Mes atual
        current_month_start = today.replace(day=1)
        current_result = await self.session.execute(
            select(func.sum(ReceivableAccount.net_value - ReceivableAccount.paid_value)).where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.due_date >= current_month_start,
                    ReceivableAccount.status.notin_([ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]),
                )
            )
        )
        current_overdue = current_result.scalar_one() or Decimal("0")

        # Mes anterior
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        prev_result = await self.session.execute(
            select(func.sum(ReceivableAccount.net_value - ReceivableAccount.paid_value)).where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date < prev_month_end,
                    ReceivableAccount.due_date >= prev_month_start,
                    ReceivableAccount.status.notin_([ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]),
                )
            )
        )
        prev_overdue = prev_result.scalar_one() or Decimal("0")

        if prev_overdue == 0:
            return "estavel"

        variation = (current_overdue - prev_overdue) / prev_overdue

        if variation < -0.1:
            return "melhorando"
        elif variation > 0.1:
            return "piorando"
        return "estavel"
