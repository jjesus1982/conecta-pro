"""
Serviço de lógica de negócios para Contratos.

Gerencia:
- Renovação automática
- Reajustes por índice econômico
- Alertas de vencimento
- Cálculo de SLA e penalidades
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel

from modules.crm.models.contract import (
    AdjustmentIndex,
    Contract,
    ContractStatus,
    ContractType,
)


class RenewalResult(BaseModel):
    """Resultado de renovação de contrato."""

    success: bool
    new_end_date: date | None = None
    new_value: Decimal | None = None
    adjustment_applied: bool = False
    adjustment_percent: Decimal | None = None
    message: str = ""


class AdjustmentResult(BaseModel):
    """Resultado de reajuste de contrato."""

    success: bool
    previous_value: Decimal
    new_value: Decimal
    adjustment_percent: Decimal
    index_used: AdjustmentIndex | None = None
    effective_date: date
    message: str = ""


class SLACalculation(BaseModel):
    """Cálculo de SLA mensal."""

    overall_score: Decimal
    indicators: list[dict[str, Any]]
    penalty_applicable: bool
    penalty_percent: Decimal
    penalty_amount: Decimal
    target_met: bool


class ContractAlert(BaseModel):
    """Alerta de contrato."""

    contract_id: str
    contract_number: str
    alert_type: str  # expiring, needs_adjustment, sla_warning
    severity: str  # low, medium, high, critical
    message: str
    days_until_event: int | None = None


class ContractService:
    """Serviço para operações de contrato."""

    # 08/09/2026: os índices eram constantes de 2024 (IGPM 4,50 / IPCA 4,23 / INPC 4,18) aplicadas a
    # 14 contratos com reajuste habilitado. O acumulado 12m não é consultado automaticamente: quem
    # reajusta informa o percentual (custom_percent). Sem ele, o cálculo recusa em vez de inventar.
    ECONOMIC_INDICES: dict = {}

    def calculate_renewal(
        self,
        contract: Contract,
        custom_adjustment_percent: Decimal | None = None,
        new_end_date: date | None = None,
    ) -> RenewalResult:
        """
        Calcula renovação do contrato.

        Args:
            contract: Contrato a renovar
            custom_adjustment_percent: Percentual de reajuste personalizado
            new_end_date: Nova data de término (se não informado, usa período padrão)

        Returns:
            RenewalResult com detalhes da renovação
        """
        if not contract.is_renewable:
            return RenewalResult(
                success=False,
                message="Contrato não é elegível para renovação automática",
            )

        if contract.status != ContractStatus.ACTIVE:
            return RenewalResult(
                success=False,
                message="Apenas contratos ativos podem ser renovados",
            )

        # Calcular nova data de término
        if new_end_date:
            calculated_end_date = new_end_date
        else:
            current_end = contract.end_date or date.today()
            months = contract.renewal_period_months
            calculated_end_date = self._add_months(current_end, months)

        # Calcular reajuste
        adjustment_applied = False
        adjustment_percent = Decimal("0")
        new_value = contract.monthly_value

        if contract.adjustment_enabled and contract.needs_adjustment:
            if custom_adjustment_percent is not None:
                adjustment_percent = custom_adjustment_percent
            elif contract.adjustment_index == AdjustmentIndex.FIXED:
                adjustment_percent = contract.adjustment_fixed_percent or Decimal("0")
            elif contract.adjustment_index != AdjustmentIndex.FIXED:
                raise ValueError(f"Informe o percentual de reajuste: o acumulado 12m do índice {getattr(contract.adjustment_index, 'value', contract.adjustment_index)} não é consultado automaticamente.")

            if adjustment_percent > 0:
                multiplier = Decimal("1") + (adjustment_percent / Decimal("100"))
                new_value = (contract.monthly_value * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                adjustment_applied = True

        return RenewalResult(
            success=True,
            new_end_date=calculated_end_date,
            new_value=new_value,
            adjustment_applied=adjustment_applied,
            adjustment_percent=adjustment_percent if adjustment_applied else None,
            message="Renovação calculada com sucesso",
        )

    def calculate_adjustment(
        self,
        contract: Contract,
        custom_percent: Decimal | None = None,
        effective_date: date | None = None,
    ) -> AdjustmentResult:
        """
        Calcula reajuste do contrato.

        Args:
            contract: Contrato a reajustar
            custom_percent: Percentual personalizado (sobrescreve índice)
            effective_date: Data de efetivação

        Returns:
            AdjustmentResult com detalhes do reajuste
        """
        if not contract.adjustment_enabled:
            return AdjustmentResult(
                success=False,
                previous_value=contract.monthly_value,
                new_value=contract.monthly_value,
                adjustment_percent=Decimal("0"),
                effective_date=effective_date or date.today(),
                message="Reajuste não habilitado para este contrato",
            )

        # Determinar percentual
        if custom_percent is not None:
            percent = custom_percent
            index_used = AdjustmentIndex.CUSTOM
        elif contract.adjustment_index == AdjustmentIndex.FIXED:
            percent = contract.adjustment_fixed_percent or Decimal("0")
            index_used = AdjustmentIndex.FIXED
        elif contract.adjustment_index in self.ECONOMIC_INDICES:
            percent = self.ECONOMIC_INDICES[contract.adjustment_index]
            index_used = contract.adjustment_index
        else:
            percent = Decimal("0")
            index_used = None

        # Calcular novo valor
        multiplier = Decimal("1") + (percent / Decimal("100"))
        new_value = (contract.monthly_value * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return AdjustmentResult(
            success=True,
            previous_value=contract.monthly_value,
            new_value=new_value,
            adjustment_percent=percent,
            index_used=index_used,
            effective_date=effective_date or contract.next_adjustment_date or date.today(),
            message=f"Reajuste de {percent}% calculado",
        )

    def calculate_sla(  # pylint: disable=too-many-locals
        self,
        contract: Contract,
        indicator_results: list[dict[str, Any]],
    ) -> SLACalculation:
        """
        Calcula score de SLA e penalidades.

        Args:
            contract: Contrato com SLA
            indicator_results: Lista com resultados de cada indicador

        Returns:
            SLACalculation com score e penalidades
        """
        if not contract.has_sla or not contract.sla_config:
            return SLACalculation(
                overall_score=Decimal("100"),
                indicators=[],
                penalty_applicable=False,
                penalty_percent=Decimal("0"),
                penalty_amount=Decimal("0"),
                target_met=True,
            )

        sla_config = contract.sla_config
        penalty_config = sla_config.get("penalty", {})

        # Calcular score ponderado
        total_weight = Decimal("0")
        weighted_score = Decimal("0")
        processed_indicators = []

        for result in indicator_results:
            name = result.get("name", "")
            target = Decimal(str(result.get("target", 100)))
            actual = Decimal(str(result.get("actual", 0)))
            weight = Decimal(str(result.get("weight", 1)))

            # Score do indicador: (actual / target) * 100
            if target > 0:
                score = (actual / target * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                score = Decimal("100")

            achieved = actual >= target
            total_weight += weight
            weighted_score += score * weight

            processed_indicators.append(
                {
                    "name": name,
                    "target": float(target),
                    "actual": float(actual),
                    "score": float(score),
                    "weight": float(weight),
                    "achieved": achieved,
                }
            )

        # Score final
        if total_weight > 0:
            overall_score = (weighted_score / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            overall_score = Decimal("100")

        # Calcular penalidade
        target_met = overall_score >= Decimal("100")
        penalty_applicable = not target_met
        penalty_percent = Decimal("0")
        penalty_amount = Decimal("0")

        if penalty_applicable:
            min_score = Decimal(str(penalty_config.get("min_score", 80)))
            max_penalty = Decimal(str(penalty_config.get("max_penalty_percent", 10)))

            if overall_score < min_score:
                # Penalidade proporcional
                gap = Decimal("100") - overall_score
                penalty_percent = min(gap / Decimal("5"), max_penalty)
                pen_calc = contract.monthly_value * penalty_percent / Decimal("100")
                penalty_amount = pen_calc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return SLACalculation(
            overall_score=overall_score,
            indicators=processed_indicators,
            penalty_applicable=penalty_applicable,
            penalty_percent=penalty_percent,
            penalty_amount=penalty_amount,
            target_met=target_met,
        )

    def get_contract_alerts(
        self,
        contracts: list[Contract],
        days_ahead: int = 30,
    ) -> list[ContractAlert]:
        """
        Gera alertas para contratos.

        Args:
            contracts: Lista de contratos ativos
            days_ahead: Dias à frente para alertas de vencimento

        Returns:
            Lista de alertas
        """
        alerts = []

        for contract in contracts:
            if contract.status != ContractStatus.ACTIVE:
                continue

            # Alerta de vencimento
            if contract.end_date:
                days_until_end = (contract.end_date - date.today()).days

                if 0 < days_until_end <= days_ahead:
                    severity = "critical" if days_until_end <= 7 else ("high" if days_until_end <= 15 else "medium")
                    alerts.append(
                        ContractAlert(
                            contract_id=str(contract.id),
                            contract_number=contract.contract_number,
                            alert_type="expiring",
                            severity=severity,
                            message=f"Contrato vence em {days_until_end} dias",
                            days_until_event=days_until_end,
                        )
                    )
                elif days_until_end <= 0:
                    alerts.append(
                        ContractAlert(
                            contract_id=str(contract.id),
                            contract_number=contract.contract_number,
                            alert_type="expiring",
                            severity="critical",
                            message="Contrato vencido",
                            days_until_event=days_until_end,
                        )
                    )

            # Alerta de reajuste
            if contract.needs_adjustment:
                alerts.append(
                    ContractAlert(
                        contract_id=str(contract.id),
                        contract_number=contract.contract_number,
                        alert_type="needs_adjustment",
                        severity="medium",
                        message="Contrato necessita de reajuste",
                        days_until_event=contract.days_until_adjustment,
                    )
                )
            elif contract.days_until_adjustment is not None:
                days = contract.days_until_adjustment
                if 0 < days <= days_ahead:
                    alerts.append(
                        ContractAlert(
                            contract_id=str(contract.id),
                            contract_number=contract.contract_number,
                            alert_type="needs_adjustment",
                            severity="low",
                            message=f"Reajuste em {days} dias",
                            days_until_event=days,
                        )
                    )

        # Ordenar por severidade
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 4), a.days_until_event or 999))

        return alerts

    def generate_contract_summary(
        self,
        contracts: list[Contract],
    ) -> dict[str, Any]:
        """
        Gera resumo de contratos.

        Args:
            contracts: Lista de contratos

        Returns:
            Dict com métricas resumidas
        """
        active = [c for c in contracts if c.status == ContractStatus.ACTIVE]
        recurring = [c for c in active if c.contract_type == ContractType.RECURRING]

        total_revenue = sum(c.monthly_value for c in recurring)
        avg_value = total_revenue / len(recurring) if recurring else Decimal("0")

        return {
            "total_contracts": len(contracts),
            "active_contracts": len(active),
            "recurring_contracts": len(recurring),
            "total_monthly_revenue": float(total_revenue),
            "average_contract_value": float(avg_value),
            "expiring_soon": len([c for c in active if c.is_expiring_soon]),
            "needs_adjustment": len([c for c in active if c.needs_adjustment]),
            "with_sla": len([c for c in active if c.has_sla]),
            "by_status": {status.value: len([c for c in contracts if c.status == status]) for status in ContractStatus},
        }

    def get_current_economic_index(
        self,
        index_type: AdjustmentIndex,
    ) -> Decimal:
        """
        Retorna índice econômico atual.

        Em produção, integrar com API do IBGE/FGV.
        """
        return self.ECONOMIC_INDICES.get(index_type, Decimal("0"))

    def _add_months(self, start_date: date, months: int) -> date:
        """Adiciona meses a uma data."""
        year = start_date.year + (start_date.month + months - 1) // 12
        month = (start_date.month + months - 1) % 12 + 1

        # Ajustar dia se necessário
        day = min(start_date.day, self._days_in_month(year, month))

        return date(year, month, day)

    def _days_in_month(self, year: int, month: int) -> int:
        """Retorna número de dias no mês."""
        if month in [1, 3, 5, 7, 8, 10, 12]:
            return 31
        elif month in [4, 6, 9, 11]:
            return 30
        elif year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            return 29
        return 28
