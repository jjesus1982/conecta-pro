"""Fase 5.2a.4 — QUICK-WINS EXECUTIVOS (read-heavy, cross-domínio) com groundedness + auditoria.

Superfície `/consultores/mcp/executivo/*` que o conector MCP chama. São 4 endpoints
que ORQUESTRAM os panoramas reais já existentes (CFO/COO/CMO/folha) — NÃO reconstroem
lógica de negócio, só cruzam e sintetizam:

  POST /viabilidade-contratacao  — flagship "posso contratar N porteiros?" (CFO+COO+folha)
  GET  /briefing                  — 1-card executivo (caixa, postos descobertos, certidões, deals)
  GET  /runway                    — saldo Inter vivo ÷ folha mensal = meses (corrige KPI cache velho)
  GET  /margem-condominio         — receita por contrato − folha alocada (best-effort, proveniência)

DOUTRINA INEGOCIÁVEL (Conecta PRO):
- SÓ LEITURA. Nenhum endpoint aqui move dinheiro, escreve estado de negócio ou altera escala.
- NUNCA fabricar dado: cada número carrega sua PROVENIÊNCIA (origem real). É o ponto do 5.2a.
- Toda síntese textual passa por `groundedness.verificar(sintese, fonte)`; se um número não
  tiver lastro na fonte real, a síntese suspeita é DESCARTADA e substituída pela versão
  determinística (montada só com os números reais) + disclaimer. Nunca entregamos número
  fabricado ao gestor.
- Cada chamada grava 1 linha append-only em `audit_logs` (agent_audit.registrar_acao_agente).

O router é montado em main_production.py sob o mesmo gate MCP dos consultores (conta de
serviço do conector + diretoria) — `_MCP_CONSULTOR_GATE`.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.ai.conversation.services.garantia import agent_audit, groundedness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consultores/mcp/executivo", tags=["Consultores MCP — Executivo"])

_DISCLAIMER = "Síntese executiva gerada por IA — números com proveniência; confira antes de decidir."

# Piso CCT SINDECOMPRESTS 2026 (agentes de portaria) — usado como fallback quando o cargo
# não tem piso cadastrado em cct_cargos. Fonte: CCT AM000613/2025.
_PISO_CCT_FALLBACK = Decimal("1670.00")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de orquestração (reuso dos panoramas; nada de lógica de negócio nova)
# ─────────────────────────────────────────────────────────────────────────────
def _src(valor: Any, source: str) -> dict[str, Any]:
    """Embrulha um número com sua PROVENIÊNCIA. É o contrato de dado do 5.2a."""
    return {"valor": valor, "source": source}


def _fonte_robusta(fonte: dict[str, Any]) -> dict[str, Any]:
    """Enriquece a `fonte` com formas de 1 casa decimal (BR) dos floats reais, ANTES do
    groundedness. Motivo: um valor real como runway=0.4 é achatado pela garantia como '0,40'
    (2 casas), mas a IA costuma escrever '0,4' (1 casa) — numericamente igual, textualmente
    diferente, e o `_canon` da garantia não normaliza zeros à direita. Sem isso, um número
    REAL de 1 casa seria (falsamente) marcado suspeito e a síntese boa da IA seria descartada.
    Não altera a garantia (5.2a.3, intocada): só adiciona representações do MESMO dado real."""
    extras: list[str] = []
    for v in list(fonte.values()):
        if isinstance(v, float):
            extras.append(f"{v:.1f}".replace(".", ","))  # 0.4 -> "0,4"
    if extras:
        f = dict(fonte)
        f["_formas_1casa"] = extras
        return f
    return fonte


async def _cfo_panorama(db: AsyncSession) -> dict[str, Any]:
    from modules.financial import cfo_service

    return await cfo_service.panorama(db)


async def _coo_panorama(db: AsyncSession) -> dict[str, Any]:
    from modules.operacional.services import consultor_coo_service

    return await consultor_coo_service.panorama(db)


async def _piso_do_cargo(db: AsyncSession, cargo: str) -> tuple[Decimal, str]:
    """Piso salarial REAL do cargo (cct_cargos.piso_salarial). Fallback = piso CCT 2026."""
    try:
        row = (
            await db.execute(
                text(
                    "SELECT piso_salarial FROM cct_cargos "
                    "WHERE is_active = true AND lower(cargo_nome) = lower(:c) "
                    "ORDER BY updated_at DESC NULLS LAST LIMIT 1"
                ),
                {"c": cargo},
            )
        ).first()
        if row and row[0] is not None:
            return Decimal(str(row[0])), f"cct_cargos.piso_salarial (cargo '{cargo}')"
    except Exception as e:  # noqa: BLE001
        logger.debug("piso_do_cargo: %s", e)
    return _PISO_CCT_FALLBACK, "piso CCT SINDECOMPRESTS 2026 (fallback — cargo sem piso cadastrado)"


def _custo_folha_mensal(piso: Decimal, qtd: int) -> tuple[float, float, float, str]:
    """Custo de folha mensal de contratar `qtd` no `piso`, com encargos CCT.
    Reusa o PricingEngine (mesmos encargos da precificação) — labor_cost = salários + encargos.
    Retorna (custo_total, encargos_pct, base_salarios, source)."""
    from modules.crm.services.pricing_engine import PricingEngine, PricingInput

    inp = PricingInput(
        base_salary=piso, headcount=max(qtd, 0), contract_months=1,
        service_type="portaria", client_state="AM", margin_target=Decimal("0"),
    )
    costs = PricingEngine()._calculate_costs(inp)  # noqa: SLF001 — reuso interno do motor CCT
    return (
        float(costs["labor_cost"]),
        float(costs["cct_percent"]),
        float(costs["base_cost"]),
        "PricingEngine (piso × qtd × encargos CCT: INSS/FGTS/SAT/13º/férias/rescisão)",
    )


async def _sintetizar(
    db: AsyncSession, *, origem_evento: str, pergunta: str,
    fonte: dict[str, Any], contexto_llm: str, fallback: str,
) -> tuple[str, dict[str, Any]]:
    """Gera uma síntese curta ancorada em `fonte` (dict de números REAIS) e a submete
    ao groundedness. Se a IA fabricar um número (suspeito sem lastro), DESCARTA a síntese
    da IA e usa o `fallback` determinístico (montado só com números reais) + disclaimer.

    Grava 1 linha de auditoria (agent_audit) com o resultado do groundedness.
    Retorna (sintese_final, groundedness_info)."""
    fonte = _fonte_robusta(fonte)
    modelo, provider, tier = "n/a", "template", "leve"
    sintese = fallback
    llm_texto: str | None = None
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        system_prompt = (
            "Você é o consultor executivo (orquestrador) da Conecta PRO. Escreva UMA síntese "
            "objetiva (2-4 frases) para a diretoria decidir. Use APENAS os números do contexto "
            "abaixo — NUNCA invente valor, saldo ou custo. Se faltar dado, diga 'aguardando dado'.\n\n"
            f"=== NÚMEROS REAIS (fonte da verdade) ===\n{contexto_llm}"
        )
        # direct=True: NUNCA re-rotear pro Hermes (guard de re-entrância) — usa OpenAI direto.
        llm_texto, meta = await _hub.gerar(
            messages=[{"role": "user", "content": pergunta}],
            system_prompt=system_prompt, origem="executivo", direct=True,
            max_tokens=400, temperature=0.2,
        )
        llm_texto = (llm_texto or "").strip()
        modelo = str(meta.get("model") or "openai")
        provider = "openai"
        tier = "pesada"
    except Exception as e:  # noqa: BLE001 — LLM indisponível degrada pro template (grounded)
        logger.info("executivo: síntese LLM indisponível, usando template: %s", e)

    if llm_texto:
        g = groundedness.verificar(llm_texto, fonte)
        if g["ok"]:
            sintese = llm_texto
            g_ok = True
        else:
            # IA fabricou número(s) → descarta a síntese da IA, usa o determinístico grounded.
            logger.warning("executivo: groundedness reprovou síntese IA. suspeitos=%s", g["suspeitos"])
            sintese = (
                fallback + "\n\n[NOTA: uma síntese gerada por IA foi descartada por conter "
                f"número(s) sem lastro nos dados ({', '.join(g['suspeitos'])}); "
                "acima está a versão determinística, montada só com dados reais.]"
            )
            g_ok = False
        gnd = {"ok": g_ok, "suspeitos": g["suspeitos"], "verificado": True}
    else:
        # Sem IA: o template é grounded por construção (só números reais da fonte).
        gcheck = groundedness.verificar(sintese, fonte)
        gnd = {"ok": gcheck["ok"], "suspeitos": gcheck["suspeitos"], "verificado": True}

    # Auditoria append-only (best-effort — nunca derruba o endpoint de leitura)
    try:
        await agent_audit.registrar_acao_agente(
            db, origem="executivo", pergunta=pergunta, resposta=sintese,
            modelo=modelo, tier=tier, provider=provider, groundedness_ok=gnd["ok"],
            trace_id=origem_evento,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("executivo: falha ao auditar (%s): %s", origem_evento, e)

    return sintese, gnd


# ─────────────────────────────────────────────────────────────────────────────
# 1) FLAGSHIP — POST /viabilidade-contratacao
# ─────────────────────────────────────────────────────────────────────────────
class ViabilidadeIn(BaseModel):
    qtd: int = Field(..., ge=1, le=500, description="Quantidade a contratar")
    cargo: str = Field(..., min_length=2, max_length=80, description="Cargo (ex.: 'Agente de Portaria')")


@router.post("/viabilidade-contratacao")
async def viabilidade_contratacao(
    payload: ViabilidadeIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟢 READ — "posso contratar N do cargo X?": cruza CFO (saldo/runway) + COO (postos
    descobertos/demanda) + custo de folha (qtd × piso CCT + encargos). Dado real + proveniência."""
    qtd, cargo = payload.qtd, payload.cargo.strip()
    cfo = await _cfo_panorama(db)
    coo = await _coo_panorama(db)
    piso, piso_src = await _piso_do_cargo(db, cargo)
    custo_mensal, encargos_pct, base_sal, custo_src = _custo_folha_mensal(piso, qtd)

    saldo = float(cfo.get("saldo_banco") or 0.0)
    saldo_fonte = cfo.get("saldo_fonte") or "cadastro"
    folha_atual = float(cfo.get("folha_mensal") or 0.0)
    runway_atual = cfo.get("runway_meses")
    postos_desc = list((coo.get("cobertura") or {}).get("postos_descobertos") or [])
    qtd_postos_desc = len(postos_desc)

    folha_nova = folha_atual + custo_mensal
    runway_novo = round(saldo / folha_nova, 1) if folha_nova > 0 else None
    meses_cobertos_pelo_saldo = round(saldo / custo_mensal, 1) if custo_mensal > 0 else None

    dados = {
        "qtd_solicitada": _src(qtd, "parâmetro da consulta"),
        "cargo": _src(cargo, "parâmetro da consulta"),
        "piso_salarial": _src(float(piso), piso_src),
        "custo_folha_mensal_estimado": _src(custo_mensal, custo_src),
        "encargos_cct_pct": _src(encargos_pct, "PricingEngine.CCT_COMPONENTS"),
        "base_salarios_mensal": _src(base_sal, "piso × qtd (sem encargos)"),
        "saldo_disponivel": _src(saldo, saldo_fonte),
        "folha_mensal_atual": _src(folha_atual, "cfo_service.panorama (KPI FOLHA)"),
        "runway_atual_meses": _src(runway_atual, "cfo_service.panorama.runway_meses (saldo ÷ folha)"),
        "runway_apos_contratacao_meses": _src(runway_novo, "saldo ÷ (folha atual + custo novo)"),
        "meses_que_o_saldo_cobre_so_o_novo_custo": _src(meses_cobertos_pelo_saldo, "saldo ÷ custo novo"),
        "postos_descobertos_qtd": _src(qtd_postos_desc, "consultor_coo_service.panorama.cobertura"),
        "postos_descobertos": _src(postos_desc, "consultor_coo_service.panorama.cobertura"),
    }

    # Fonte p/ groundedness: só os números reais (achatados). Inclui qtd/postos.
    fonte = {
        "qtd": qtd, "piso": float(piso), "custo_folha_mensal_estimado": custo_mensal,
        "encargos_cct_pct": encargos_pct, "base_salarios": base_sal, "saldo": saldo,
        "folha_atual": folha_atual, "folha_nova": folha_nova,
        "runway_atual": runway_atual, "runway_novo": runway_novo,
        "meses_cobertos": meses_cobertos_pelo_saldo, "postos_descobertos_qtd": qtd_postos_desc,
    }

    # Fallback determinístico (grounded por construção — só números da fonte)
    fallback = (
        f"Contratar {qtd} {cargo} custa cerca de R$ {custo_mensal:,.2f}/mês "
        f"(piso R$ {float(piso):,.2f} + {encargos_pct:.0f}% de encargos CCT). "
        f"Saldo disponível R$ {saldo:,.2f}; folha mensal atual R$ {folha_atual:,.2f}"
        + (f"; o runway iria de {runway_atual} para {runway_novo} meses" if runway_novo is not None and runway_atual is not None else "")
        + f". Postos descobertos hoje: {qtd_postos_desc}"
        + (f" ({', '.join(postos_desc[:5])})" if postos_desc else "")
        + "."
    )

    contexto_llm = (
        f"qtd a contratar: {qtd} | cargo: {cargo}\n"
        f"piso salarial: R$ {float(piso):,.2f} ({piso_src})\n"
        f"custo de folha mensal estimado: R$ {custo_mensal:,.2f} (encargos CCT {encargos_pct:.0f}%)\n"
        f"saldo disponível: R$ {saldo:,.2f} ({saldo_fonte})\n"
        f"folha mensal atual: R$ {folha_atual:,.2f}\n"
        f"runway atual: {runway_atual} meses | runway após contratação: {runway_novo} meses\n"
        f"postos descobertos hoje: {qtd_postos_desc}"
        + (f" ({', '.join(postos_desc)})" if postos_desc else "")
    )

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.viabilidade", fonte=fonte,
        pergunta=f"Posso contratar {qtd} {cargo}? Analise viabilidade financeira e a demanda operacional.",
        contexto_llm=contexto_llm, fallback=fallback,
    )
    return {"dados": dados, "sintese": sintese, "groundedness": gnd, "disclaimer": _DISCLAIMER}


