"""Celery Tasks - Módulo Financeiro.

Sync automático: bank_transactions → cashflow_entries
Executado a cada hora via Celery Beat.
"""

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="financial.sincronizar_nfse_nacional",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def sincronizar_nfse_nacional_task(self):
    """Puxa NFS-e emitidas (receita) + tomadas (custo) do ADN nacional (gov.br) e fecha o razão.
    Diário: junho e meses futuros completam sozinhos quando o Ambiente Nacional recebe as notas.
    """
    try:
        from modules.financial.services.ledger_auto_service import LedgerAutoService
        from modules.financial.services.nfse_nacional_sync_service import NFSeNacionalSyncService

        svc = NFSeNacionalSyncService()
        emit = svc.sincronizar()
        tom = svc.sincronizar_tomadas()
        fechar = LedgerAutoService().fechar()
        # Fecha o fluxo de caixa: corrige sinal dos recebidos + justifica cada saída
        try:
            from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
            fc = FluxoCaixaService().recategorizar_saidas()
        except Exception as fce:
            logger.warning("recategorizacao fluxo caixa falhou (segue): %s", fce)
            fc = {"erro": str(fce)}
        logger.info("NFS-e nacional sync: emitidas=%s tomadas=%s fluxo=%s",
                    emit.get("validas_cStat100"), tom.get("recebidas"), fc.get("reclassificadas"))
        return {"emitidas": emit.get("por_competencia"), "tomadas": tom.get("por_competencia_2026"),
                "razao": fechar.get("novos_lancamentos"), "fluxo_caixa": fc.get("por_categoria")}
    except Exception as exc:
        logger.error("Erro no sync NFS-e nacional: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.fechar_razao_auto",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def fechar_razao_auto_task(self):
    """Contabilidade que fecha sozinha: posta folha (hr_payslips) + ISS (nfses) no razão
    accounting_entries, idempotente, com empresa_id. Alimenta balancete + DRE.
    Executado diariamente via Celery Beat.
    """
    try:
        from modules.financial.services.ledger_auto_service import LedgerAutoService

        result = LedgerAutoService().fechar()
        logger.info("Fechamento automático do razão: %s", result)
        return result
    except Exception as exc:
        logger.error("Erro no fechamento do razão: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.sync_cashflow_entries",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def sync_cashflow_entries_task(self):
    """Sincroniza bank_transactions pendentes → cashflow_entries.

    Executado a cada hora via Celery Beat.
    Idempotente: ON CONFLICT (bank_transaction_id) DO NOTHING.
    """
    try:
        from modules.financial.services.auto_sync_service import run_full_sync

        result = run_full_sync(limit=500)
        logger.info(
            "[Financial Task] sync_cashflow: pending=%s synced=%s errors=%s",
            result["pending"],
            result["synced"],
            result["errors"],
        )
        return result
    except Exception as exc:
        logger.error("[Financial Task] sync_cashflow error: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.inter_reconciliacao_diaria",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def inter_reconciliacao_diaria_task(self):
    """Conciliação bancária DIÁRIA: sincroniza o extrato do Banco Inter e organiza a conciliação.

    Puxa os últimos 7 dias do extrato via API → grava em inter_transactions → faz a PONTE para
    bank_transactions (conciliação) → auto-categoriza os PIX de VT+VR de diaristas (R$32 e múltiplos)
    e marca os fornecedores conhecidos. Idempotente. Não move dinheiro nem baixa contas.
    """
    try:
        async def _run(session):
            from modules.integrations.inter.inter_sync_service import InterSyncService
            svc = InterSyncService(session)
            return await svc.sincronizar_extrato(dias=7)

        result = _run_async(_run)
        logger.info("[Financial Task] inter_reconciliacao_diaria: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] inter_reconciliacao_diaria error: %s", exc)
        raise self.retry(exc=exc)


@app.task(
    name="financial.inter_monitorar_pendentes",
    bind=True,
    max_retries=1,
)
def inter_monitorar_pendentes_task(self):
    """MONITOR automático: verifica no Inter o status dos pagamentos que estão
    'aguardando_aprovacao' e atualiza para 'confirmado'/'erro' quando o Inter concluir/rejeitar.
    Assim o Jordan não precisa clicar em 'Status Inter' — o sistema acompanha em tempo real.
    Só leitura no Inter; não move dinheiro."""
    try:
        async def _run(session):
            from sqlalchemy import text

            from modules.integrations.inter.services.payment_service import InterPaymentService

            rows = (
                await session.execute(
                    text(
                        "SELECT id FROM inter_payments "
                        "WHERE status = 'aguardando_aprovacao' "
                        "AND created_at > now() - interval '10 days' "
                        "ORDER BY created_at DESC LIMIT 50"
                    )
                )
            ).fetchall()
            svc = InterPaymentService(session)
            atualizados = 0
            for r in rows:
                try:
                    res = await svc.atualizar_status_inter(str(r[0]))
                    if res.get("status") != "aguardando_aprovacao":
                        atualizados += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning("monitor pendente %s: %s", r[0], e)
            return {"checados": len(rows), "concluidos_ou_alterados": atualizados}

        result = _run_async(_run)
        logger.info("[Financial Task] inter_monitorar_pendentes: %s", result)
        return result
    except Exception as exc:
        logger.error("[Financial Task] inter_monitorar_pendentes error: %s", exc)
        raise self.retry(exc=exc, countdown=120)


# ═══════════════════════════════════════
# GEDEON LAYER 2 — Execução automática dos agentes financeiros
# ═══════════════════════════════════════


def _run_async(coro):
    """Helper para rodar corrotinas async nas tasks Celery."""
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            return await coro(session)

    return asyncio.run(_inner())


@app.task(name="gedeon.risk_monitor", bind=True, max_retries=3)
def gedeon_risk_monitor_task(self):
    """RiskMonitorAgent — executa a cada 5 minutos."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_risk_monitor()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@app.task(name="gedeon.daily_all", bind=True, max_retries=1)
def gedeon_daily_all_task(self):
    """Pipeline diário — todos os agentes (07:00)."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_all_daily()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@app.task(name="gedeon.cashflow_predictor", bind=True, max_retries=2)
def gedeon_cashflow_predictor_task(self):
    """CashflowPredictorAgent — diariamente às 07:00."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_cashflow_predictor()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@app.task(name="gedeon.collection_negotiator", bind=True, max_retries=2)
def gedeon_collection_negotiator_task(self):
    """CollectionNegotiatorAgent — diariamente às 09:00."""

    def run(session):
        from modules.financial.agents.gedeon_financial_orchestrator import GedeonFinancialOrchestrator

        orch = GedeonFinancialOrchestrator(db=session)
        return orch.run_collection_negotiator()

    try:
        return _run_async(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)
