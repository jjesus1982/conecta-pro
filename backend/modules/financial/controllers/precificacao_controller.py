"""
Precificação Controller — Conecta PRO
Framework CCT SINDECOMPRESTS 2026 + benchmarks Manaus/AM.
Simulador de preço ideal + análise dos contratos ativos subprecificados.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session as get_db

router = APIRouter(prefix="/financial/precificacao", tags=["Precificação"])

# ── CCT SINDECOMPRESTS 2026 (agentes de portaria/serviços, NÃO vigilância) ──
# Fonte única do piso: tabela cct_cargos (piso da categoria R$1.670).
PISO_CATEGORIA = 1670.00  # menor piso de cct_cargos (fallback)
from modules.financial.services.encargos import ENCARGOS_PCT, encargo_pct  # noqa: F401 (ponto único por regime)
REPASSE_PCT = 0.075  # repasse contratual obrigatório CCT Cláusula 2ª §3º
VR_DIA = 22.00
DIAS_UTEIS = 22
VT_MEDIO = 150.0

# Posto de mão de obra (portaria/limpeza) = Conecta Patrimonial (Simples Anexo III).
# Seg. eletrônica/CFTV/remota = Conecta Eletrônica (Lucro Real).
_TIPOS_MAO_DE_OBRA = {"portaria", "portaria_presencial", "portaria_noturno", "limpeza", "facilities"}


def _regime_do_tipo(tipo: str) -> str:
    return "simples_nacional" if (tipo or "").lower() in _TIPOS_MAO_DE_OBRA else "lucro_real"


# Custo all-in por posto CLT (portaria/limpeza = Patrimonial/Simples) × (1 + repasse 7,5%)
CUSTO_CLT_POSTO = (
    PISO_CATEGORIA * (1 + encargo_pct("simples_nacional")) + VR_DIA * DIAS_UTEIS + VT_MEDIO
) * (1 + REPASSE_PCT)

# ── Benchmarks Manaus 2026 (por posto/mês) ───────────────────────────────────
BENCH = {
    "portaria_presencial": {"min": 2800, "max": 3800, "label": "Portaria Presencial"},
    "portaria": {"min": 2800, "max": 3800, "label": "Portaria Presencial"},  # alias retroativo
    "portaria_noturno": {"min": 3200, "max": 4500, "label": "Portaria Presencial Noturna"},
    "portaria_remota": {"min": 1200, "max": 2500, "label": "Portaria Remota (Econdos)"},
    "manutencao_cftv": {"min": 600, "max": 1200, "label": "Manutenção CFTV"},
    "seguranca_eletronica": {"min": 1500, "max": 3500, "label": "Seg. Eletrônica + Monitoramento"},
    "limpeza": {"min": 1500, "max": 3000, "label": "Limpeza e Conservação"},
    "facilities": {"min": 1500, "max": 3000, "label": "Facilities e Serviços Gerais"},
}

MARGEM_TARGET = 35.0
MARGEM_MINIMA = 20.0


def _detectar_tipo(nome: str) -> str:
    n = nome.lower()
    if "remota" in n:
        return "portaria_remota"
    if "cftv" in n and "manut" in n:
        return "manutencao_cftv"
    if "cftv" in n or "seg. eletr" in n or "eletr" in n:
        return "seguranca_eletronica"
    if "portaria" in n:
        return "portaria_presencial"
    if "limpeza" in n:
        return "limpeza"
    return "outros"


def _custo_direto_por_tipo(tipo: str, receita: float) -> float:
    if tipo in ("portaria", "limpeza"):
        postos = max(1, round(receita / CUSTO_CLT_POSTO))
        return CUSTO_CLT_POSTO * postos
    elif tipo == "portaria_remota":
        return 3270.0  # Econdos R$1.770 + operador R$1.500
    elif tipo in ("seguranca_eletronica", "manutencao_cftv"):
        return receita * 0.35
    return receita * 0.75


@router.get("/simulador", summary="Simulador de precificação CCT 2026")
async def get_simulador(
    tipo_servico: str = Query(
        "portaria",
        description="portaria_presencial | portaria_remota | manutencao_cftv | seguranca_eletronica | facilities",
    ),
    num_postos: int = Query(1, description="Número de postos / unidades"),
    turno_noturno: bool = Query(False, description="Adicional noturno +20% (CCT 2026)"),
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Simula o preço ideal para um novo contrato.
    Base: CCT SINDECOMPRESTS 2026 + benchmarks do mercado Manaus/AM.
    """
    try:
        # Retrocompatibilidade: kit_mensal → portaria_presencial
        TIPO_ALIAS = {"kit_mensal": "portaria_presencial", "portaria": "portaria_presencial"}
        tipo_servico = TIPO_ALIAS.get(tipo_servico, tipo_servico)

        # Piso lido da fonte única (cct_cargos); fallback = PISO_CATEGORIA
        piso_row = await db.execute(
            text("SELECT MIN(piso_salarial) FROM cct_cargos WHERE is_active")
        )
        piso_db = piso_row.scalar()
        piso = float(piso_db) if piso_db else PISO_CATEGORIA

        sal_base = piso * (1.20 if turno_noturno else 1.0)
        encargos = sal_base * encargo_pct(_regime_do_tipo(tipo_servico))
        vr_mensal = VR_DIA * DIAS_UTEIS
        # Repasse contratual obrigatório 7,5% (CCT Cláusula 2ª §3º) sobre o custo
        custo_sem_repasse = sal_base + encargos + vr_mensal + VT_MEDIO
        repasse = custo_sem_repasse * REPASSE_PCT
        custo_posto = custo_sem_repasse + repasse

        # Custo direto total
        if tipo_servico in ("portaria_presencial", "portaria", "limpeza", "facilities"):
            custo_direto = custo_posto * num_postos
        elif tipo_servico == "portaria_remota":
            custo_direto = 1770.0 + 1500.0 * num_postos
        elif tipo_servico in ("manutencao_cftv", "seguranca_eletronica"):
            custo_direto = 700.0 * num_postos
        else:
            custo_direto = custo_posto * num_postos

        overhead = custo_direto * 0.15
        custo_total = custo_direto + overhead

        preco_minimo = round(custo_total / (1 - MARGEM_MINIMA / 100), 2)
        preco_ideal = round(custo_total / (1 - MARGEM_TARGET / 100), 2)

        bench_key = "portaria_noturno" if turno_noturno and tipo_servico == "portaria" else tipo_servico
        bench = BENCH.get(bench_key, BENCH.get("portaria", {"min": 2800, "max": 3800, "label": tipo_servico}))
        bench_min = bench["min"] * num_postos
        bench_max = bench["max"] * num_postos

        posicionamento = (
            "abaixo_mercado" if preco_ideal < bench_min else "premium" if preco_ideal > bench_max else "adequado"
        )

        # Contratos similares ativos
        sim_q = await db.execute(
            text("""
            SELECT name, COALESCE(base_value, 0) AS ticket
            FROM billing_rules
            WHERE ativo = true
              AND LOWER(name) LIKE :pattern
            ORDER BY base_value DESC
            LIMIT 5
        """),
            {"pattern": f"%{tipo_servico.split('_')[0].lower()[:7]}%"},
        )
        similares = sim_q.fetchall()

        return {
            "timestamp": datetime.now().isoformat(),
            "input": {
                "tipo_servico": tipo_servico,
                "num_postos": num_postos,
                "turno_noturno": turno_noturno,
                "cct_2026": True,
            },
            "custo_clt_cct2026": {
                "salario_base": round(sal_base, 2),
                "encargos_61pct": round(encargos, 2),
                "vr_mensal": round(vr_mensal, 2),
                "vt_medio": VT_MEDIO,
                "repasse_75pct": round(repasse, 2),
                "custo_total_por_posto": round(custo_posto, 2),
            },
            "custo_direto_total": round(custo_direto, 2),
            "precos_recomendados": {
                "preco_minimo": preco_minimo,
                "preco_ideal_35pct": preco_ideal,
                "preco_mercado_min": bench_min,
                "preco_mercado_max": bench_max,
                "preco_mercado_medio": round((bench_min + bench_max) / 2, 2),
            },
            "margens_no_preco_ideal": {
                "mc_pct": MARGEM_TARGET,
                "mc_valor": round(preco_ideal - custo_direto, 2),
            },
            "posicionamento_mercado": posicionamento,
            "recomendacao": (
                f"Preço ideal R${preco_ideal:,.2f} está abaixo do mínimo de mercado — aceitar com cautela"
                if posicionamento == "abaixo_mercado"
                else f"Preço ideal R${preco_ideal:,.2f} acima do mercado — justificar com diferencial Conecta PRO"
                if posicionamento == "premium"
                else f"Preço ideal R${preco_ideal:,.2f} dentro do mercado Manaus ({bench['label']})"
            ),
            "alertas": [
                "⚠️  Contrato sem cláusula de reajuste anual = margem negativa após CCT",
                *(["⚠️  Adicional noturno: confirmar cláusula no contrato"] if turno_noturno else []),
            ],
            "contratos_similares_ativos": [{"nome": s.name[:50], "ticket_atual": float(s.ticket)} for s in similares],
        }

    except Exception as exc:
        import traceback

        return {"error": str(exc), "detail": traceback.format_exc()[-600:]}