# ─────────────────────────────────────────────────────────────────────────────
# 2) GET /briefing — 1-card executivo
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/briefing")
async def briefing(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟢 READ — 1-card: caixa (saldo Inter), postos descobertos (COO), certidões vencendo
    (fiscal, se acessível), deals quentes (CRM funil, se acessível). Cada número com source."""
    cfo = await _cfo_panorama(db)
    coo = await _coo_panorama(db)

    saldo = float(cfo.get("saldo_banco") or 0.0)
    cobertura = coo.get("cobertura") or {}
    postos_desc = list(cobertura.get("postos_descobertos") or [])

    # Certidões vencendo/vencidas — best-effort (ged_certidoes). Ausente → "aguardando dado".
    certidoes: dict[str, Any]
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE expiry_date < CURRENT_DATE) AS vencidas, "
                    "count(*) FILTER (WHERE expiry_date >= CURRENT_DATE AND expiry_date <= CURRENT_DATE + 30) AS vencendo_30d "
                    "FROM ged_certidoes"
                )
            )
        ).first()
        certidoes = _src(
            {"vencidas": int(rows.vencidas or 0), "vencendo_30d": int(rows.vencendo_30d or 0)},
            "ged_certidoes (validade real)",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("briefing certidoes: %s", e)
        certidoes = _src(None, "aguardando dado (ged_certidoes indisponível)")

    # Deals quentes — best-effort (pipeline aberto em negociação/proposta). Ausente → "aguardando dado".
    deals: dict[str, Any]
    try:
        row = (
            await db.execute(
                text(
                    "SELECT count(*) AS qtd, COALESCE(sum(value),0) AS valor FROM opportunities "
                    "WHERE is_active AND stage IN ('negotiation','proposal')"
                )
            )
        ).first()
        deals = _src(
            {"qtd": int(row.qtd or 0), "valor_total": float(row.valor or 0.0)},
            "opportunities (stage negotiation/proposal, ativos)",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("briefing deals: %s", e)
        deals = _src(None, "aguardando dado (opportunities indisponível)")

    dados = {
        "caixa_saldo": _src(saldo, cfo.get("saldo_fonte") or "cadastro"),
        "postos_descobertos_qtd": _src(len(postos_desc), "consultor_coo_service.panorama.cobertura"),
        "postos_descobertos": _src(postos_desc, "consultor_coo_service.panorama.cobertura"),
        "certidoes": certidoes,
        "deals_quentes": deals,
    }

    # Fonte p/ groundedness — só números com lastro real (omite os "aguardando dado")
    fonte: dict[str, Any] = {"saldo": saldo, "postos_descobertos_qtd": len(postos_desc)}
    cert_v = certidoes["valor"]
    if isinstance(cert_v, dict):
        fonte["certidoes_vencidas"] = cert_v["vencidas"]
        fonte["certidoes_vencendo"] = cert_v["vencendo_30d"]
    deal_v = deals["valor"]
    if isinstance(deal_v, dict):
        fonte["deals_qtd"] = deal_v["qtd"]
        fonte["deals_valor"] = deal_v["valor_total"]

    partes = [f"Caixa: R$ {saldo:,.2f}", f"Postos descobertos: {len(postos_desc)}"]
    if isinstance(cert_v, dict):
        partes.append(f"Certidões vencidas: {cert_v['vencidas']}, vencendo em 30d: {cert_v['vencendo_30d']}")
    else:
        partes.append("Certidões: aguardando dado")
    if isinstance(deal_v, dict):
        partes.append(f"Deals quentes: {deal_v['qtd']} (R$ {deal_v['valor_total']:,.2f})")
    else:
        partes.append("Deals quentes: aguardando dado")
    fallback = "Briefing executivo — " + " | ".join(partes) + "."

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.briefing", fonte=fonte,
        pergunta="Faça o briefing executivo de hoje (caixa, operação, compliance, comercial).",
        contexto_llm="\n".join(partes), fallback=fallback,
    )
    return {"dados": dados, "sintese": sintese, "groundedness": gnd,
            "as_of": datetime.now().isoformat(timespec="seconds"), "disclaimer": _DISCLAIMER}


# ─────────────────────────────────────────────────────────────────────────────
# 3) GET /runway — saldo Inter vivo ÷ folha mensal (corrige o KPI cache velho)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/runway")
async def runway(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟢 READ — runway ao vivo: saldo Inter vivo ÷ folha mensal = meses, com `as_of`.
    Reusa cfo_service.panorama (runway_meses já calculado sobre o saldo VIVO)."""
    cfo = await _cfo_panorama(db)
    saldo = float(cfo.get("saldo_banco") or 0.0)
    folha = float(cfo.get("folha_mensal") or 0.0)
    runway_meses = cfo.get("runway_meses")

    dados = {
        "saldo": _src(saldo, cfo.get("saldo_fonte") or "cadastro"),
        "folha_mensal": _src(folha, "cfo_service.panorama (KPI FOLHA)"),
        "runway_meses": _src(runway_meses, "cfo_service.panorama.runway_meses (saldo ÷ folha)"),
    }
    fonte = {"saldo": saldo, "folha": folha, "runway": runway_meses}

    if runway_meses is not None:
        fallback = (
            f"Runway ao vivo: R$ {saldo:,.2f} de saldo ÷ R$ {folha:,.2f} de folha mensal "
            f"= {runway_meses} meses de caixa."
        )
    else:
        fallback = (
            f"Saldo R$ {saldo:,.2f}; folha mensal ainda sem valor calculado — runway aguardando dado."
        )

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.runway", fonte=fonte,
        pergunta="Qual o runway de caixa hoje?",
        contexto_llm=f"saldo: R$ {saldo:,.2f} ({dados['saldo']['source']})\n"
                     f"folha mensal: R$ {folha:,.2f}\nrunway: {runway_meses} meses",
        fallback=fallback,
    )
    return {"dados": dados, "sintese": sintese, "groundedness": gnd,
            "as_of": datetime.now().isoformat(timespec="seconds"), "disclaimer": _DISCLAIMER}


