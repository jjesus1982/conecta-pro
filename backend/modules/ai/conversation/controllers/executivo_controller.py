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
import re
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


async def _coo_panorama(db: AsyncSession) -> dict[str, Any]:
    from modules.operacional.services import consultor_coo_service

    return await consultor_coo_service.panorama(db)


async def _caixa_cnpj(db: AsyncSession) -> dict[str, Any]:
    """Caixa + folha POR CNPJ (Inter/Eletrônica × Cora/Patrimonial), com proveniência."""
    from modules.financial.services import caixa_service

    return await caixa_service.caixa_por_cnpj(db)


def _classificar_cargo(cargo: str) -> tuple[str, str]:
    """CARGO → (natureza 'patrimonial'|'eletronica', empresa_id). Roteia a contratação."""
    from modules.empresas.services.classificador_cargo import classificar_cargo_empresa

    return classificar_cargo_empresa(cargo)


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
    coo = await _coo_panorama(db)
    piso, piso_src = await _piso_do_cargo(db, cargo)
    custo_mensal, encargos_pct, base_sal, custo_src = _custo_folha_mensal(piso, qtd)

    # CIENTE DE CNPJ: o cargo decide contra QUAL empresa/conta avaliar. Mão de obra
    # humanizada (porteiro, serviços gerais, artífice…) → Patrimonial/Cora; técnica
    # (dev, monitoramento, CFTV…) → Eletrônica/Inter. Antes lia SÓ o Inter (bug do dono).
    natureza, empresa_id = _classificar_cargo(cargo)
    caixa = await _caixa_cnpj(db)
    alvo = caixa[natureza]
    empresa_nome, banco = alvo["nome"], alvo["banco"]

    saldo = alvo["saldo"]  # pode ser None (aguardando dado)
    saldo_fonte = alvo["saldo_fonte"]
    folha_atual = alvo["folha"]  # folha DAQUELE CNPJ (None se sem colaborador ativo)
    folha_fonte = alvo["folha_fonte"]
    n_ativos = alvo["funcionarios_ativos"]

    postos_desc = list((coo.get("cobertura") or {}).get("postos_descobertos") or [])
    qtd_postos_desc = len(postos_desc)

    saldo_num = float(saldo) if saldo is not None else None
    folha_base = float(folha_atual) if folha_atual is not None else 0.0
    folha_nova = folha_base + custo_mensal
    runway_atual = (
        round(saldo_num / folha_base, 1) if (saldo_num is not None and folha_base > 0) else None
    )
    runway_novo = (
        round(saldo_num / folha_nova, 1) if (saldo_num is not None and folha_nova > 0) else None
    )
    meses_cobertos_pelo_saldo = (
        round(saldo_num / custo_mensal, 1) if (saldo_num is not None and custo_mensal > 0) else None
    )

    dados = {
        "qtd_solicitada": _src(qtd, "parâmetro da consulta"),
        "cargo": _src(cargo, "parâmetro da consulta"),
        "empresa_avaliada": _src(
            {"natureza": natureza, "empresa_id": empresa_id, "nome": empresa_nome, "banco": banco},
            "classificador cargo→CNPJ (natureza da mão de obra)",
        ),
        "piso_salarial": _src(float(piso), piso_src),
        "custo_folha_mensal_estimado": _src(custo_mensal, custo_src),
        "encargos_cct_pct": _src(encargos_pct, "PricingEngine.CCT_COMPONENTS"),
        "base_salarios_mensal": _src(base_sal, "piso × qtd (sem encargos)"),
        "saldo_disponivel": _src(saldo_num, saldo_fonte),
        "folha_mensal_atual": _src(folha_atual, folha_fonte),
        "funcionarios_ativos_empresa": _src(n_ativos, folha_fonte),
        "runway_atual_meses": _src(runway_atual, f"saldo {banco} ÷ folha {empresa_nome}"),
        "runway_apos_contratacao_meses": _src(runway_novo, "saldo ÷ (folha da empresa + custo novo)"),
        "meses_que_o_saldo_cobre_so_o_novo_custo": _src(meses_cobertos_pelo_saldo, "saldo ÷ custo novo"),
        "postos_descobertos_qtd": _src(qtd_postos_desc, "consultor_coo_service.panorama.cobertura"),
        "postos_descobertos": _src(postos_desc, "consultor_coo_service.panorama.cobertura"),
    }

    # Fonte p/ groundedness: só os números reais (achatados). Omite os None (aguardando dado).
    fonte: dict[str, Any] = {
        "qtd": qtd, "piso": float(piso), "custo_folha_mensal_estimado": custo_mensal,
        "encargos_cct_pct": encargos_pct, "base_salarios": base_sal,
        "postos_descobertos_qtd": qtd_postos_desc,
    }
    if saldo_num is not None:
        fonte["saldo"] = saldo_num
    if folha_atual is not None:
        fonte["folha_atual"] = folha_base
        fonte["folha_nova"] = folha_nova
    if n_ativos is not None:
        fonte["n_ativos"] = n_ativos
    for k, v in (("runway_atual", runway_atual), ("runway_novo", runway_novo),
                 ("meses_cobertos", meses_cobertos_pelo_saldo)):
        if v is not None:
            fonte[k] = v

    saldo_txt = f"R$ {saldo_num:,.2f}" if saldo_num is not None else "aguardando dado"
    folha_txt = f"R$ {folha_base:,.2f}" if folha_atual is not None else "sem colaborador ativo (aguardando dado)"

    # Fallback determinístico (grounded por construção — só números da fonte)
    fallback = (
        f"Avaliado contra {empresa_nome} (Banco {banco}). "
        f"Contratar {qtd} {cargo} custa cerca de R$ {custo_mensal:,.2f}/mês "
        f"(piso R$ {float(piso):,.2f} + {encargos_pct:.0f}% de encargos CCT). "
        f"Saldo {banco}: {saldo_txt}; folha atual de {empresa_nome}: {folha_txt}"
        + (f"; o runway iria de {runway_atual} para {runway_novo} meses" if runway_novo is not None and runway_atual is not None else "")
        + f". Postos descobertos hoje: {qtd_postos_desc}"
        + (f" ({', '.join(postos_desc[:5])})" if postos_desc else "")
        + "."
    )

    contexto_llm = (
        f"empresa avaliada (pelo cargo): {empresa_nome} — Banco {banco}\n"
        f"qtd a contratar: {qtd} | cargo: {cargo}\n"
        f"piso salarial: R$ {float(piso):,.2f} ({piso_src})\n"
        f"custo de folha mensal estimado: R$ {custo_mensal:,.2f} (encargos CCT {encargos_pct:.0f}%)\n"
        f"saldo disponível ({banco}): {saldo_txt} ({saldo_fonte})\n"
        f"folha mensal atual ({empresa_nome}): {folha_txt}\n"
        f"runway atual: {runway_atual} meses | runway após contratação: {runway_novo} meses\n"
        f"postos descobertos hoje: {qtd_postos_desc}"
        + (f" ({', '.join(postos_desc)})" if postos_desc else "")
    )

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.viabilidade", fonte=fonte,
        pergunta=f"Posso contratar {qtd} {cargo}? Analise viabilidade financeira (contra a empresa/conta certa pelo cargo) e a demanda operacional.",
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
    """🟢 READ — 1-card: caixa DISCRIMINADA por CNPJ (Inter/Eletrônica + Cora/Patrimonial +
    consolidado), postos descobertos (COO), certidões vencendo (fiscal, se acessível), deals
    quentes (CRM funil, se acessível). Cada número com source."""
    caixa = await _caixa_cnpj(db)
    coo = await _coo_panorama(db)

    ele, patr = caixa["eletronica"], caixa["patrimonial"]
    saldo_ele = ele["saldo"]
    saldo_patr = patr["saldo"]
    saldo_total = caixa["consolidado"]["saldo_total"]["valor"]
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
        "caixa_eletronica": _src(
            {"nome": ele["nome"], "banco": ele["banco"], "saldo": saldo_ele, "as_of": ele["as_of"]},
            ele["saldo_fonte"],
        ),
        "caixa_patrimonial": _src(
            {"nome": patr["nome"], "banco": patr["banco"], "saldo": saldo_patr, "as_of": patr["as_of"]},
            patr["saldo_fonte"],
        ),
        "caixa_consolidado": _src(saldo_total, caixa["consolidado"]["saldo_total"]["source"]),
        "postos_descobertos_qtd": _src(len(postos_desc), "consultor_coo_service.panorama.cobertura"),
        "postos_descobertos": _src(postos_desc, "consultor_coo_service.panorama.cobertura"),
        "certidoes": certidoes,
        "deals_quentes": deals,
    }

    # Fonte p/ groundedness — só números com lastro real (omite os "aguardando dado")
    fonte: dict[str, Any] = {"postos_descobertos_qtd": len(postos_desc)}
    if saldo_ele is not None:
        fonte["saldo_eletronica"] = float(saldo_ele)
    if saldo_patr is not None:
        fonte["saldo_patrimonial"] = float(saldo_patr)
    if saldo_total is not None:
        fonte["saldo_total"] = float(saldo_total)
    cert_v = certidoes["valor"]
    if isinstance(cert_v, dict):
        fonte["certidoes_vencidas"] = cert_v["vencidas"]
        fonte["certidoes_vencendo"] = cert_v["vencendo_30d"]
    deal_v = deals["valor"]
    if isinstance(deal_v, dict):
        fonte["deals_qtd"] = deal_v["qtd"]
        fonte["deals_valor"] = deal_v["valor_total"]

    _sfmt = lambda v: (f"R$ {float(v):,.2f}" if v is not None else "aguardando dado")  # noqa: E731
    partes = [
        f"Caixa Eletrônica (Inter): {_sfmt(saldo_ele)}",
        f"Caixa Patrimonial (Cora): {_sfmt(saldo_patr)}",
        f"Caixa consolidado: {_sfmt(saldo_total)}",
        f"Postos descobertos: {len(postos_desc)}",
    ]
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
    """🟢 READ — runway ao vivo POR CNPJ: Inter÷folha Eletrônica e Cora÷folha Patrimonial,
    com `as_of`. NÃO mistura as contas (era o bug do dono). Nunca fabrica: onde falta saldo
    ou folha, o runway daquele CNPJ fica 'aguardando dado'."""
    caixa = await _caixa_cnpj(db)

    def _runway_bloco(b: dict[str, Any]) -> dict[str, Any]:
        saldo = b["saldo"]
        folha = b["folha"]
        rw = (
            round(float(saldo) / float(folha), 1)
            if (saldo is not None and folha not in (None, 0, 0.0))
            else None
        )
        rw_fonte = (
            f"saldo {b['banco']} ÷ folha {b['nome']} (colaboradores ativos)"
            if rw is not None
            else "aguardando dado (saldo ou folha do CNPJ indisponível)"
        )
        return {
            "empresa": b["nome"], "banco": b["banco"],
            "saldo": _src(saldo, b["saldo_fonte"]),
            "folha_mensal": _src(folha, b["folha_fonte"]),
            "runway_meses": _src(rw, rw_fonte),
            "as_of": b["as_of"],
            "_runway": rw,
        }

    r_ele = _runway_bloco(caixa["eletronica"])
    r_patr = _runway_bloco(caixa["patrimonial"])

    dados = {
        "eletronica": {k: v for k, v in r_ele.items() if k != "_runway"},
        "patrimonial": {k: v for k, v in r_patr.items() if k != "_runway"},
    }

    fonte: dict[str, Any] = {}
    for tag, b, rb in (("eletronica", caixa["eletronica"], r_ele), ("patrimonial", caixa["patrimonial"], r_patr)):
        if b["saldo"] is not None:
            fonte[f"saldo_{tag}"] = float(b["saldo"])
        if b["folha"] is not None:
            fonte[f"folha_{tag}"] = float(b["folha"])
        if rb["_runway"] is not None:
            fonte[f"runway_{tag}"] = rb["_runway"]

    def _linha(b: dict[str, Any], rb: dict[str, Any]) -> str:
        saldo = b["saldo"]; folha = b["folha"]; rw = rb["_runway"]
        stxt = f"R$ {float(saldo):,.2f}" if saldo is not None else "aguardando dado"
        ftxt = f"R$ {float(folha):,.2f}" if folha is not None else "sem folha ativa"
        rtxt = f"{rw} meses" if rw is not None else "aguardando dado"
        return f"{b['nome']} (Banco {b['banco']}): saldo {stxt} ÷ folha {ftxt} = runway {rtxt}"

    fallback = (
        "Runway ao vivo por CNPJ — "
        + _linha(caixa["eletronica"], r_ele) + " | "
        + _linha(caixa["patrimonial"], r_patr) + "."
    )

    sintese, gnd = await _sintetizar(
        db, origem_evento="executivo.runway", fonte=fonte,
        pergunta="Qual o runway de caixa hoje, por CNPJ (Eletrônica/Inter e Patrimonial/Cora)?",
        contexto_llm=_linha(caixa["eletronica"], r_ele) + "\n" + _linha(caixa["patrimonial"], r_patr),
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
    # posts daquele contrato, ATRIBUÍDA AO CNPJ via employees.empresa_id → empresas.slug.
    # Onde não houver posts/alocações ligados, fica None (honesto). Hoje posts.contract_id
    # está vazio em produção → o cruzamento não fecha; o CNPJ da folha aparece quando popular.
    folha_por_contrato: dict[str, float] = {}
    cnpj_por_contrato: dict[str, str] = {}
    cruzamento_disponivel = False
    try:
        frows = (
            await db.execute(
                text(
                    "SELECT p.contract_id::text AS contract_id, e.slug AS empresa, "
                    "COALESCE(SUM(emp.salario_base),0) AS folha_base, COUNT(a.id) AS alocados "
                    "FROM posts p "
                    "JOIN allocations a ON a.post_id = p.id AND a.status::text ILIKE 'ACTIVE%' "
                    "JOIN employees emp ON emp.id = a.employee_id "
                    "LEFT JOIN empresas e ON e.id = emp.empresa_id "
                    "WHERE p.contract_id IS NOT NULL "
                    "GROUP BY p.contract_id, e.slug"
                )
            )
        ).fetchall()
        for r in frows:
            folha_por_contrato[r.contract_id] = folha_por_contrato.get(r.contract_id, 0.0) + float(r.folha_base or 0.0)
            if r.empresa:
                cnpj_por_contrato[r.contract_id] = r.empresa
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
            "cnpj_folha": _src(
                cnpj_por_contrato.get(r.contract_id),
                "employees.empresa_id → empresas.slug (CNPJ que arca a folha alocada)"
                if cnpj_por_contrato.get(r.contract_id)
                else "aguardando dado (sem alocação ligada a este contrato)",
            ),
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


# ─────────────────────────────────────────────────────────────────────────────
# 5) ORQUESTRADOR — POST /consultar  (o que "ACENDE" o Hermes: direct=False)
# ─────────────────────────────────────────────────────────────────────────────
# Diferente dos 4 quick-wins acima (que passam direct=True — guard de re-entrância, síntese
# curta OpenAI direta e groundedness DURO que descarta a síntese suspeita), este é o CHAT
# LIVRE executivo. Com `direct=False`, a ponte em consultor_hub.gerar roteia pro Hermes local
# quando HERMES_BRIDGE_ENABLED=true e o Hermes está vivo — o cérebro encadeia as ~243 tools MCP
# CNPJ-aware. Se o Hermes cair, `gerar` já degrada pro MODEL_CHAIN (OpenAI) sobre o LASTRO
# ancorado (a degradação é da PONTE — não reimplementamos aqui). Groundedness em modo BRANDO:
# rebaixa/flag, não bloqueia (o orquestrador legitimamente puxa de tools que o lastro
# pré-buscado não cobre); só reforça o lastro em caso de CONTRADIÇÃO clara com um saldo real.
# NÃO é exposto como tool MCP (seria loop Hermes→tool→gerar→Hermes) — é endpoint p/ o dono.

class ConsultarIn(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=2000, description="Pergunta executiva livre")


def _fmt_brl(v: Any) -> str:
    if v is None:
        return "aguardando dado"
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _detectar_contradicao(resposta: str, anchors: list[tuple[list[str], float]]) -> list[str]:
    """Contradição CLARA (única condição em que o modo brando reforça o lastro): uma frase
    que fala de 'saldo' de uma conta âncora (Inter/Cora/consolidado) citando um valor
    MONETÁRIO da MESMA ordem de grandeza do saldo real, porém divergente. Conservador de
    propósito — exige 'saldo' + o rótulo da conta na MESMA frase e o valor dentro de ±50%
    do real (senão é outra grandeza, ex. folha, não uma contradição do saldo)."""
    contras: list[str] = []
    # Split de frases que NÃO quebra números BR: um '.' entre dígitos (milhar, ex. 30.813,63)
    # não é fim de frase — só '.'/';'/quebra fora de dígitos delimita.
    for frase in re.split(r"(?<!\d)[.;\n]+(?!\d)", resposta or ""):
        fl = frase.lower()
        if "saldo" not in fl:
            continue
        for rotulos, val_real in anchors:
            if not any(r in fl for r in rotulos):
                continue
            for n in groundedness.extrair_numeros(frase, ignorar_anos=True, ignorar_percentuais=True):
                try:
                    v = float(groundedness._canon(n))  # noqa: SLF001 — reuso do canonizador da garantia
                except ValueError:
                    continue
                if v < 1000:  # contagens/inteiros pequenos não são saldo
                    continue
                if not (0.5 * val_real <= v <= 1.5 * val_real):
                    continue  # ordem de grandeza diferente → outra grandeza, não contradição do saldo
                if abs(v - val_real) > max(1.0, val_real * 0.005):
                    contras.append(f"{rotulos[0]}: citou R$ {n}, mas o saldo real é {_fmt_brl(val_real)}")
    return contras


@router.post("/consultar")
async def consultar(
    payload: ConsultarIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """🟢 READ — ORQUESTRADOR EXECUTIVO (chat livre do dono). "Acende" o Hermes via a ponte
    (direct=False): o cérebro cruza caixa/folha/postos/deals encadeando as tools MCP CNPJ-aware.
    Pré-busca o LASTRO real (caixa por CNPJ + postos descobertos) que ancora o groundedness E
    dá contexto ao cérebro mesmo em degradação. Groundedness BRANDO: rebaixa/flag, não bloqueia;
    só reforça o lastro em contradição clara com um saldo real. Money-out/ato legal = propõe, nunca executa."""
    pergunta = payload.pergunta.strip()

    # 1) LASTRO (fonte real) — ancora o groundedness e alimenta o cérebro na degradação.
    caixa = await _caixa_cnpj(db)
    ele, patr, cons = caixa["eletronica"], caixa["patrimonial"], caixa["consolidado"]
    saldo_ele, saldo_patr = ele["saldo"], patr["saldo"]
    saldo_total = cons["saldo_total"]["valor"]
    folha_ele, folha_patr = ele["folha"], patr["folha"]
    folha_total = cons["folha_total"]["valor"]

    # Postos descobertos (COO) — aditivo/best-effort; nunca derruba a consulta.
    qtd_postos = None
    postos_desc: list[Any] = []
    try:
        coo = await _coo_panorama(db)
        postos_desc = list((coo.get("cobertura") or {}).get("postos_descobertos") or [])
        qtd_postos = len(postos_desc)
    except Exception as e:  # noqa: BLE001
        logger.debug("consultar: COO indisponível (aditivo): %s", e)

    # 2) Contexto ancorado (números reais) — anexado ao system prompt E usado como template.
    linhas_ctx = [
        f"Conecta Eletrônica (Banco {ele['banco']}): saldo {_fmt_brl(saldo_ele)} ({ele['saldo_fonte']}); "
        f"folha {_fmt_brl(folha_ele)} ({ele['funcionarios_ativos'] or 0} colaboradores ativos).",
        f"Conecta Patrimonial (Banco {patr['banco']}): saldo {_fmt_brl(saldo_patr)} ({patr['saldo_fonte']}); "
        f"folha {_fmt_brl(folha_patr)} ({patr['funcionarios_ativos'] or 0} colaboradores ativos).",
        f"Consolidado: saldo {_fmt_brl(saldo_total)}; folha {_fmt_brl(folha_total)}.",
    ]
    if qtd_postos is not None:
        linhas_ctx.append(
            f"Postos descobertos hoje: {qtd_postos}"
            + (f" ({', '.join(str(p) for p in postos_desc[:5])})" if postos_desc else "")
            + "."
        )
    contexto_caixa = "\n".join(linhas_ctx)

    system_prompt = (
        "Você é o Orquestrador Executivo da Conecta PRO — a visão do dono. Cruze caixa, folha, "
        "postos, prazos e deals para responder à diretoria com precisão.\n\n"
        "DUAS empresas/contas — NUNCA misture:\n"
        "- Conecta Eletrônica → Banco Inter (segurança eletrônica / portaria remota / "
        "monitoramento; quadro ativo = PJ/técnico).\n"
        "- Conecta Patrimonial → Banco Cora (mão de obra humanizada: agente de portaria, "
        "serviços gerais, artífice, jardineiro; 50 CLT).\n"
        "Uma decisão de MÃO DE OBRA olha Patrimonial/Cora; segurança ELETRÔNICA olha "
        "Eletrônica/Inter. Nunca misture as contas.\n\n"
        "REGRAS:\n"
        "- Use as tools para buscar CADA número no banco; CITE a fonte de cada número; NUNCA "
        "fabrique — se faltar, diga 'aguardando dado'.\n"
        "- Dinheiro que SAI e ato legal SEMPRE exigem gate humano + OTP — você PROPÕE, nunca executa.\n\n"
        "=== LASTRO ANCORADO (números reais do banco, agora) ===\n" + contexto_caixa
    )

    # 3) CÉREBRO via a ponte (direct=False → Hermes quando vivo; senão MODEL_CHAIN sobre o lastro).
    template = (
        "Segue o lastro real do banco (cérebro executivo indisponível no momento): "
        + contexto_caixa.replace("\n", " ")
    )
    provider, modelo = "template", "n/a"
    resposta = template
    try:
        from modules.ai.conversation.services import consultor_hub as _hub

        texto, meta = await _hub.gerar(
            messages=[{"role": "user", "content": pergunta}],
            system_prompt=system_prompt, origem="executivo", direct=False,
            max_tokens=1200, temperature=0.3,
        )
        texto = (texto or "").strip()
        if texto:
            resposta = texto
            provider = str(meta.get("provider") or "model_chain")
            modelo = str(meta.get("model") or "openai")
    except Exception as e:  # noqa: BLE001 — cérebro totalmente fora → template ancorado (nunca quebra)
        logger.warning("consultar: cérebro indisponível, usando template ancorado: %s", e)

    # 4) GROUNDEDNESS BRANDO — fonte = só números reais (omite None). Rebaixa/flag, não bloqueia.
    fonte: dict[str, Any] = {}
    if saldo_ele is not None:
        fonte["saldo_inter"] = float(saldo_ele)
    if saldo_patr is not None:
        fonte["saldo_cora"] = float(saldo_patr)
    if saldo_total is not None:
        fonte["saldo_consolidado"] = float(saldo_total)
    if folha_ele is not None:
        fonte["folha_eletronica"] = float(folha_ele)
    if folha_patr is not None:
        fonte["folha_patrimonial"] = float(folha_patr)
    if folha_total is not None:
        fonte["folha_total"] = float(folha_total)
    if qtd_postos is not None:
        fonte["postos_descobertos"] = qtd_postos
    fonte = _fonte_robusta(fonte)

    g = groundedness.verificar(resposta, fonte)
    suspeitos = list(g.get("suspeitos") or [])

    # Contradição CLARA com um saldo real (única condição que REFORÇA o lastro no modo brando).
    anchors: list[tuple[list[str], float]] = []
    if saldo_ele is not None:
        anchors.append((["inter", "eletrônica", "eletronica"], float(saldo_ele)))
    if saldo_patr is not None:
        anchors.append((["cora", "patrimonial"], float(saldo_patr)))
    if saldo_total is not None:
        anchors.append((["consolidado"], float(saldo_total)))
    contradicoes = _detectar_contradicao(resposta, anchors)

    flags: list[str] = []
    if contradicoes:
        # Reforça o lastro: prefixa a resposta com a correção autoritativa (não a descarta inteira,
        # mas o número certo passa a vir primeiro e em destaque). grounded=False.
        correcao = "⚠️ CORREÇÃO (dados reais do banco): " + "; ".join(contradicoes) + "."
        resposta = correcao + "\n\n" + resposta
        flags.append("contradicao_saldo_corrigida")
    if suspeitos and not contradicoes:
        # Números não verificáveis contra o lastro pré-buscado → flag "confira", SEM descartar.
        flags.append(
            "confira: alguns números não puderam ser verificados automaticamente contra o "
            "lastro do banco (" + ", ".join(suspeitos[:8]) + ") — confira antes de decidir"
        )
        resposta = (
            resposta
            + "\n\n[Aviso: alguns números acima não puderam ser verificados automaticamente "
            "contra o lastro do banco — confira antes de decidir.]"
        )
    grounded = not contradicoes and not suspeitos

    # 5) Auditoria append-only (best-effort — nunca derruba o endpoint de leitura).
    try:
        await agent_audit.registrar_acao_agente(
            db, origem="executivo", pergunta=pergunta, resposta=resposta,
            modelo=modelo, tier="orquestrador", provider=provider,
            groundedness_ok=grounded, trace_id="executivo.consultar",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("consultar: falha ao auditar: %s", e)

    caixa_resumo = {
        "eletronica": {
            "nome": ele["nome"], "banco": ele["banco"], "saldo": saldo_ele,
            "folha": folha_ele, "ativos": ele["funcionarios_ativos"],
            "as_of": ele["as_of"], "saldo_fonte": ele["saldo_fonte"],
        },
        "patrimonial": {
            "nome": patr["nome"], "banco": patr["banco"], "saldo": saldo_patr,
            "folha": folha_patr, "ativos": patr["funcionarios_ativos"],
            "as_of": patr["as_of"], "saldo_fonte": patr["saldo_fonte"],
        },
        "consolidado": {"saldo_total": saldo_total, "folha_total": folha_total},
        "postos_descobertos": qtd_postos,
    }

    return {
        "resposta": resposta,
        "provider": provider,
        "modelo": modelo,
        "grounded": grounded,
        "flags": flags,
        "caixa_resumo": caixa_resumo,
        "origem": "executivo",
        "disclaimer": _DISCLAIMER,
    }
