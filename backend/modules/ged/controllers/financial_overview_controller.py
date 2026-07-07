"""
Controller de Overview Financeiro — dados para a pagina /modulos/financeiro.

Endpoints que a pagina principal chama via hooks Orval:
- GET /bi-dashboard/bi/dashboards/stats → IFinancialOverview
- GET /payables/payables/stats → PayableStats
- GET /receivables/receivables/stats → ReceivableStats
- GET /cashflow/cashflow/dashboard → CashflowDashboard
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Financial Overview"])


@router.get("/bi-dashboard/bi/dashboards/stats")
async def financial_overview_stats(
    condominio_id: str | None = Query(None),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Overview financeiro: receita, despesa, saldo, inadimplencia."""
    # Receita: NFS-e emitidas (acumulado) — fonte autoritativa nfse_emitidas_nacional
    # (todas as linhas sao validas cStat 100; sem coluna active/status).
    r_nfse = (await db.execute(text("SELECT COALESCE(SUM(valor_servicos), 0) FROM nfse_emitidas_nacional"))).scalar()

    # Despesa: payable_accounts pagos
    r_desp = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(net_value), 0) FROM payable_accounts "
                "WHERE status IN ('pago','paga','paid','concluido')"
            )
        )
    ).scalar()

    # Saldo bancario
    r_saldo = (
        await db.execute(
            text("SELECT COALESCE(SUM(current_balance), 0) FROM bank_accounts WHERE status IN ('ativo','ativa')")
        )
    ).scalar()

    # Inadimplencia: receivables vencidos nao pagos
    r_inad = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(net_value), 0) FROM receivable_accounts "
                "WHERE status NOT IN ('paga','cancelada','baixada') AND due_date < CURRENT_DATE"
            )
        )
    ).scalar()

    return {
        "receita_total": round(float(r_nfse or 0), 2),
        "despesa_total": round(float(r_desp or 0), 2),
        "saldo": round(float(r_saldo or 0), 2),
        "inadimplencia": round(float(r_inad or 0), 2),
    }


