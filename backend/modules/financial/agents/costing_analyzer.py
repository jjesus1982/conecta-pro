"""CostingAnalyzerAgent — Análise de custeio ABC por tipo de serviço."""

from datetime import date
from typing import Any

from sqlalchemy import func, select

from modules.financial.agents.base_agent import BaseAgent

# Resposta vazia quando a tabela não possui registros (zero dados simulados)
_EMPTY_MARGINS: list[dict] = [
    {
        "service_type": t,
        "label": label,
        "margin_pct": 0.0,
        "total_cost": 0.0,
        "total_revenue": 0.0,
        "color": c,
        "fonte": "sem_dados",
    }
    for t, label, c in [
        ("portaria", "Portaria", "#3B82F6"),
        ("limpeza", "Limpeza", "#10B981"),
        ("jardinagem", "Jardinagem", "#84CC16"),
        ("seguranca_eletronica", "Segurança Eletrônica", "#F59E0B"),
        ("portaria_remota", "Portaria Remota", "#8B5CF6"),
    ]
]

_SERVICE_LABELS: dict[str, str] = {
    "portaria": "Portaria",
    "limpeza": "Limpeza",
    "jardinagem": "Jardinagem",
    "seguranca_eletronica": "Segurança Eletrônica",
    "portaria_remota": "Portaria Remota",
}

_SERVICE_COLORS: dict[str, str] = {
    "portaria": "#3B82F6",
    "limpeza": "#10B981",
    "jardinagem": "#84CC16",
    "seguranca_eletronica": "#F59E0B",
    "portaria_remota": "#8B5CF6",
}


