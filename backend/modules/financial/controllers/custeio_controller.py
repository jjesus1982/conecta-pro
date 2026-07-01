"""
Custeio Controller — Conecta PRO
Custeio ABC por tipo de serviço usando dados reais de billing_rules + bank_transactions.
CCT SINDECOMPRESTS 2026 (agentes de portaria/serviços, NÃO vigilância):
piso R$1.670 + encargos ≈61,24% + VR R$22/dia + VT + repasse 7,5% = custo all-in/posto.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session as get_db

router = APIRouter(prefix="/financial/custeio", tags=["Custeio ABC"])

# CCT SINDECOMPRESTS 2026 (agentes de portaria/serviços, NÃO vigilância)
PISO_CATEGORIA = 1670.00  # menor piso de cct_cargos
ENCARGOS_PCT = 0.6124  # INSS 20 + FGTS 8 + RAT 3 + terceiros 5,8 + férias 11,11 + 13º 8,33 + rescisão 5
VR_DIA = 22.00
DIAS_UTEIS = 22
VT_MEDIO = 150.0
REPASSE_PCT = 0.075  # repasse contratual obrigatório CCT Cláusula 2ª §3º
# Custo all-in/posto = (salário + encargos + VR + VT) × (1 + repasse 7,5%)
CUSTO_CLT_POSTO = (
    PISO_CATEGORIA * (1 + ENCARGOS_PCT) + VR_DIA * DIAS_UTEIS + VT_MEDIO
) * (1 + REPASSE_PCT)
MARGEM_TARGET = 35.0
MARGEM_MINIMA = 20.0


def _detectar_tipo(nome: str) -> str:
    """Extrai tipo de serviço pelo nome da regra de cobrança."""
    n = nome.lower()
    if "remota" in n:
        return "portaria_remota"
    if "cftv" in n and "manut" in n:
        return "manutencao_cftv"
    if "cftv" in n or "seg. eletr" in n or "eletr" in n:
        return "seguranca_eletronica"
    if "portaria" in n:
        return "portaria"
    if "limpeza" in n:
        return "limpeza"
    if "jard" in n:
        return "jardinagem"
    return "outros"


@router.get("/abc", summary="Custeio ABC por tipo de serviço (dados reais)")
async def get_custeio_abc(
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Custeio ABC: distribui custos reais (bank_transactions) entre os tipos
    de serviço detectados nos billing_rules ativos.
    Base: última data de transações disponível.
    """
    try:
        # 1. Contratos ativos + valor
        contratos_q = await db.execute(
            text("""
            SELECT name, COALESCE(base_value, 0) AS receita
            FROM billing_rules
            WHERE ativo = true
            ORDER BY base_value DESC
        """)
        )
        contratos = contratos_q.fetchall()

        mrr_total = sum(float(r.receita) for r in contratos)

        # Agrupar por tipo
        tipo_dados: dict[str, dict] = {}
        for c in contratos:
            tipo = _detectar_tipo(c.name)
            if tipo not in tipo_dados:
                tipo_dados[tipo] = {"receita": 0.0, "contratos": 0, "nomes": []}
            tipo_dados[tipo]["receita"] += float(c.receita)
            tipo_dados[tipo]["contratos"] += 1
            tipo_dados[tipo]["nomes"].append(c.name)

        # 2. Custos reais por categoria (mês mais recente disponível)
        custos_q = await db.execute(
            text("""
            SELECT
                category,
                ROUND(SUM(ABS(amount))::numeric, 2) AS total,
                COUNT(*) AS qtd,
                MAX(transaction_date) AS ultima_data,
                date_trunc('month', MAX(transaction_date)) AS mes_ref
            FROM bank_transactions
            WHERE amount < 0
              AND category IS NOT NULL
              AND category != ''
              AND category != 'receita'
            GROUP BY category
            ORDER BY total DESC
        """)
        )
        custos = custos_q.fetchall()

        custo_total_global = sum(float(c.total) for c in custos)
        custo_folha = next((float(c.total) for c in custos if c.category == "folha_pagamento"), 0)
        custo_fornec = next((float(c.total) for c in custos if c.category == "fornecedores"), 0)
        custo_impostos = next((float(c.total) for c in custos if c.category == "impostos"), 0)
        custo_operac = next((float(c.total) for c in custos if c.category == "operacional"), 0)
        custo_pessoal = next((float(c.total) for c in custos if c.category in ("pro_labore", "pessoal_admin")), 0)
        mes_ref = str(custos[0].ultima_data)[:7] if custos else "N/D"

        # 3. ABC: alocar custos por tipo (proporcional à receita + diretos)
        analise = []
        for tipo, dados in sorted(tipo_dados.items(), key=lambda x: -x[1]["receita"]):
            receita = dados["receita"]
            pct_mrr = receita / mrr_total if mrr_total > 0 else 0

            # Custo direto por tipo
            if tipo in ("portaria", "limpeza", "jardinagem"):
                # Mão de obra direta: folha proporcional à receita
                custo_direto = custo_folha * pct_mrr + custo_fornec * 0.2 * pct_mrr
            elif tipo == "portaria_remota":
                # Econdos (~R$1.770/mês) + operador parcial
                custo_direto = 1770.0 + 1500.0 * pct_mrr
            elif tipo in ("seguranca_eletronica", "manutencao_cftv"):
                # Equipamentos/peças: ~35% da receita + overhead menor
                custo_direto = receita * 0.35
            else:
                custo_direto = custo_total_global * pct_mrr

            # Overhead: impostos + operacional + pró-labore rateados
            overhead = (custo_impostos + custo_operac + custo_pessoal) * pct_mrr

            custo_total_tipo = custo_direto + overhead
            mc_valor = receita - custo_direto
            mc_pct = round(mc_valor / receita * 100, 1) if receita > 0 else 0
            ml_valor = receita - custo_total_tipo
            ml_pct = round(ml_valor / receita * 100, 1) if receita > 0 else 0

            classificacao = (
                "estrela" if mc_pct >= MARGEM_TARGET else "atencao" if mc_pct >= MARGEM_MINIMA else "abacaxi"
            )

            analise.append(
                {
                    "tipo": tipo,
                    "label": tipo.replace("_", " ").title(),
                    "contratos": dados["contratos"],
                    "receita_mensal": round(receita, 2),
                    "pct_mrr": round(pct_mrr * 100, 1),
                    "custeio": {
                        "custo_direto": round(custo_direto, 2),
                        "overhead_rateado": round(overhead, 2),
                        "custo_total": round(custo_total_tipo, 2),
                    },
                    "margens": {
                        "mc_valor": round(mc_valor, 2),
                        "mc_pct": mc_pct,
                        "margem_liquida_valor": round(ml_valor, 2),
                        "margem_liquida_pct": ml_pct,
                        "meta_mc_pct": MARGEM_TARGET,
                        "gap_meta": round(MARGEM_TARGET - mc_pct, 1),
                        # campo mapeado para frontend custeio/page.tsx
                        "margem": mc_pct,
                        "custo_medio": round(custo_direto / dados["contratos"], 2),
                        "cor": _cor_tipo(tipo),
                    },
                    "classificacao": classificacao,
                    "recomendacao": (
                        "Escalar — maior margem"
                        if classificacao == "estrela"
                        else "Monitorar — margem aceitável"
                        if classificacao == "atencao"
                        else f"Renegociar — MC {mc_pct}% abaixo do mínimo {MARGEM_MINIMA}%"
                    ),
                    "fonte": "banco_real",
                }
            )

        return {
            "timestamp": datetime.now().isoformat(),
            "periodo_referencia": mes_ref,
            "mrr_total": round(mrr_total, 2),
            "custo_total_mes": round(custo_total_global, 2),
            "resultado_estimado": round(mrr_total - custo_total_global, 2),
            "margem_global_pct": round((mrr_total - custo_total_global) / mrr_total * 100, 1) if mrr_total > 0 else 0,
            "cct_2026": {
                "piso_base_cct": PISO_CATEGORIA,
                "custo_all_in_posto": round(CUSTO_CLT_POSTO, 2),
                "encargos_pct": round(ENCARGOS_PCT * 100, 2),
                "repasse_pct": round(REPASSE_PCT * 100, 2),
            },
            "custo_por_categoria": [
                {"categoria": c.category, "total": float(c.total), "qtd": int(c.qtd)} for c in custos
            ],
            "analise_por_tipo": analise,
            "alertas": [a["recomendacao"] for a in analise if a["classificacao"] == "abacaxi"],
        }

    except Exception as exc:
        import traceback

        return {"error": str(exc), "detail": traceback.format_exc()[-600:]}


