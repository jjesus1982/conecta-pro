"""Controller para fluxo de caixa, entradas, previsões e análise de IA."""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models import (
    CashFlowEntryStatus,
    CashFlowEntryType,
    CashFlowSourceType,
    TransactionCategory,
    TransactionStatus,
    TransactionType,
)
from modules.financial.repositories import (
    BankAccountRepository,
    BankTransactionRepository,
    CashFlowEntryRepository,
    CashFlowForecastRepository,
)
from modules.financial.schemas import (
    AIForecastRequest,
    CashFlowDashboard,
    CashFlowEntryCreate,
    CashFlowEntryFilter,
    CashFlowEntryRealize,
    CashFlowEntryResponse,
    CashFlowEntryUpdate,
    CashFlowProjection,
    CashFlowSummary,
    CashFlowTrend,
    ForecastOpportunity,
    ForecastRisk,
)
from modules.financial.services.cashflow_ai_service import CashFlowAIService
from modules.financial.services.cashflow_service import CashFlowService
from modules.financial.services.payable_ai_service import PayableAIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cashflow", tags=["Fluxo de Caixa"])


# ==================== DEPENDÊNCIAS ====================


def get_cashflow_service(session: AsyncSession = Depends(get_session)) -> CashFlowService:
    """Retorna instância do CashFlowService."""
    return CashFlowService(session)


def get_ai_service(session: AsyncSession = Depends(get_session)) -> CashFlowAIService:
    """Retorna instância do CashFlowAIService."""
    return CashFlowAIService(session)


def get_payable_ai_service(session: AsyncSession = Depends(get_session)) -> PayableAIService:
    """Retorna instância do PayableAIService."""
    return PayableAIService(session)


def get_entry_repository(session: AsyncSession = Depends(get_session)) -> CashFlowEntryRepository:
    """Retorna instância do CashFlowEntryRepository."""
    return CashFlowEntryRepository(session)


def get_forecast_repository(
    session: AsyncSession = Depends(get_session),
) -> CashFlowForecastRepository:
    """Retorna instância do CashFlowForecastRepository."""
    return CashFlowForecastRepository(session)


def get_account_repository(session: AsyncSession = Depends(get_session)) -> BankAccountRepository:
    """Retorna instância do BankAccountRepository."""
    return BankAccountRepository(session)


# ==================== PROJEÇÕES E RESUMO ====================


