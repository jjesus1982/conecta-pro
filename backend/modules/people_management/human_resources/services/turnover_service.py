"""
Servico de Turnover do RH.

Calcula indicadores reais de turnover a partir da tabela employees:
admissoes, desligamentos, taxa trimestral, distribuicao por cargo e
motivos de desligamento — incluindo o gap honesto de motivos nao
informados (chamada de acao para preencher a ficha do funcionario).

Nota historica: este arquivo era um re-export morto de
modules.retention.turnover.services.turnover_service, caminho que nunca
existiu (o modulo retention expoe TurnoverPredictor/RiskAnalyzer). O
service real do RH vive aqui agora.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TurnoverService:
    """Indicadores de turnover baseados em dados reais de employees."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dashboard(self) -> dict[str, Any]:
        """Dashboard de turnover com dados reais e gaps de dado explicitos."""
        total = (await self.db.execute(text("SELECT count(*) FROM employees"))).scalar() or 0
        ativos = (
            await self.db.execute(text("SELECT count(*) FROM employees WHERE lower(status) = 'ativo'"))
        ).scalar() or 0

        admitidos_90d = (
            await self.db.execute(
                text("SELECT count(*) FROM employees WHERE data_admissao >= CURRENT_DATE - INTERVAL '90 days'")
            )
        ).scalar() or 0

        desligados_90d = (
            await self.db.execute(
                text("SELECT count(*) FROM employees WHERE data_demissao >= CURRENT_DATE - INTERVAL '90 days'")
            )
        ).scalar() or 0

        sem_motivo_90d = (
            await self.db.execute(
                text(
                    "SELECT count(*) FROM employees "
                    "WHERE data_demissao >= CURRENT_DATE - INTERVAL '90 days' "
                    "AND motivo_desligamento IS NULL"
                )
            )
        ).scalar() or 0

        media = (ativos + total) / 2 if total > 0 else 1
        taxa_turnover = round(((admitidos_90d + desligados_90d) / 2 / media) * 100, 2) if media > 0 else 0

        por_cargo = (
            (
                await self.db.execute(
                    text(
                        "SELECT cargo, count(*) as qtd FROM employees "
                        "WHERE status = 'ativo' GROUP BY cargo ORDER BY qtd DESC"
                    )
                )
            )
            .mappings()
            .all()
        )

        result: dict[str, Any] = {
            "total_colaboradores": total,
            "ativos": ativos,
            "admitidos_90_dias": admitidos_90d,
            "desligados_90_dias": desligados_90d,
            "taxa_turnover_trimestral": taxa_turnover,
            "distribuicao_cargo": [dict(r) for r in por_cargo],
            "motivo_desligamento_pendentes": sem_motivo_90d,
        }
        if desligados_90d > 0 and sem_motivo_90d > 0:
            result["data_gap"] = (
                f"motivo_desligamento nao informado em {sem_motivo_90d}/{desligados_90d} "
                "desligados nos ultimos 90 dias — preencha o motivo na ficha do funcionario "
                "para habilitar a analise de causas de turnover."
            )
        return result

    async def motivos(self) -> dict[str, Any]:
        """Distribuicao por motivo de desligamento nos ultimos 12 meses."""
        rows = (
            (
                await self.db.execute(
                    text(
                        "SELECT motivo_desligamento, COUNT(*) as total "
                        "FROM employees "
                        "WHERE motivo_desligamento IS NOT NULL "
                        "AND data_demissao >= CURRENT_DATE - INTERVAL '12 months' "
                        "GROUP BY motivo_desligamento ORDER BY total DESC"
                    )
                )
            )
            .mappings()
            .all()
        )
        sem_motivo = (
            await self.db.execute(
                text(
                    "SELECT count(*) FROM employees "
                    "WHERE motivo_desligamento IS NULL "
                    "AND data_demissao >= CURRENT_DATE - INTERVAL '12 months'"
                )
            )
        ).scalar() or 0

        result: dict[str, Any] = {
            "motivos": [dict(r) for r in rows],
            "sem_motivo_informado": sem_motivo,
            "periodo": "12_meses",
        }
        if sem_motivo > 0:
            result["data_gap"] = (
                f"{sem_motivo} desligamento(s) nos ultimos 12 meses sem motivo informado — "
                "os graficos de motivo so refletem os registros preenchidos."
            )
        return result


__all__ = ["TurnoverService"]