@router.get("/contratos/analise", summary="Análise de precificação dos contratos ativos")
async def get_analise_contratos(
    condominio_id: uuid.UUID | None = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analisa todos os contratos ativos: estão dentro ou abaixo do mercado Manaus?
    Identifica subprecificados e calcula potencial de reajuste.
    """
    try:
        result = await db.execute(
            text("""
            SELECT name, COALESCE(base_value, 0) AS ticket, start_date
            FROM billing_rules
            WHERE ativo = true
            ORDER BY base_value DESC
        """)
        )
        contratos = result.fetchall()

        analise = []
        subprecificados = []

        for c in contratos:
            ticket = float(c.ticket)
            tipo = _detectar_tipo(c.name)
            bench = BENCH.get(tipo, {"min": ticket * 0.9, "max": ticket * 1.1, "label": tipo})

            # Inferir número de postos pelo ticket (portaria ~R$3.300/posto)
            if tipo in ("portaria", "limpeza"):
                postos_est = max(1, round(ticket / CUSTO_CLT_POSTO))
                bench_min_c = bench["min"] * postos_est
                bench_max_c = bench["max"] * postos_est
                custo_est = CUSTO_CLT_POSTO * postos_est
            else:
                postos_est = 1
                bench_min_c = bench["min"]
                bench_max_c = bench["max"]
                custo_est = _custo_direto_por_tipo(tipo, ticket)

            mc = ticket - custo_est
            mc_pct = round(mc / ticket * 100, 1) if ticket > 0 else 0

            status = (
                "subprecificado"
                if ticket < bench_min_c or mc_pct < 15
                else "adequado"
                if mc_pct >= MARGEM_MINIMA
                else "atencao"
            )

            potencial = round(max(0.0, bench_min_c * 1.05 - ticket), 2) if status == "subprecificado" else 0.0

            entry = {
                "nome": c.name[:60],
                "tipo": tipo,
                "ticket_atual": ticket,
                "custo_estimado": round(custo_est, 2),
                "mc_pct": mc_pct,
                "benchmark_minimo": bench_min_c,
                "benchmark_maximo": bench_max_c,
                "postos_estimados": postos_est,
                "status_preco": status,
                "potencial_reajuste": potencial,
                "recomendacao": (
                    f"Renegociar: R${ticket:,.2f} abaixo do mínimo R${bench_min_c:,.2f}"
                    if status == "subprecificado"
                    else "Monitorar — margem aceitável"
                    if status == "atencao"
                    else "OK — precificação adequada"
                ),
            }
            analise.append(entry)
            if status == "subprecificado":
                subprecificados.append(entry)

        potencial_total = sum(c["potencial_reajuste"] for c in subprecificados)

        return {
            "timestamp": datetime.now().isoformat(),
            "total_contratos": len(analise),
            "contratos_subprecificados": len(subprecificados),
            "potencial_reajuste_mensal": round(potencial_total, 2),
            "potencial_reajuste_anual": round(potencial_total * 12, 2),
            "contratos": analise,
            "alertas": (
                [f"⚠️  {len(subprecificados)} contrato(s) subprecificado(s) — potencial +R${potencial_total:,.2f}/mês"]
                if subprecificados
                else ["✅ Todos os contratos dentro do mercado Manaus"]
            ),
            "nota_cct": "Custo estimado CCT SINDECOMPRESTS 2026 — validar com folha real",
        }

    except Exception as exc:
        import traceback

        return {"error": str(exc), "detail": traceback.format_exc()[-600:]}