@router.get(
    "/summary",
    response_model=CashFlowSummary,
    summary="Resumo de fluxo de caixa",
)
async def get_summary(
    condominio_id: UUID | None = Query(None),
    period_days: int = Query(30, ge=7, le=365, description="Período em dias"),
    service: CashFlowService = Depends(get_cashflow_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CashFlowSummary:
    """Retorna resumo do fluxo de caixa."""
    return await service.get_summary(condominio_id, period_days)


@router.get(
    "/trends",
    response_model=list[CashFlowTrend],
    summary="Tendências de fluxo de caixa",
)
async def get_trends(
    condominio_id: UUID | None = Query(None),
    months: int = Query(12, ge=3, le=24, description="Meses de histórico"),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[CashFlowTrend]:
    """Retorna tendências mensais de fluxo de caixa (a partir de cashflow_entries).

    condominio_id None agrega todos (mesmo padrão do summary/entries — FIN-01).
    """
    condominio_filter = "AND condominio_id = :cid" if condominio_id else ""
    rows = (
        (
            await session.execute(
                text(f"""
                    SELECT
                        to_char(date_trunc('month', entry_date), 'YYYY-MM') AS period,
                        COALESCE(SUM(CASE WHEN entry_type = 'entrada'
                            THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END), 0) AS inflows,
                        COALESCE(SUM(CASE WHEN entry_type = 'saida'
                            THEN COALESCE(realized_amount, expected_amount, 0) ELSE 0 END), 0) AS outflows
                    FROM cashflow_entries
                    WHERE ativo = true
                      {condominio_filter}
                      AND entry_date >= (date_trunc('month', CURRENT_DATE) - make_interval(months => :months))
                    GROUP BY 1
                    ORDER BY 1
                """),
                {"cid": str(condominio_id), "months": months}
                if condominio_id
                else {"months": months},
            )
        )
        .mappings()
        .all()
    )

    trends: list[CashFlowTrend] = []
    running_balance = Decimal("0")
    for r in rows:
        inflows = Decimal(str(r["inflows"] or 0))
        outflows = Decimal(str(r["outflows"] or 0))
        net_flow = inflows - outflows
        running_balance += net_flow
        variance_pct = float(net_flow / inflows * 100) if inflows else None
        trends.append(
            CashFlowTrend(
                period=r["period"],
                inflows=inflows,
                outflows=outflows,
                net_flow=net_flow,
                balance=running_balance,
                variance_pct=variance_pct,
            )
        )
    return trends


@router.get(
    "/category-breakdown",
    summary="Breakdown por categoria",
)
async def get_category_breakdown(
    condominio_id: UUID,
    start_date: date | None = Query(None, description="Data inicial"),
    end_date: date | None = Query(None, description="Data final"),
    service: CashFlowService = Depends(get_cashflow_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[dict]:
    """Retorna breakdown de despesas por categoria."""
    return await service.get_category_breakdown(condominio_id, start_date, end_date)


@router.get(
    "/supplier-breakdown",
    summary="Breakdown por fornecedor",
)
async def get_supplier_breakdown(
    condominio_id: UUID,
    start_date: date | None = Query(None, description="Data inicial"),
    end_date: date | None = Query(None, description="Data final"),
    limit: int = Query(10, ge=1, le=50, description="Quantidade de fornecedores"),
    service: CashFlowService = Depends(get_cashflow_service),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[dict]:
    """Retorna breakdown de despesas por fornecedor."""
    return await service.get_supplier_breakdown(condominio_id, start_date, end_date, limit)


@router.get(
    "/dashboard",
    response_model=CashFlowDashboard,
    summary="Dashboard financeiro completo",
)
async def get_dashboard(
    condominio_id: UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> CashFlowDashboard:
    """Retorna dados completos para dashboard financeiro."""
    today = date.today()
    period_start = today.replace(day=1)
    _DEFAULT_CID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    cid = str(condominio_id) if condominio_id else _DEFAULT_CID

    # ── Saldo real das contas bancárias (closing_balance) ──────────────────
    # Usa SUM direto para incluir TODAS as contas ativas (status='ativa')
    bal_result = await session.execute(
        text("""
            SELECT COALESCE(SUM(current_balance), 0) as total
            FROM bank_accounts
            WHERE condominio_id = :cid
              AND ativo = true
              AND status = 'ativa'
        """),
        {"cid": cid},
    )
    closing_balance = Decimal(str(bal_result.scalar_one() or 0))

    # ── Entradas e saídas do mês atual (realized_amount, TODOS os source_types) ──
    flows_result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(CASE WHEN entry_type = 'entrada' THEN realized_amount ELSE 0 END), 0) AS total_in,
                COALESCE(SUM(CASE WHEN entry_type = 'saida'   THEN realized_amount ELSE 0 END), 0) AS total_out
            FROM cashflow_entries
            WHERE condominio_id = :cid
              AND ativo = true
              AND entry_date BETWEEN :start AND :end
        """),
        {"cid": cid, "start": period_start, "end": today},
    )
    flows_row = flows_result.one()
    total_inflows = Decimal(str(flows_row.total_in or 0))
    total_outflows = Decimal(str(flows_row.total_out or 0))
    net_flow = total_inflows - total_outflows

    # opening_balance = saldo real atual - fluxo líquido do período
    opening_balance = closing_balance - net_flow

    # ── Breakdown por categoria ─────────────────────────────────────────────
    cat_result = await session.execute(
        text("""
            SELECT entry_type, category,
                   COALESCE(SUM(realized_amount), 0) as total
            FROM cashflow_entries
            WHERE condominio_id = :cid
              AND ativo = true
              AND entry_date BETWEEN :start AND :end
            GROUP BY entry_type, category
        """),
        {"cid": cid, "start": period_start, "end": today},
    )
    inflows_by_category: dict = {}
    outflows_by_category: dict = {}
    for row in cat_result:
        cat = row.category or "outros"
        val = Decimal(str(row.total or 0))
        if row.entry_type == "entrada":
            inflows_by_category[cat] = str(val)
        else:
            outflows_by_category[cat] = str(val)

    # ── Contas a receber — FONTE ÚNICA canônica (NFS-e emitidas − recebido, aging FIFO) ─────
    # Antes lia receivable_accounts (SEED fictício: "Parise Village" etc. no cid a1b2c3d4…),
    # que divergia do relatório /financial/relatorios/contas-receber (base NFS-e). Agora ambas
    # as telas consomem o MESMO cálculo do FluxoCaixaService, então o número reconcilia.
    try:
        from modules.financial.services.fluxo_caixa_service import FluxoCaixaService

        _car = FluxoCaixaService().contas_a_receber(today.year)
        _total_ar = _car.get("total_a_receber", 0.0) or 0.0
        # A Receber por competência já é "em aberto" (faturado − recebido, floor 0). Vencido =
        # competências fechadas (mês anterior ao atual) ainda com saldo em aberto.
        _mes_atual = today.strftime("%Y-%m")
        _overdue_ar = sum(
            (m.get("a_receber", 0.0) or 0.0)
            for m in _car.get("meses", [])
            if m.get("competencia", "") < _mes_atual and (m.get("a_receber", 0.0) or 0.0) > 0
        )
        _qtd_pending = sum(1 for m in _car.get("meses", []) if (m.get("a_receber", 0.0) or 0.0) > 0)
        _qtd_overdue = sum(
            1 for m in _car.get("meses", [])
            if m.get("competencia", "") < _mes_atual and (m.get("a_receber", 0.0) or 0.0) > 0
        )
    except Exception as _e:  # noqa: BLE001
        logger.warning("A Receber canônico (NFS-e) indisponível, caindo p/ 0: %s", _e)
        _total_ar = _overdue_ar = 0.0
        _qtd_pending = _qtd_overdue = 0

    class _Rec:
        pending = _total_ar
        overdue = _overdue_ar
        qtd_pending = _qtd_pending
        qtd_overdue = _qtd_overdue

    rec = _Rec()

    # ── Contas a pagar (pendente / vencido) — dados reais ───────────────────
    pay_result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(net_value) FILTER (
                    WHERE status NOT IN ('paga','pago','cancelada','cancelado','cancelled')), 0) AS pending,
                COALESCE(SUM(net_value) FILTER (
                    WHERE due_date < CURRENT_DATE
                    AND status NOT IN ('paga','pago','cancelada','cancelado','cancelled')), 0) AS overdue,
                COUNT(*) FILTER (
                    WHERE due_date < CURRENT_DATE
                    AND status NOT IN ('paga','pago','cancelada','cancelado','cancelled')) AS qtd_overdue,
                COUNT(*) FILTER (
                    WHERE status NOT IN ('paga','pago','cancelada','cancelado','cancelled')) AS qtd_pending
            FROM payable_accounts
            WHERE condominio_id = :cid
        """),
        {"cid": cid},
    )
    pay = pay_result.one()

    pending_receivables = Decimal(str(rec.pending or 0))
    overdue_receivables = Decimal(str(rec.overdue or 0))
    pending_payables = Decimal(str(pay.pending or 0))
    overdue_payables = Decimal(str(pay.overdue or 0))

    summary = CashFlowSummary(
        period_start=period_start,
        period_end=today,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        total_inflows=total_inflows,
        total_outflows=total_outflows,
        net_flow=net_flow,
        inflows_by_category=inflows_by_category,
        outflows_by_category=outflows_by_category,
        pending_receivables=pending_receivables,
        pending_payables=pending_payables,
        overdue_receivables=overdue_receivables,
        overdue_payables=overdue_payables,
    )

    return CashFlowDashboard(
        summary=summary,
        trends=[],
        projections=[],
        accounts=[],
        alerts=[],
        upcoming_payables=int(pay.qtd_pending or 0),
        upcoming_receivables=int(rec.qtd_pending or 0),
        overdue_payables=int(pay.qtd_overdue or 0),
        overdue_receivables=int(rec.qtd_overdue or 0),
    )


# ==================== ENTRADAS DE FLUXO DE CAIXA ====================


@router.post(
    "/sync",
    summary="Sincronizar bank_transactions → cashflow_entries",
)
async def sync_cashflow_entries(
    current_user=Depends(get_current_user),
) -> dict:
    """Dispara sync manual de bank_transactions pendentes → cashflow_entries."""
    try:
        from modules.financial.services.auto_sync_service import run_full_sync

        result = run_full_sync(limit=500)
        logger.info("Sync cashflow manual: %s", result)
        return {"ok": True, **result}
    except Exception as e:
        logger.error("Erro no sync cashflow: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro no sync: {e}",
        )


@router.post(
    "/entries",
    response_model=CashFlowEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar entrada de fluxo de caixa",
)
async def create_entry(
    data: CashFlowEntryCreate,
    repo: CashFlowEntryRepository = Depends(get_entry_repository),
    current_user: dict = Depends(get_current_user),
) -> CashFlowEntryResponse:
    """Cria nova entrada de fluxo de caixa."""
    try:
        payload = data.model_dump()
        # Normaliza entry_type para os labels do ENUM nativo do Postgres
        # (cashflowentrytype = entrada/saida). O frontend/schema pode enviar
        # income/expense (ou entrada/saida). Sem isso o INSERT falha (enum mismatch).
        _ENTRY_TYPE_MAP = {
            "income": "entrada",
            "inflow": "entrada",
            "credit": "entrada",
            "entrada": "entrada",
            "expense": "saida",
            "outflow": "saida",
            "debit": "saida",
            "saida": "saida",
            "transferencia": "transferencia",
            "transfer": "transferencia",
            "previsao": "previsao",
            "ajuste": "ajuste",
        }
        raw_type = str(payload.get("entry_type", "")).lower().strip()
        payload["entry_type"] = _ENTRY_TYPE_MAP.get(raw_type, raw_type)

        entry = await repo.create(payload)
        _user_email = (
            current_user.get("email")
            if isinstance(current_user, dict)
            else getattr(current_user, "email", None)
        )
        logger.info(f"Entrada de fluxo criada: {entry.id} por {_user_email}")
        return CashFlowEntryResponse.model_validate(entry)
    except Exception as e:
        logger.error(f"Erro ao criar entrada: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar entrada de fluxo de caixa",
        )


@router.put(
    "/entries/{entry_id}",
    response_model=CashFlowEntryResponse,
    summary="Atualizar entrada",
)
async def update_entry(
    entry_id: UUID,
    data: CashFlowEntryUpdate,
    repo: CashFlowEntryRepository = Depends(get_entry_repository),
    current_user: dict = Depends(get_current_user),
) -> CashFlowEntryResponse:
    """Atualiza entrada de fluxo de caixa."""
    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada",
        )

    if entry.status == CashFlowEntryStatus.REALIZADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível alterar entrada já realizada",
        )

    update_data = data.model_dump(exclude_unset=True)
    updated = await repo.update(entry_id, update_data)
    logger.info(f"Entrada atualizada: {entry_id} por {current_user.get('email')}")
    return CashFlowEntryResponse.model_validate(updated)


@router.delete(
    "/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir entrada",
)
async def delete_entry(
    entry_id: UUID,
    repo: CashFlowEntryRepository = Depends(get_entry_repository),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Exclui entrada de fluxo de caixa."""
    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada",
        )

    await repo.delete(entry_id)
    logger.info(f"Entrada excluída: {entry_id} por {current_user.get('email')}")


# ==================== PREVISÕES ====================


# ==================== INTELIGÊNCIA ARTIFICIAL ====================


# ==================== ANÁLISES LEGADAS (COMPATIBILIDADE) ====================


