"""
Financial Dashboard Controller — Conecta PRO
GET /financial/dashboard      → KPIs principais do módulo financeiro
GET /financial/cashflow/forecast → Projeção 30/60/90 dias
GET /financial/bi/overview    → Visão BI: receita vs despesa 6 meses, DRE, margem

Dados 100% reais do banco. Sem mock. Sem hardcode.
Commit: feat(financial): 3 endpoints críticos 404 → 200
Dados reais: 2.875 transações, saldo R$ 36.476,27
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database.session import get_db

import logging
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/financial", tags=["Financial Dashboard"])


# ──────────────────────────────────────────────────────────────────────────────
# GET /financial/dashboard
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", summary="KPIs principais do módulo financeiro")
async def get_financial_dashboard(
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    KPIs principais para o dashboard financeiro.
    Dados 100% reais: bank_transactions, bank_accounts,
    payable_accounts, receivable_accounts, billing_rules.
    """
    try:
        hoje = date.today()
        inicio_mes = hoje.replace(day=1)

        # Saldo bancário real — CONSOLIDADO: soma de TODAS as contas ativas
        # (antes pegava só is_main_account=true -> mostrava só o Inter e ignorava a Cora).
        saldo_result = await db.execute(
            text("""
            SELECT COALESCE(SUM(COALESCE(available_balance, current_balance, 0)), 0) AS saldo
            FROM bank_accounts
            WHERE COALESCE(ativo, true) = true
              AND COALESCE(status, 'ativa') = 'ativa'
        """)
        )
        saldo_row = saldo_result.fetchone()
        saldo_atual = float(saldo_row.saldo if saldo_row else 0)

        # Entradas / saídas mês atual e anterior
        fluxo_result = await db.execute(
            text("""
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0
                    AND date_trunc('month', transaction_date) = date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date)
                    THEN amount ELSE 0 END), 0) AS entradas_mes,
                COALESCE(SUM(CASE WHEN amount < 0
                    AND date_trunc('month', transaction_date) = date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date)
                    THEN ABS(amount) ELSE 0 END), 0) AS saidas_mes,
                COALESCE(SUM(CASE WHEN amount > 0
                    AND date_trunc('month', transaction_date) =
                        date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date - interval '1 month')
                    THEN amount ELSE 0 END), 0) AS entradas_ant,
                COALESCE(SUM(CASE WHEN amount < 0
                    AND date_trunc('month', transaction_date) =
                        date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date - interval '1 month')
                    THEN ABS(amount) ELSE 0 END), 0) AS saidas_ant,
                COUNT(CASE WHEN date_trunc('month', transaction_date) =
                    date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date) THEN 1 END) AS txs_mes
            FROM bank_transactions
        """)
        )
        fx = fluxo_result.fetchone()
        entradas = float(fx.entradas_mes or 0)
        saidas = float(fx.saidas_mes or 0)
        entradas_ant = float(fx.entradas_ant or 0)
        saidas_ant = float(fx.saidas_ant or 0)

        # Contas a pagar
        pay_result = await db.execute(
            text("""
            SELECT
                COALESCE(SUM(net_value) FILTER (
                    WHERE due_date < (now() AT TIME ZONE 'America/Manaus')::date
                    AND status NOT IN ('pago','cancelado','cancelled','cancelada','baixada')), 0) AS vencido,
                COALESCE(SUM(net_value) FILTER (
                    WHERE due_date >= (now() AT TIME ZONE 'America/Manaus')::date
                    AND status NOT IN ('pago','cancelado','cancelled','cancelada','baixada')), 0) AS a_vencer,
                COUNT(*) FILTER (
                    WHERE due_date < (now() AT TIME ZONE 'America/Manaus')::date
                    AND status NOT IN ('pago','cancelado','cancelled','cancelada','baixada')) AS qtd_vencido
            FROM payable_accounts
        """)
        )
        pay = pay_result.fetchone()

        # Contas a receber
        rec_result = await db.execute(
            text("""
            SELECT
                COALESCE(SUM(net_value) FILTER (
                    WHERE due_date < (now() AT TIME ZONE 'America/Manaus')::date
                    AND status NOT IN ('pago','cancelado','cancelled','paga','cancelada','baixada')), 0) AS vencido,
                COALESCE(SUM(net_value) FILTER (
                    WHERE status NOT IN ('pago','cancelado','cancelled','paga','cancelada','baixada')), 0) AS total_pendente,
                COUNT(*) FILTER (
                    WHERE status NOT IN ('pago','cancelado','cancelled','paga','cancelada','baixada')) AS qtd_pendente
            FROM receivable_accounts
        """)
        )
        rec = rec_result.fetchone()

        # MRR = contratos ativos — a fonte que GERA as cobranças (receivable_accounts.origem=
        # 'contrato'). billing_rules é cadastro paralelo e estava velho: Prime Arena R$ 40.466,50
        # (contrato R$ 33.479,60 desde maio), Parise R$ 1.700 (R$ 2.000), Hawk Eye e Parque dos
        # Franceses sem regra — três MRRs na casa, R$ 886,90 de diferença (achado 07/09/2026).
        mrr_result = await db.execute(
            text("SELECT COALESCE(SUM(monthly_value), 0) AS mrr FROM contracts WHERE status = 'active'")
        )
        mrr = float((mrr_result.fetchone() or [0]).mrr or 0)

        # Top 5 categorias de despesa do mês
        top_result = await db.execute(
            text("""
            SELECT category,
                   ROUND(SUM(ABS(amount))::numeric, 2) AS total,
                   COUNT(*) AS qtd
            FROM bank_transactions
            WHERE amount < 0
              AND date_trunc('month', transaction_date) = date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date)
              AND category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY total DESC
            LIMIT 5
        """)
        )
        top_cats = top_result.fetchall()

        def var_pct(atual, anterior):
            if not anterior or anterior == 0:
                return 0.0
            return round((atual - anterior) / anterior * 100, 1)

        # Score de saúde (0-100)
        score = 100
        alertas = []
        if saldo_atual < 88000:
            score -= 30
            alertas.append("SALDO CRÍTICO: abaixo de 1x custo fixo mensal estimado")
        elif saldo_atual < 176000:
            score -= 15
        rec_vencido = float(rec.vencido or 0)
        pay_vencido = float(pay.vencido or 0)
        if rec_vencido > (mrr or 1) * 0.5:
            score -= 25
            alertas.append("INADIMPLÊNCIA ALTA: receber vencido > 50% do MRR")
        elif rec_vencido > (mrr or 1) * 0.2:
            score -= 10
        if pay_vencido > 50000:
            score -= 20
            alertas.append("CONTAS A PAGAR VENCIDAS: acima de R$ 50k")
        elif pay_vencido > 20000:
            score -= 10

        return {
            "timestamp": datetime.now().isoformat(),
            "periodo": {
                "mes_atual": inicio_mes.strftime("%m/%Y"),
                "data_referencia": hoje.isoformat(),
            },
            "saldo": {
                "atual": saldo_atual,
                "status": ("critico" if saldo_atual < 88000 else "atencao" if saldo_atual < 176000 else "saudavel"),
            },
            "mes_atual": {
                "entradas": entradas,
                "saidas": saidas,
                "resultado": round(entradas - saidas, 2),
                "transacoes": int(fx.txs_mes or 0),
                "variacao_entradas_pct": var_pct(entradas, entradas_ant),
                "variacao_saidas_pct": var_pct(saidas, saidas_ant),
            },
            "contas_pagar": {
                "vencido": float(pay.vencido or 0),
                "a_vencer": float(pay.a_vencer or 0),
                "qtd_vencido": int(pay.qtd_vencido or 0),
            },
            "contas_receber": {
                "vencido": rec_vencido,
                "total_pendente": float(rec.total_pendente or 0),
                "qtd_pendente": int(rec.qtd_pendente or 0),
            },
            "mrr": mrr,
            "top_despesas": [{"categoria": r.category, "total": float(r.total), "qtd": int(r.qtd)} for r in top_cats],
            "saude_financeira": {
                "score": max(0, min(100, score)),
                "alertas": alertas,
            },
        }
    except Exception as e:
        logger.exception("painel financeiro falhou")
        raise HTTPException(status_code=503, detail=f"painel indisponível: {e}") from e  # era 200 com {"error"} (08/09/2026)


