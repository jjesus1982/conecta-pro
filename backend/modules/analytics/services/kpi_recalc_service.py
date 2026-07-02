"""KPI Recalculation Service.

Recalcula os KPIs "congelados" das tabelas `executive_kpis` e `financial_kpis`
a partir do dado REAL das tabelas de origem (contracts, hr_payslips, clients,
employees, bank_accounts, inter_transactions, nfses).

Regra: para cada KPI reconhecido (por code/codigo), calcula o valor real,
move current -> previous e grava o novo valor + last_calculated_at = now().
KPIs sem fonte real definida NÃO são tocados (não inventamos números).

Uso:
    from modules.analytics.services.kpi_recalc_service import recalcular_kpis
    resultado = await recalcular_kpis(db)  # db: AsyncSession

Fontes provadas (2026-07, DB conecta_pro):
    - MRR:              SUM(contracts.monthly_value) WHERE status='active' = 270586.96
    - FOLHA:            SUM(hr_payslips.total_earnings) na última competência = 97504.07
    - CLIENTES ATIVOS:  COUNT(DISTINCT contracts.client_id) WHERE status='active' = 10
                        (clients total = 14)
    - FUNCIONARIOS:     COUNT(employees) WHERE status='ativo' = 50
    - SALDO:            SUM(bank_accounts.current_balance) WHERE ativo = 54688.03
    - NFS-e:            COUNT(nfses) WHERE status='autorizada' = 27
    - ISS:              SUM(nfses.iss_valor) WHERE status='autorizada' = 27133.76
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Coletores de fonte real. Cada coletor devolve um Decimal (o valor atual real)
# ou None (fonte sem dado → não sobrescreve o KPI).
# ─────────────────────────────────────────────────────────────────────────────


async def _scalar(db: AsyncSession, sql: str) -> Any:
    result = await db.execute(text(sql))
    return result.scalar()


async def src_mrr(db: AsyncSession) -> Decimal | None:
    """MRR = soma do valor mensal dos contratos ativos."""
    val = await _scalar(
        db,
        "SELECT COALESCE(SUM(monthly_value), 0) FROM contracts WHERE status = 'active'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_folha(db: AsyncSession) -> Decimal | None:
    """Folha = total_earnings dos holerites da última competência disponível."""
    val = await _scalar(
        db,
        """
        SELECT COALESCE(SUM(total_earnings), 0)
        FROM hr_payslips
        WHERE (reference_year, reference_month) = (
            SELECT reference_year, reference_month
            FROM hr_payslips
            ORDER BY reference_year DESC, reference_month DESC
            LIMIT 1
        )
        """,
    )
    return Decimal(str(val)) if val is not None else None


async def src_clientes_ativos(db: AsyncSession) -> Decimal | None:
    """Clientes ativos = clientes distintos com pelo menos um contrato ativo."""
    val = await _scalar(
        db,
        "SELECT COUNT(DISTINCT client_id) FROM contracts WHERE status = 'active'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_funcionarios_ativos(db: AsyncSession) -> Decimal | None:
    """Funcionários ativos = employees com status 'ativo'."""
    val = await _scalar(
        db,
        "SELECT COUNT(*) FROM employees WHERE status = 'ativo'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_saldo(db: AsyncSession) -> Decimal | None:
    """Saldo = soma do current_balance das contas bancárias ativas."""
    val = await _scalar(
        db,
        "SELECT COALESCE(SUM(current_balance), 0) FROM bank_accounts WHERE ativo = TRUE",
    )
    return Decimal(str(val)) if val is not None else None


async def src_contratos_ativos(db: AsyncSession) -> Decimal | None:
    """Contratos ativos = linhas em contracts com status 'active'."""
    val = await _scalar(
        db,
        "SELECT COUNT(*) FROM contracts WHERE status = 'active'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_nfse_count(db: AsyncSession) -> Decimal | None:
    """NFS-e emitidas = notas autorizadas."""
    val = await _scalar(
        db,
        "SELECT COUNT(*) FROM nfses WHERE status = 'autorizada'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_iss_total(db: AsyncSession) -> Decimal | None:
    """ISS recolhido = soma do iss_valor das NFS-e autorizadas."""
    val = await _scalar(
        db,
        "SELECT COALESCE(SUM(iss_valor), 0) FROM nfses WHERE status = 'autorizada'",
    )
    return Decimal(str(val)) if val is not None else None


async def src_ticket_medio(db: AsyncSession) -> Decimal | None:
    """Ticket médio = MRR / nº de contratos ativos."""
    mrr = await src_mrr(db)
    n = await src_contratos_ativos(db)
    if not mrr or not n or n == 0:
        return None
    return (mrr / n).quantize(Decimal("0.0001"))


async def src_receita_por_funcionario(db: AsyncSession) -> Decimal | None:
    """Receita por funcionário = MRR / funcionários ativos."""
    mrr = await src_mrr(db)
    n = await src_funcionarios_ativos(db)
    if not mrr or not n or n == 0:
        return None
    return (mrr / n).quantize(Decimal("0.0001"))


async def src_custo_folha_faturamento(db: AsyncSession) -> Decimal | None:
    """Custo folha / faturamento (%) = folha / MRR * 100."""
    folha = await src_folha(db)
    mrr = await src_mrr(db)
    if not folha or not mrr or mrr == 0:
        return None
    return (folha / mrr * Decimal("100")).quantize(Decimal("0.0001"))


async def src_margem_bruta(db: AsyncSession) -> Decimal | None:
    """Margem bruta (%) = (MRR - folha) / MRR * 100.

    Aproximação baseada na única fonte de custo real disponível (folha).
    """
    folha = await src_folha(db)
    mrr = await src_mrr(db)
    if not folha or not mrr or mrr == 0:
        return None
    return ((mrr - folha) / mrr * Decimal("100")).quantize(Decimal("0.0001"))


# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento KPI (code/codigo) -> coletor de fonte real.
# Códigos SEM entrada aqui NÃO são recalculados (ficam como estão).
# ─────────────────────────────────────────────────────────────────────────────

# executive_kpis.code -> coletor
EXECUTIVE_MAP = {
    "MRR": src_mrr,
    "FOLHA": src_folha,
    "MARGEM": src_margem_bruta,
    "HEADCOUNT": src_funcionarios_ativos,
    "CLIENTES": src_clientes_ativos,
    "TICKET": src_ticket_medio,
    "RPF": src_receita_por_funcionario,
    "CUSTO_FOLHA": src_custo_folha_faturamento,
    "NFSE_COUNT": src_nfse_count,
    "ISS_TOTAL": src_iss_total,
}

# financial_kpis.codigo -> coletor
FINANCIAL_MAP = {
    "KPI-001": src_mrr,  # MRR
    "KPI-002": src_saldo,  # Saldo Inter
    "KPI-005": src_contratos_ativos,  # Contratos Ativos
    # KPI-003 (Compliance Lucro Real), KPI-004 (Inadimplência),
    # KPI-006 (Score Saúde Financeira) — sem fonte real definida: NÃO tocar.
}


def _trend(current: Decimal, previous: Decimal | None) -> str:
    """Tendência textual comparando novo x anterior (minúsculas p/ executive)."""
    if previous is None:
        return "stable"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "stable"


def _variance_pct(current: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous) * Decimal("100")).quantize(Decimal("0.0001"))


async def _recalc_executive(db: AsyncSession, now: datetime) -> list[dict]:
    """Recalcula executive_kpis. Retorna lista de {code, old, new, source}."""
    changed: list[dict] = []
    result = await db.execute(
        text("SELECT code, current_value FROM executive_kpis WHERE ativo = TRUE")
    )
    rows = result.fetchall()

    for code, current_value in rows:
        collector = EXECUTIVE_MAP.get(code)
        if collector is None:
            continue  # KPI sem fonte real → não tocar
        new_value = await collector(db)
        if new_value is None:
            logger.info("[KPI-recalc] executive %s: fonte sem dado, mantido", code)
            continue

        previous = Decimal(str(current_value)) if current_value is not None else None
        variance = (new_value - previous) if previous is not None else None
        var_pct = _variance_pct(new_value, previous)
        trend = _trend(new_value, previous)

        await db.execute(
            text(
                """
                UPDATE executive_kpis
                SET previous_value = current_value,
                    current_value = :new_value,
                    variance = :variance,
                    variance_percentage = :var_pct,
                    trend = :trend,
                    last_calculated_at = :now,
                    updated_at = :now
                WHERE code = :code
                """
            ),
            {
                "new_value": new_value,
                "variance": variance,
                "var_pct": var_pct,
                "trend": trend,
                "now": now,
                "code": code,
            },
        )
        changed.append(
            {
                "code": code,
                "old": float(previous) if previous is not None else None,
                "new": float(new_value),
                "source": collector.__name__,
            }
        )
        logger.info("[KPI-recalc] executive %s: %s -> %s", code, previous, new_value)

    return changed


async def _recalc_financial(db: AsyncSession, now: datetime) -> list[dict]:
    """Recalcula financial_kpis. Retorna lista de {codigo, old, new, source}."""
    changed: list[dict] = []
    result = await db.execute(
        text("SELECT codigo, valor_atual FROM financial_kpis WHERE ativo = TRUE")
    )
    rows = result.fetchall()

    for codigo, valor_atual in rows:
        collector = FINANCIAL_MAP.get(codigo)
        if collector is None:
            continue  # KPI sem fonte real → não tocar
        new_value = await collector(db)
        if new_value is None:
            logger.info("[KPI-recalc] financial %s: fonte sem dado, mantido", codigo)
            continue

        previous = Decimal(str(valor_atual)) if valor_atual is not None else None
        var_pct = _variance_pct(new_value, previous)

        await db.execute(
            text(
                """
                UPDATE financial_kpis
                SET valor_anterior = valor_atual,
                    valor_atual = :new_value,
                    variacao_percent = :var_pct,
                    variacao_percentual = :var_pct2,
                    ultima_atualizacao = :now_naive,
                    ultimo_calculo_at = :now,
                    updated_at = :now_naive
                WHERE codigo = :codigo
                """
            ),
            {
                "new_value": new_value,
                "var_pct": var_pct,
                # variacao_percentual é numeric(10,2)
                "var_pct2": (var_pct.quantize(Decimal("0.01")) if var_pct is not None else None),
                "now": now,
                "now_naive": now.replace(tzinfo=None),
                "codigo": codigo,
            },
        )
        changed.append(
            {
                "codigo": codigo,
                "old": float(previous) if previous is not None else None,
                "new": float(new_value),
                "source": collector.__name__,
            }
        )
        logger.info("[KPI-recalc] financial %s: %s -> %s", codigo, previous, new_value)

    return changed


async def recalcular_kpis(db: AsyncSession) -> dict:
    """Recalcula todos os KPIs com fonte real e persiste.

    Move current -> previous, grava o novo valor e last_calculated_at = now().
    KPIs sem fonte real permanecem intactos.

    Returns:
        dict com contagens e detalhe das mudanças.
    """
    now = datetime.now(timezone.utc)

    executive_changes = await _recalc_executive(db, now)
    financial_changes = await _recalc_financial(db, now)

    await db.commit()

    resultado = {
        "recalculated_at": now.isoformat(),
        "executive_updated": len(executive_changes),
        "financial_updated": len(financial_changes),
        "executive_changes": executive_changes,
        "financial_changes": financial_changes,
    }
    logger.info(
        "[KPI-recalc] concluído: executive=%s financial=%s",
        len(executive_changes),
        len(financial_changes),
    )
    return resultado