# ─────────────────────────────────────────────────────────────────────────────
# 4) GET /margem-condominio — receita por contrato − folha alocada (best-effort)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/margem-condominio")
async def margem_condominio(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟢 READ — margem por contrato: receita (contracts.monthly_value) − folha alocada
    (posts.contract_id → allocations ativas → employees.salario_base). Best-effort: onde o
    cruzamento não fecha, a folha vem marcada "aguardando dado" — NUNCA inventamos."""
    # Receita por contrato (real). Cliente via join best-effort.
    rows = (
        await db.execute(
            text(
                "SELECT c.id::text AS contract_id, c.contract_number, "
                "COALESCE(cl.name, cl.trading_name, 'cliente s/ nome') AS cliente, "
                "COALESCE(c.monthly_value,0) AS receita "
                "FROM contracts c "
                "LEFT JOIN clients cl ON cl.id = c.client_id "
                "WHERE lower(c.status::text) IN ('active','ativo') "
                "ORDER BY c.monthly_value DESC NULLS LAST"
            )
        )
    ).fetchall() if True else []

    # Folha alocada por contrato: SUM(salario_base) de employees com allocation ativa em
    # posts daquele contrato. Onde não houver posts/alocações ligados, fica None (honesto).
    folha_por_contrato: dict[str, float] = {}
    cruzamento_disponivel = False
    try:
        frows = (
            await db.execute(
                text(
                    "SELECT p.contract_id::text AS contract_id, "
                    "COALESCE(SUM(e.salario_base),0) AS folha_base, COUNT(a.id) AS alocados "
                    "FROM posts p "
                    "JOIN allocations a ON a.post_id = p.id AND a.status::text ILIKE 'ACTIVE%' "
                    "JOIN employees e ON e.id = a.employee_id "
                    "WHERE p.contract_id IS NOT NULL "
                    "GROUP BY p.contract_id"
                )
            )
        ).fetchall()
        for r in frows:
            folha_por_contrato[r.contract_id] = float(r.folha_base or 0.0)
        cruzamento_disponivel = True
    except Exception as e:  # noqa: BLE001
        logger.debug("margem folha alocada: %s", e)

    itens = []
    total_receita = 0.0
    total_folha = 0.0
    for r in rows:
        receita = float(r.receita or 0.0)
        total_receita += receita
        folha_base = folha_por_contrato.get(r.contract_id)
        if folha_base is not None:
            total_folha += folha_base
            margem = round(receita - folha_base, 2)
            folha_src = "posts.contract_id → allocations ativas → employees.salario_base (sem encargos)"
        else:
            margem = None
            folha_src = "aguardando dado (sem posto/alocação ligado a este contrato)"
        itens.append({
            "contrato": r.contract_number,
            "cliente": r.cliente,
            "receita_mensal": _src(receita, "contracts.monthly_value"),
            "folha_alocada_base": _src(folha_base, folha_src),
            "margem_bruta_mensal": _src(
                margem,
                "receita − folha base (best-effort; encargos não incluídos)"
                if margem is not None else "aguardando dado (folha alocada indisponível)",
            ),
        })

    dados = {
        "itens": itens,
        "total_receita_mensal": _src(round(total_receita, 2), "SUM(contracts.monthly_value) ativos"),
        "total_folha_base_alocada": _src(
            round(total_folha, 2) if cruzamento_disponivel and folha_por_contrato else None,
            "SUM(employees.salario_base) alocados via posts.contract_id"
            if cruzamento_disponivel and folha_por_contrato
            else "aguardando dado (nenhum posto ligado a contrato)",
        ),
        "cobertura_do_cruzamento": _src(
            f"{len(folha_por_contrato)}/{len(rows)} contratos com folha alocada apurável",
            "diagnóstico do cruzamento posts↔contracts",
        ),
    }

    fonte: dict[str, Any] = {
        "total_receita": round(total_receita, 2),
        "contratos_ativos": len(rows),
        "contratos_com_folha": len(folha_por_contrato),
    }
    if cruzamento_disponivel and folha_por_contrato:
        fonte["total_folha"] = round(total_folha, 2)

    if folha_por_contrato:
        fallback = (
            f"Margem por condomínio: receita total mensal R$ {total_receita:,.2f} de {len(rows)} "
            f"contrato(s) ativos; folha base alocada apurável R$ {total_folha:,.2f} em "
            f"{len(folha_por_contrato)} deles. Contratos sem posto/alocação ligado ficam com "
            "folha 'aguardando dado' (não estimada)."
        )
    else:
        fallback = (
            f"Margem por condomínio: receita total mensal R$ {total_receita:,.2f} de {len(rows)} "
            "contrato(s) ativos. Folha alocada por contrato: aguardando dado — nenhum posto está "
            "ligado a um contrato (posts.contract_id vazio); cruzamento não apurável hoje."
        )

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.margem_condominio", fonte=fonte,
        pergunta="Qual a margem por condomínio (receita − folha alocada)?",
        contexto_llm=fallback, fallback=fallback,
    )
    return {"dados": dados, "sintese": sintese, "groundedness": gnd, "disclaimer": _DISCLAIMER}