class CostingAnalyzerAgent(BaseAgent):
    """Agente de análise de custeio por tipo de serviço e contrato."""

    name = "costing_analyzer"

    # ------------------------------------------------------------------ #
    # execute() dispatcher — permite chamar via agent.execute("method")  #
    # ------------------------------------------------------------------ #

    async def _execute(self, method: str = "get_margin_by_service_type", **kwargs) -> Any:
        dispatch = {
            "get_margin_by_service_type": self.get_margin_by_service_type,
            "get_contract_costs": self.get_contract_costs,
            "identify_anomalies": self.identify_anomalies,
        }
        handler = dispatch.get(method)
        if handler is None:
            raise ValueError(f"Método desconhecido: {method!r}")
        return await handler(**kwargs)

    async def _fallback(self, method: str = "get_margin_by_service_type", **kwargs) -> Any:
        if method == "get_margin_by_service_type":
            return _EMPTY_MARGINS
        return []

    # ------------------------------------------------------------------ #
    # Método 1 — Margem por tipo de serviço                               #
    # ------------------------------------------------------------------ #

    async def get_margin_by_service_type(self) -> list[dict]:
        """
        Retorna margem média por tipo de serviço para o mês atual e os
        2 meses anteriores. Tabela vazia → retorna VAZIO honesto (0.0, fonte='sem_dados'); NÃO fabrica.
        """
        from modules.financial.models.contract_cost import ContractCost

        today = date.today()
        # Primeiro dia do mês atual
        _first_of_current = today.replace(day=1)
        # Primeiro dia 3 meses atrás
        month = today.month - 2
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        first_of_range = date(year, month, 1)

        q = (
            select(
                ContractCost.service_type,
                func.avg(ContractCost.gross_margin).label("avg_margin"),
                func.sum(ContractCost.total_cost).label("sum_cost"),
                func.sum(ContractCost.contract_revenue).label("sum_revenue"),
            )
            .where(ContractCost.reference_month >= first_of_range)
            .group_by(ContractCost.service_type)
        )

        result = (await self.session.execute(q)).all()

        if not result:
            self.logger.info("[costing_analyzer] Tabela vazia — retornando vazio honesto (sem_dados).")
            return _EMPTY_MARGINS

        rows = []
        for row in result:
            stype = str(row.service_type)
            rows.append(
                {
                    "service_type": stype,
                    "label": _SERVICE_LABELS.get(stype, stype),
                    "margin_pct": round(float(row.avg_margin or 0), 2),
                    "total_cost": round(float(row.sum_cost or 0), 2),
                    "total_revenue": round(float(row.sum_revenue or 0), 2),
                    "color": _SERVICE_COLORS.get(stype, "#6B7280"),
                }
            )
        return rows

    # ------------------------------------------------------------------ #
    # Método 2 — Últimos registros de custo por contrato                  #
    # ------------------------------------------------------------------ #

    async def get_contract_costs(self, limit: int = 10) -> list[dict]:
        """
        Retorna os N registros mais recentes de financial_contract_costs.
        """
        from modules.financial.models.contract_cost import ContractCost

        q = select(ContractCost).order_by(ContractCost.reference_month.desc(), ContractCost.contract_name).limit(limit)
        rows = (await self.session.execute(q)).scalars().all()

        if not rows:
            return []

        return [
            {
                "id": str(r.id),
                "contract_id": r.contract_id,
                "contract_name": r.contract_name,
                "service_type": str(r.service_type),
                "service_label": _SERVICE_LABELS.get(str(r.service_type), str(r.service_type)),
                "reference_month": r.reference_month.isoformat() if r.reference_month else None,
                "total_cost": round(float(r.total_cost or 0), 2),
                "contract_revenue": round(float(r.contract_revenue or 0), 2),
                "gross_margin": round(float(r.gross_margin or 0), 2),
                "qty_workers": r.qty_workers or 0,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # Método 3 — Identificação de anomalias de custo                      #
    # ------------------------------------------------------------------ #

    async def identify_anomalies(self) -> list[dict]:
        """
        Identifica contratos com custo de mão-de-obra proporcional
        (labor_base / total_cost) > 20% acima da média do mesmo tipo de serviço.

        Retorna lista de {contract_name, anomaly_type, description, severity}.
        """
        from modules.financial.models.contract_cost import ContractCost

        today = date.today()
        first_of_month = today.replace(day=1)

        # Busca todos os contratos do mês atual com custo total > 0
        q = select(ContractCost).where(
            ContractCost.reference_month == first_of_month,
            ContractCost.total_cost > 0,
        )
        rows = (await self.session.execute(q)).scalars().all()

        if not rows:
            return []

        # Calcula proporção de mão-de-obra por tipo de serviço
        # ratio = (labor_base + labor_charges + labor_provisions) / total_cost
        from collections import defaultdict

        by_type: dict[str, list[float]] = defaultdict(list)
        contract_ratios: list[tuple] = []  # (row, ratio)

        for r in rows:
            labor_total = float(
                (r.labor_base or 0)
                + (r.labor_charges or 0)
                + (r.labor_provisions or 0)
                + (r.labor_overtime_50 or 0)
                + (r.labor_overtime_100 or 0)
                + (r.labor_night_add or 0)
            )
            total = float(r.total_cost or 1)
            ratio = labor_total / total
            stype = str(r.service_type)
            by_type[stype].append(ratio)
            contract_ratios.append((r, ratio, stype))

        # Média por tipo
        avg_by_type: dict[str, float] = {k: sum(v) / len(v) for k, v in by_type.items()}

        anomalies = []
        threshold = 0.20  # 20% acima da média

        for r, ratio, stype in contract_ratios:
            avg = avg_by_type.get(stype, ratio)
            if avg > 0 and (ratio - avg) / avg > threshold:
                excess_pct = round((ratio - avg) / avg * 100, 1)
                anomalies.append(
                    {
                        "contract_name": r.contract_name,
                        "anomaly_type": "labor_cost_high",
                        "description": (
                            f"Custo de mão-de-obra representa {ratio * 100:.1f}% do custo total, "
                            f"{excess_pct}% acima da média de "
                            f"{_SERVICE_LABELS.get(stype, stype)} ({avg * 100:.1f}%)."
                        ),
                        "severity": "alta" if excess_pct > 35 else "media",
                    }
                )

        return anomalies