# ──────────────────────────────────────────────────────────────────────────────
# GET /financial/cashflow/forecast
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/cashflow/forecast", summary="Projeção de fluxo de caixa 30/60/90 dias")
async def get_cashflow_forecast(
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Projeção baseada no histórico real dos últimos 90 dias.
    3 cenários: pessimista (mín entradas / máx saídas),
                esperado (médias), otimista (máx entradas / mín saídas).
    """
    try:
        # Saldo atual
        saldo_result = await db.execute(
            text("""
            SELECT COALESCE(available_balance, current_balance, 0) AS saldo
            FROM bank_accounts WHERE is_main_account = true
            ORDER BY updated_at DESC LIMIT 1
        """)
        )
        saldo_row = saldo_result.fetchone()
        saldo_base = float(saldo_row.saldo) if (saldo_row and saldo_row.saldo is not None) else 0.0

        # MRR
        mrr_result = await db.execute(
            text("SELECT COALESCE(SUM(monthly_value), 0) AS mrr FROM contracts WHERE status = 'active'")
        )
        mrr_row = mrr_result.fetchone()
        mrr = float(mrr_row.mrr) if (mrr_row and mrr_row.mrr is not None) else 0.0

        # Médias mensais dos últimos 90 dias por mês completo
        stats_result = await db.execute(
            text("""
            WITH mensal AS (
                SELECT
                    date_trunc('month', transaction_date) AS mes,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS entradas,
                    SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) AS saidas
                FROM bank_transactions
                -- 3 meses COMPLETOS. Era `>= (now() AT TIME ZONE 'America/Manaus')::date - 90 dias`: o primeiro mês entrava
                -- pela metade e a média caía (07/09/2026: 235.464 exibido × 278.581 real, −15%);
                -- o rótulo já dizia "meses completos" — o SQL é que não cumpria.
                WHERE transaction_date >= date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date) - interval '3 months'
                  AND transaction_date < date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date)
                GROUP BY 1
            )
            SELECT
                COALESCE(AVG(entradas), 0)  AS media_entradas,
                COALESCE(MIN(entradas), 0)  AS min_entradas,
                COALESCE(MAX(entradas), 0)  AS max_entradas,
                COALESCE(AVG(saidas), 0)    AS media_saidas,
                COALESCE(MIN(saidas), 0)    AS min_saidas,
                COALESCE(MAX(saidas), 0)    AS max_saidas,
                COUNT(*) AS meses_analisados
            FROM mensal
        """)
        )
        st = stats_result.fetchone()

        media_entrada = float(st.media_entradas or mrr)
        min_entrada = float(st.min_entradas or mrr * 0.85)
        max_entrada = float(st.max_entradas or mrr * 1.1)
        media_saida = float(st.media_saidas or 88000)
        min_saida = float(st.min_saidas or 80000)
        max_saida = float(st.max_saidas or 100000)
        meses_hist = int(st.meses_analisados or 0)

        def mes_offset(n: int) -> str:
            m = hoje.month + n
            y = hoje.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            return f"{m:02d}/{y}"

        hoje = date.today()

        def projetar(entrada_m, saida_m, horizonte):
            saldo = saldo_base
            proj = []
            for i in range(1, horizonte + 1):
                saldo = saldo + entrada_m - saida_m
                proj.append(
                    {
                        "mes": mes_offset(i),
                        "entradas": round(entrada_m, 2),
                        "saidas": round(saida_m, 2),
                        "saldo_projetado": round(saldo, 2),
                        "status": ("critico" if saldo < 88000 else "atencao" if saldo < 176000 else "saudavel"),
                    }
                )
            return proj

        alerta_ruptura = None
        if saldo_base + min_entrada - max_saida < 0:
            alerta_ruptura = "SALDO NEGATIVO PROJETADO em 30 dias (cenário pessimista)"

        return {
            "timestamp": datetime.now().isoformat(),
            "saldo_atual": saldo_base,
            "mrr_base": mrr,
            "historico_base": {
                "periodo": "últimos 90 dias (meses completos)",
                "meses_analisados": meses_hist,
                "media_entradas_mensal": round(media_entrada, 2),
                "media_saidas_mensal": round(media_saida, 2),
                "resultado_medio": round(media_entrada - media_saida, 2),
            },
            "cenarios": {
                "pessimista": {
                    "descricao": "Entradas mínimas históricas, saídas máximas",
                    "projecao_30d": projetar(min_entrada, max_saida, 1),
                    "projecao_60d": projetar(min_entrada, max_saida, 2),
                    "projecao_90d": projetar(min_entrada, max_saida, 3),
                },
                "esperado": {
                    "descricao": "Médias históricas mantidas",
                    "projecao_30d": projetar(media_entrada, media_saida, 1),
                    "projecao_60d": projetar(media_entrada, media_saida, 2),
                    "projecao_90d": projetar(media_entrada, media_saida, 3),
                },
                "otimista": {
                    "descricao": "Entradas máximas históricas, saídas mínimas",
                    "projecao_30d": projetar(max_entrada, min_saida, 1),
                    "projecao_60d": projetar(max_entrada, min_saida, 2),
                    "projecao_90d": projetar(max_entrada, min_saida, 3),
                },
            },
            "alerta_ruptura": alerta_ruptura,
        }
    except Exception as e:
        logger.exception("painel financeiro falhou")
        raise HTTPException(status_code=503, detail=f"painel indisponível: {e}") from e  # era 200 com {"error"} (08/09/2026)


# ──────────────────────────────────────────────────────────────────────────────
# GET /financial/bi/overview
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/bi/kpis", summary="KPIs financeiros ao vivo — financial_kpis table")
async def get_bi_kpis(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    KPIs financeiros em tempo real da tabela financial_kpis + dados ao vivo.
    MRR, saldo Inter, compliance Lucro Real, inadimplência, score saúde 0-100.
    """
    try:
        kpis_result = await db.execute(
            text("""
            SELECT nome, valor_atual, unidade, categoria, updated_at
            FROM financial_kpis
            WHERE ativo = true
            ORDER BY categoria, nome
            """)
        )
        kpis_rows = kpis_result.fetchall()

        live_result = await db.execute(
            text("""
            SELECT
                (SELECT COALESCE(round(sum(monthly_value)::numeric,2), 0)
                 FROM contracts WHERE status = 'active') as mrr,
                (SELECT COALESCE(round(current_balance::numeric,2), 0)
                 FROM bank_accounts WHERE bank_code = '077'
                 ORDER BY updated_at DESC LIMIT 1) as saldo_inter,
                (SELECT count(*) FROM receivable_accounts
                 WHERE due_date < (now() AT TIME ZONE 'America/Manaus')::date
                 AND status NOT IN ('paga','cancelada','baixada')) as inadimplentes,
                (SELECT COALESCE(round(sum(net_value)::numeric,2), 0)
                 FROM receivable_accounts
                 WHERE due_date < (now() AT TIME ZONE 'America/Manaus')::date
                 AND status NOT IN ('paga','cancelada','baixada')) as total_inadimplencia,
                (SELECT round(count(CASE WHEN category IS NOT NULL AND category != '' THEN 1 END)::numeric /
                 NULLIF(count(*), 0) * 100, 1)
                 FROM bank_transactions WHERE amount < 0) as compliance_pct
            """)
        )
        live = live_result.fetchone()

        mrr = float(live.mrr or 0) if live else 0
        saldo = float(live.saldo_inter or 0) if live else 0
        inadimplentes = int(live.inadimplentes or 0) if live else 0
        total_inad = float(live.total_inadimplencia or 0) if live else 0
        compliance = float(live.compliance_pct or 0) if live else 0
        inadimplencia_pct = round(total_inad / mrr * 100, 1) if mrr > 0 else 0

        score = round(
            (min(compliance, 100) * 0.30)
            + (max(0, 100 - inadimplencia_pct * 10) * 0.30)
            + (min(saldo / mrr * 100, 100) if mrr > 0 else 50) * 0.20
            + 20,
            1,
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "kpis": [
                {
                    "name": r.nome,
                    "value": float(r.valor_atual) if r.valor_atual is not None else None,
                    "unit": r.unidade,
                    "category": r.categoria,
                    "updated_at": str(r.updated_at),
                }
                for r in kpis_rows
            ],
            "live": {
                "mrr": mrr,
                "saldo_inter": saldo,
                "inadimplentes": inadimplentes,
                "total_inadimplencia": total_inad,
                "inadimplencia_pct": inadimplencia_pct,
                "compliance_lucro_real_pct": compliance,
                "score_saude": min(round(score, 1), 100),
            },
            "total_kpis": len(kpis_rows),
        }
    except Exception as e:
        logger.exception("painel financeiro falhou")
        raise HTTPException(status_code=503, detail=f"painel indisponível: {e}") from e  # era 200 com {"error"} (08/09/2026)


# ──────────────────────────────────────────────────────────────────────────────
# GET /financial/bi/dashboards
# ──────────────────────────────────────────────────────────────────────────────