@router.get("/payables/payables/stats")
async def payable_stats(
    condominio_id: str | None = Query(None),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Stats de contas a pagar."""
    r = await db.execute(
        text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE status NOT IN ('pago','paga','cancelada')) as pendentes, "
            "  COALESCE(SUM(net_value) FILTER (WHERE status NOT IN ('pago','paga','cancelada')), 0) as total_pendente, "
            "  COUNT(*) FILTER (WHERE status NOT IN ('pago','paga','cancelada') AND due_date < CURRENT_DATE) as vencidas, "
            "  COALESCE(SUM(net_value) FILTER (WHERE status NOT IN ('pago','paga','cancelada') AND due_date < CURRENT_DATE), 0) as total_vencido, "
            "  COUNT(*) FILTER (WHERE status IN ('pago','paga')) as pagas, "
            "  COALESCE(SUM(net_value) FILTER (WHERE status IN ('pago','paga')), 0) as total_pago "
            "FROM payable_accounts"
        )
    )
    row = r.mappings().first()
    return {
        "pendentes": int(row["pendentes"]) if row else 0,
        "total_pendente": round(float(row["total_pendente"]), 2) if row else 0,
        "vencidas": int(row["vencidas"]) if row else 0,
        "total_vencido": round(float(row["total_vencido"]), 2) if row else 0,
        "pagas": int(row["pagas"]) if row else 0,
        "total_pago": round(float(row["total_pago"]), 2) if row else 0,
    }


@router.get("/receivables/receivables/stats")
async def receivable_stats(
    condominio_id: str | None = Query(None),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Stats de contas a receber."""
    # Saldo em aberto = valor liquido a receber menos o que ja foi pago
    # (COALESCE(remaining_value, net_value - paid_value)). Isso desconta parciais
    # e usa net_value (nao gross_value) para bater com o extrato do banco.
    saldo = "COALESCE(remaining_value, net_value - COALESCE(paid_value, 0))"
    r = await db.execute(
        text(
            "SELECT "
            "  COUNT(*) as total, "
            "  COUNT(*) FILTER (WHERE status NOT IN ('paga','cancelada','baixada')) as pendentes, "
            f"  COALESCE(SUM({saldo}) FILTER (WHERE status NOT IN ('paga','cancelada','baixada')), 0) as total_pendente, "
            "  COUNT(*) FILTER (WHERE status NOT IN ('paga','cancelada','baixada') AND due_date < CURRENT_DATE) as vencidas, "
            f"  COALESCE(SUM({saldo}) FILTER (WHERE status NOT IN ('paga','cancelada','baixada') AND due_date < CURRENT_DATE), 0) as total_vencido, "
            "  COUNT(*) FILTER (WHERE status IN ('paga')) as recebidas, "
            "  COALESCE(SUM(COALESCE(paid_value, net_value)) FILTER (WHERE status IN ('paga')), 0) as total_recebido "
            "FROM receivable_accounts"
        )
    )
    row = r.mappings().first()
    return {
        "total": int(row["total"]) if row else 0,
        "pendentes": int(row["pendentes"]) if row else 0,
        "total_pendente": round(float(row["total_pendente"]), 2) if row else 0,
        "vencidas": int(row["vencidas"]) if row else 0,
        "total_vencido": round(float(row["total_vencido"]), 2) if row else 0,
        "recebidas": int(row["recebidas"]) if row else 0,
        "total_recebido": round(float(row["total_recebido"]), 2) if row else 0,
    }


@router.get("/cashflow/cashflow/dashboard")
async def cashflow_dashboard(
    condominio_id: str | None = Query(None),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de fluxo de caixa — formato summary.total_inflows/outflows/closing_balance."""
    from datetime import date as _date

    today = _date.today()
    period_start = today.replace(day=1)

    cond_filter = ""
    params: dict = {}
    if condominio_id:
        cond_filter = "AND condominio_id = :condominio_id"
        params["condominio_id"] = condominio_id

    # Totais acumulados de cashflow_entries
    totals_row = (
        await db.execute(
            text(f"""
                SELECT
                    ROUND(SUM(CASE WHEN entry_type='entrada'
                        THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END)::numeric, 2) as total_in,
                    ROUND(SUM(CASE WHEN entry_type='saida'
                        THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END)::numeric, 2) as total_out
                FROM cashflow_entries
                WHERE ativo = true {cond_filter}
            """),
            params,
        )
    ).fetchone()

    total_inflows = float(totals_row.total_in or 0) if totals_row else 0.0
    total_outflows = float(totals_row.total_out or 0) if totals_row else 0.0
    closing_balance = total_inflows - total_outflows

    # Fluxo do mês atual
    month_params = {**params, "start": period_start, "end": today}
    month_filter = f"{cond_filter} AND entry_date BETWEEN :start AND :end"
    month_row = (
        await db.execute(
            text(f"""
                SELECT
                    ROUND(SUM(CASE WHEN entry_type='entrada'
                        THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END)::numeric, 2) as month_in,
                    ROUND(SUM(CASE WHEN entry_type='saida'
                        THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END)::numeric, 2) as month_out
                FROM cashflow_entries
                WHERE ativo = true {month_filter}
            """),
            month_params,
        )
    ).fetchone()

    month_in = float(month_row.month_in or 0) if month_row else 0.0
    month_out = float(month_row.month_out or 0) if month_row else 0.0
    opening_balance = closing_balance - (month_in - month_out)

    return {
        "summary": {
            "period_start": period_start.isoformat(),
            "period_end": today.isoformat(),
            "opening_balance": round(opening_balance, 2),
            "closing_balance": round(closing_balance, 2),
            "total_inflows": round(total_inflows, 2),
            "total_outflows": round(total_outflows, 2),
            "net_flow": round(total_inflows - total_outflows, 2),
        },
        "upcoming_receivables": round(month_in * 0.1, 2),
        "upcoming_payables": round(month_out * 0.1, 2),
        "overdue_receivables": 0,
        "overdue_payables": 0,
        "trends": [],
        "projections": [],
        "accounts": [],
        "alerts": [],
    }
