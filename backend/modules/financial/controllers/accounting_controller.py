"""Controllers para o modulo de Contabilidade."""

import logging
import os

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounting", tags=["Contabilidade"])


# =============================================================================
# ChartOfAccounts Endpoints
# =============================================================================


# =============================================================================
# AccountingAccount Endpoints
# =============================================================================


# =============================================================================
# CostCenter Endpoints
# =============================================================================


# =============================================================================
# AccountingPeriod Endpoints
# =============================================================================


# =============================================================================
# JournalEntry Endpoints
# =============================================================================


# =============================================================================
# TrialBalance Endpoints
# =============================================================================


def _get_raw_conn():
    """Conexão psycopg2 direta à DB."""
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    return psycopg2.connect(url)


@router.get("/dre")
async def accounting_dre(
    periodo: str | None = Query(None, description="Período YYYY-MM"),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """DRE a partir dos lançamentos contábeis reais (accounting_entries).
    if not periodo:  # sem período somava a vida inteira e rotulava como DRE do mês (08/09/2026)
        from datetime import date as _d
        periodo = _d.today().strftime("%Y-%m")

    Plano de contas REAL: 4.x = RECEITA (4.1.1 = serviços/NFS-e), 5.x = DESPESA (5.1 = pessoal/folha+
    encargos, 5.2 = operacional/tomadas), 5.2.2 = ISS (dedução da receita). Os filtros antigos usavam
    3.1.1/4.x (outro plano) e zeravam tudo mesmo com 1396 lançamentos e R$1,8M de receita real.
    """
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                sum(CASE WHEN conta_credito LIKE '4%%' THEN valor ELSE 0 END)::float as receita_bruta,
                sum(CASE WHEN conta_debito  LIKE '5.2.2%%' THEN valor ELSE 0 END)::float as deducoes,
                sum(CASE WHEN conta_debito  LIKE '5.1%%' THEN valor ELSE 0 END)::float as despesa_pessoal,
                sum(CASE WHEN conta_debito  LIKE '5.1.1.02%%' THEN valor ELSE 0 END)::float as despesa_encargos,
                sum(CASE WHEN conta_debito  LIKE '5%%' AND conta_debito NOT LIKE '5.2.2%%'
                         THEN valor ELSE 0 END)::float as despesas_operacionais,
                sum(CASE WHEN tipo_lancamento = 'nfse_emitida' THEN valor ELSE 0 END)::float as receita_servicos,
                count(*) as total_lancamentos
            FROM accounting_entries
            WHERE status = 'confirmado'
              AND (%s IS NULL OR periodo_competencia = %s)
        """,
            [periodo, periodo],
        )

        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row, strict=False))

        receita = data.get("receita_bruta", 0) or 0
        deducoes = data.get("deducoes", 0) or 0
        despesas = data.get("despesas_operacionais", 0) or 0
        receita_liquida = receita - deducoes
        cur.close()
        conn.close()

        return {
            "periodo": periodo,
            "receita_bruta": receita,
            "deducoes": deducoes,
            "receita_liquida": receita_liquida,
            "despesa_pessoal": data.get("despesa_pessoal", 0) or 0,
            "despesa_encargos": data.get("despesa_encargos", 0) or 0,
            "despesas_operacionais": despesas,
            "resultado_operacional": receita_liquida - despesas,
            "receita_servicos_nfse": data.get("receita_servicos", 0),
            "total_lancamentos": data.get("total_lancamentos", 0),
        }
    except Exception as e:
        logger.error(f"Erro no DRE: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dre-consolidado")
async def accounting_dre_consolidado(
    periodo: str | None = Query(None, description="Período YYYY-MM (default: todos)"),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """DRE consolidado REAL por empresa (multi-CNPJ), a partir do razão accounting_entries
    isolado por empresa_id. Substitui a 'calculadora' hardcoded do frontend consolidado.
    Onde uma empresa não tem lançamento, retorna zeros (honesto: aguardando dado)."""
    try:
        conn = _get_raw_conn()
        cur = conn.cursor()

        # Empresas cadastradas (id, cnpj, razão, regime)
        cur.execute(
            "SELECT id::text, cnpj, razao_social, regime_tributario, COALESCE(is_principal,false) "
            "FROM empresas ORDER BY is_principal DESC NULLS LAST"
        )
        empresas = cur.fetchall()

        blocos = []
        tot = {"receita_bruta": 0.0, "deducoes": 0.0, "despesa_pessoal": 0.0,
               "despesa_encargos": 0.0, "despesas_operacionais": 0.0, "resultado": 0.0}
        for emp_id, cnpj, razao, regime, principal in empresas:
            from modules.financial.services.plano_contas_caixa import FILTRO_RAZAO, saldo
            cur.execute(  # plano de 13/08/2026; até 07/09 lia '3.1.1' (capital social) como receita
                f"""
                SELECT
                    (-{saldo('4', '%%')})::float,
                    {saldo('5.2.2.01', '%%')}::float,
                    {saldo('5.1.1.01', '%%')}::float,
                    {saldo('5.1.1.02', '%%')}::float,
                    ({saldo('5', '%%')} - {saldo('5.2.2.01', '%%')})::float,
                    count(*)
                FROM accounting_entries
                WHERE {FILTRO_RAZAO} AND empresa_id = %s::uuid
                  AND (%s IS NULL OR periodo_competencia = %s)
                """,
                [emp_id, periodo, periodo],
            )
            r = cur.fetchone()
            rb, ded, dp, de, desp = (float(x or 0) for x in r[:5])
            rec_liq = rb - ded
            resultado = rec_liq - desp
            blocos.append({
                "empresa_id": emp_id, "cnpj": cnpj, "razao_social": razao,
                "regime": regime, "is_principal": principal,
                "receita_bruta": round(rb, 2), "deducoes": round(ded, 2),
                "receita_liquida": round(rec_liq, 2),
                "despesa_pessoal": round(dp, 2), "despesa_encargos": round(de, 2),
                "despesas_operacionais": round(desp, 2),
                "resultado": round(resultado, 2), "lancamentos": r[5],
                "sem_dado": r[5] == 0,
            })
            tot["receita_bruta"] += rb
            tot["deducoes"] += ded
            tot["despesa_pessoal"] += dp
            tot["despesa_encargos"] += de
            tot["despesas_operacionais"] += desp
            tot["resultado"] += resultado

        cur.close()
        conn.close()
        return {
            "periodo": periodo or "todos",
            "empresas": blocos,
            "consolidado": {k: round(v, 2) for k, v in tot.items()},
            "fonte": "accounting_entries (razão real, sem valores fabricados)",
        }
    except Exception as e:
        logger.error(f"Erro no DRE consolidado: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