@router.get("/contratos", summary="Custeio por contrato individual")
async def get_custeio_contratos(
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Margem estimada por contrato com base em CCT 2026 e tipo de serviço detectado."""
    try:
        result = await db.execute(
            text("""
            SELECT
                name,
                COALESCE(base_value, 0) AS receita,
                status, start_date
            FROM billing_rules
            WHERE ativo = true
            ORDER BY base_value DESC
        """)
        )
        contratos = result.fetchall()

        analise = []
        for c in contratos:
            receita = float(c.receita)
            tipo = _detectar_tipo(c.name)

            if tipo in ("portaria", "limpeza", "jardinagem"):
                # Estimar nº de postos pelo ticket (portaria ~R$3.300/posto)
                postos_est = max(1, round(receita / CUSTO_CLT_POSTO))
                custo_direto = CUSTO_CLT_POSTO * postos_est
            elif tipo == "portaria_remota":
                custo_direto = 3270.0
            elif tipo in ("seguranca_eletronica", "manutencao_cftv"):
                custo_direto = receita * 0.35
            else:
                custo_direto = receita * 0.75

            mc = receita - custo_direto
            mc_pct = round(mc / receita * 100, 1) if receita > 0 else 0
            status = "ok" if mc_pct >= MARGEM_TARGET else "atencao" if mc_pct >= MARGEM_MINIMA else "critico"

            analise.append(
                {
                    "nome": c.name,
                    "tipo": tipo,
                    "receita_mensal": receita,
                    "custo_estimado": round(custo_direto, 2),
                    "mc_valor": round(mc, 2),
                    "mc_pct": mc_pct,
                    "status": status,
                }
            )

        return {
            "timestamp": datetime.now().isoformat(),
            "total_contratos": len(analise),
            "contratos": analise,
            "nota": "Custo estimado CCT SINDECOMPRESTS 2026 — validar com folha real",
        }
    except Exception as exc:
        import traceback

        return {"error": str(exc), "detail": traceback.format_exc()[-600:]}


def _cor_tipo(tipo: str) -> str:
    return {
        "portaria": "#3B82F6",
        "limpeza": "#10B981",
        "jardinagem": "#84CC16",
        "seguranca_eletronica": "#F59E0B",
        "portaria_remota": "#8B5CF6",
        "manutencao_cftv": "#EF4444",
        "outros": "#6B7280",
    }.get(tipo, "#6B7280")
