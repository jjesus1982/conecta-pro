"""
GedeonFinancialOrchestrator — Orquestrador Layer 2 dos agentes financeiros.

Coordena execução paralela dos agentes financeiros com:
- Shared token injection para evitar rate-limit de logins simultâneos
- Snapshot de contexto financeiro real do DB para todos os agentes
- Pipeline diário com execução paralela (run_all_daily)
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gedeon.financial.orchestrator")


class GedeonFinancialOrchestrator:
    """Orquestrador GEDEON Layer 2 — Agentes Financeiros."""

    def __init__(self, db: AsyncSession, shared_token: str | None = None):
        self.db = db
        self.shared_token = shared_token  # Evita rate-limit de logins simultâneos

    # ─────────────────────────────────────────────────────────────────────
    # CONTEXTO FINANCEIRO — snapshot real do banco
    # ─────────────────────────────────────────────────────────────────────

    async def _get_context(self) -> dict[str, Any]:
        """Monta snapshot financeiro real para todos os agentes."""
        try:
            from modules.financial.models.payable_account import (
                PayableAccount,
                PayableStatus,
            )
            from modules.financial.models.receivable_account import (
                ReceivableAccount,
                ReceivableStatus,
            )

            today = date.today()
            past_30 = today - timedelta(days=30)

            # Receita: recebíveis pagos nos últimos 30 dias
            recv_30_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.payment_date >= past_30,
                    ReceivableAccount.payment_date <= today,
                    ReceivableAccount.status == ReceivableStatus.PAGA.value,
                )
            )
            receita_30d = float((await self.db.execute(recv_30_q)).scalar_one() or 0)

            # Despesas: pagáveis pagos nos últimos 30 dias
            pay_30_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.payment_date >= past_30,
                    PayableAccount.payment_date <= today,
                    PayableAccount.status == PayableStatus.PAGA.value,
                )
            )
            despesas_30d = float((await self.db.execute(pay_30_q)).scalar_one() or 0)

            # Inadimplentes: recebíveis vencidos há mais de 5 dias
            cutoff = today - timedelta(days=5)
            inadimplentes_q = select(
                func.count(ReceivableAccount.id),
                func.coalesce(func.sum(ReceivableAccount.net_value), 0),
            ).where(
                and_(
                    ReceivableAccount.due_date < cutoff,
                    ReceivableAccount.status.notin_(("paga", "pago", "cancelada", "baixada")),  # em aberto (enum não tem ABERTA)
                )
            )
            inadimplentes_row = (await self.db.execute(inadimplentes_q)).first()
            qtd_inadimplentes = int(inadimplentes_row[0] or 0)
            total_inadimplencia = float(inadimplentes_row[1] or 0)

            # A receber (próximos 30 dias)
            a_receber_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= today,
                    ReceivableAccount.due_date <= today + timedelta(days=30),
                    ReceivableAccount.status.notin_(("paga", "pago", "cancelada", "baixada")),  # em aberto (enum não tem ABERTA)
                )
            )
            a_receber_30d = float((await self.db.execute(a_receber_q)).scalar_one() or 0)

            # A pagar (próximos 30 dias)
            a_pagar_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.due_date >= today,
                    PayableAccount.due_date <= today + timedelta(days=30),
                    PayableAccount.status.notin_(("paga", "cancelada")),  # em aberto (enum não tem ABERTA)
                )
            )
            a_pagar_30d = float((await self.db.execute(a_pagar_q)).scalar_one() or 0)

            margem = ((receita_30d - despesas_30d) / receita_30d * 100) if receita_30d > 0 else 0.0
            taxa_inadimplencia = (total_inadimplencia / receita_30d * 100) if receita_30d > 0 else 0.0

            return {
                "receita_30d": receita_30d,
                "despesas_30d": despesas_30d,
                "margem_pct": round(margem, 2),
                "qtd_inadimplentes": qtd_inadimplentes,
                "total_inadimplencia": total_inadimplencia,
                "taxa_inadimplencia_pct": round(taxa_inadimplencia, 2),
                "a_receber_30d": a_receber_30d,
                "a_pagar_30d": a_pagar_30d,
                "liquidez_projetada": round(a_receber_30d - a_pagar_30d, 2),
                "data_snapshot": today.isoformat(),
            }
        except Exception as exc:
            logger.warning("Erro ao montar contexto financeiro: %s", exc)
            return {
                "receita_30d": 0,
                "despesas_30d": 0,
                "margem_pct": 0,
                "qtd_inadimplentes": 0,
                "total_inadimplencia": 0,
                "taxa_inadimplencia_pct": 0,
                "a_receber_30d": 0,
                "a_pagar_30d": 0,
                "liquidez_projetada": 0,
                "data_snapshot": date.today().isoformat(),
                "erro": str(exc),
            }

    # ─────────────────────────────────────────────────────────────────────
    # EXECUÇÕES INDIVIDUAIS
    # ─────────────────────────────────────────────────────────────────────

    async def run_risk_monitor(self) -> dict[str, Any]:
        """RiskMonitorAgent — executa varredura de riscos."""
        logger.info("[Gedeon] RiskMonitor iniciado")
        try:
            from modules.financial.agents.risk_monitor import RiskMonitorAgent

            context = await self._get_context()
            agent = RiskMonitorAgent(self.db)
            alerts = await agent.scan()
            # Fase 0 (Task 6): persiste no sino (fim do "cérebro amnésico"). Idempotente
            # por categoria de risco (o risco que persiste ATUALIZA a linha, não spamma).
            # Best-effort: falha de persistência nunca derruba a varredura.
            persistidos = 0
            try:
                from modules.notifications.services.alert_ingest import enqueue_alert

                for a in alerts:
                    acao = a.get("action")
                    await enqueue_alert(
                        self.db,
                        category=f"risco_{a.get('category', 'geral')}",
                        source_entity_type="portfolio",
                        source_entity_id=None,
                        severity=a.get("level", "atencao"),
                        title=a.get("title", "Risco financeiro"),
                        body=(a.get("description") or "") + (f" | Ação: {acao}" if acao else ""),
                    )
                    persistidos += 1
                await self.db.commit()
            except Exception as _pe:  # noqa: BLE001
                logger.warning("[Gedeon] RiskMonitor persistência falhou (segue): %s", _pe)
                await self.db.rollback()
            return {
                "agent": "RiskMonitorAgent",
                "alerts": alerts,
                "persistidos": persistidos,
                "context": context,
                "status": "ok",
            }
        except Exception as exc:
            logger.error("[Gedeon] RiskMonitor erro: %s", exc)
            return {"agent": "RiskMonitorAgent", "status": "error", "error": str(exc)}

    async def run_cashflow_predictor(self) -> dict[str, Any]:
        """CashflowPredictorAgent — projeta fluxo de caixa 90 dias."""
        logger.info("[Gedeon] CashflowPredictor iniciado")
        try:
            from modules.financial.agents.cashflow_predictor import CashflowPredictorAgent

            context = await self._get_context()
            agent = CashflowPredictorAgent(self.db)
            prediction = await agent.predict(days=90)
            return {
                "agent": "CashflowPredictorAgent",
                "prediction": prediction,
                "context": context,
                "status": "ok",
            }
        except Exception as exc:
            logger.error("[Gedeon] CashflowPredictor erro: %s", exc)
            return {"agent": "CashflowPredictorAgent", "status": "error", "error": str(exc)}

    async def run_collection_negotiator(self) -> dict[str, Any]:
        """CollectionNegotiatorAgent — analisa inadimplência e estratégias."""
        logger.info("[Gedeon] CollectionNegotiator iniciado")
        try:
            from modules.financial.agents.collection_negotiator import CollectionNegotiatorAgent

            context = await self._get_context()
            agent = CollectionNegotiatorAgent(self.db)
            analysis = await agent.analisar()
            return {
                "agent": "CollectionNegotiatorAgent",
                "analysis": analysis,
                "context": context,
                "status": "ok",
            }
        except Exception as exc:
            logger.error("[Gedeon] CollectionNegotiator erro: %s", exc)
            return {"agent": "CollectionNegotiatorAgent", "status": "error", "error": str(exc)}

    # ─────────────────────────────────────────────────────────────────────
    # PIPELINE DIÁRIO PARALELO
    # ─────────────────────────────────────────────────────────────────────

    async def run_all_daily(self) -> dict[str, Any]:
        """Pipeline diário — todos os agentes em paralelo (07:00)."""
        logger.info("[Gedeon] Pipeline diário iniciado")
        from datetime import datetime

        start = datetime.now()

        # Contexto compartilhado para todos os agentes
        context = await self._get_context()

        # Execução paralela dos 3 agentes principais
        results = await asyncio.gather(
            self.run_risk_monitor(),
            self.run_cashflow_predictor(),
            self.run_collection_negotiator(),
            return_exceptions=True,
        )

        risk_result, cashflow_result, collection_result = results

        # Normalizar exceções
        if isinstance(risk_result, Exception):
            risk_result = {"agent": "RiskMonitorAgent", "status": "error", "error": str(risk_result)}
        if isinstance(cashflow_result, Exception):
            cashflow_result = {"agent": "CashflowPredictorAgent", "status": "error", "error": str(cashflow_result)}
        if isinstance(collection_result, Exception):
            collection_result = {
                "agent": "CollectionNegotiatorAgent",
                "status": "error",
                "error": str(collection_result),
            }

        elapsed = (datetime.now() - start).total_seconds()
        ok_count = sum(
            1
            for r in [risk_result, cashflow_result, collection_result]
            if isinstance(r, dict) and r.get("status") == "ok"
        )

        logger.info("[Gedeon] Pipeline diário concluído em %.2fs — %d/3 OK", elapsed, ok_count)

        return {
            "pipeline": "daily_all",
            "context": context,
            "risk_monitor": risk_result,
            "cashflow_predictor": cashflow_result,
            "collection_negotiator": collection_result,
            "summary": {
                "agents_ok": ok_count,
                "agents_total": 3,
                "elapsed_seconds": round(elapsed, 2),
                "executed_at": start.isoformat(),
            },
        }
