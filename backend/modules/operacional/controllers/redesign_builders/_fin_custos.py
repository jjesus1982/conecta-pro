"""F6 — Custeio ABC REAL (corrige a lacuna: o 'custeio' do redesign era só o simulador CCT).
REUSA as funções exatas do custeio_controller: get_custeio_abc (MRR/custo/margem por tipo de
serviço + custo por categoria) e get_custeio_contratos (margem por contrato individual)."""
from modules.operacional.controllers.redesign_data_controller import S, _helpers, b, brl, t


def _tone_cls(c):
    c = (c or "").lower()
    return "ok" if c in ("estrela", "saudavel", "saudável") else "bad" if c in ("critico", "crítico") else "warn"


async def build_custos(db, out: dict) -> None:
    _, _safe, _tbl = _helpers(db)
    _user = {"id": "redesign", "email": "redesign@conectapro"}

    # ── Custeio ABC por tipo de serviço (função exata do endpoint /custeio/abc) ──────────
    try:
        from modules.financial.controllers.custeio_controller import get_custeio_abc
        abc = await get_custeio_abc(condominio_id=None, current_user=_user, db=db)
        tipos = abc.get("analise_por_tipo", []) or []
        cats = abc.get("custo_por_categoria", []) or []
        out["custeio-abc"] = {
            "title": "Custeio ABC por tipo de serviço", "type": "dash", "cta": "—",
            "sub": f"Período {abc.get('periodo_referencia','—')} · margem global {abc.get('margem_global_pct','—')}% (dados reais do banco)",
            "panelGrid": "1.4fr 1fr",
            "kpis": [
                {"v": brl(abc.get("mrr_total")), "l": "MRR total", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6", "color": "#16A34A"},
                {"v": brl(abc.get("custo_total_mes")), "l": "Custo total (mês)", "icon": "M2 6h20M2 18h20M6 6v12M10 6v12M14 6v12M18 6v12", "color": "#C2410C"},
                {"v": brl(abc.get("resultado_estimado")), "l": "Resultado estimado", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
                {"v": f"{abc.get('margem_global_pct','—')}%", "l": "Margem global", "icon": "M3 3v18h18M18 9l-5 5-4-4-3 3", "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Análise por tipo de serviço", "rows": [
                    {"left": f"{tp.get('label','—')} · {tp.get('contratos',0)} contrato(s) · {tp.get('pct_mrr','—')}% do MRR",
                     "right": f"{brl(tp.get('receita_mensal'))} · {tp.get('classificacao','—')}",
                     **S[_tone_cls(tp.get("classificacao"))]} for tp in tipos] or
                    [{"left": "Sem análise disponível", "right": "—", **S["mut"]}]},
                {"title": "Custo por categoria (mês)", "rows": [
                    {"left": f"{c.get('categoria','—')} ({c.get('qtd',0)})", "right": brl(c.get("total")),
                     **S["info"]} for c in cats[:8]] or [{"left": "Sem custos", "right": "—", **S["mut"]}]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Margem por contrato (função exata do endpoint /custeio/contratos) ────────────────
    try:
        from modules.financial.controllers.custeio_controller import get_custeio_contratos
        cc = await get_custeio_contratos(condominio_id=None, current_user=_user, db=db)
        contratos = cc.get("contratos", []) or []
        out["custeio-contratos"] = {
            "title": "Margem por contrato", "type": "table", "cta": "—", "searchHint": "Buscar contrato…",
            "sub": f"{cc.get('total_contratos', len(contratos))} contratos — receita × custo estimado (dados reais)",
            "grid": "2.2fr 0.9fr 1fr 1fr 0.9fr 0.9fr",
            "cols": ["Contrato", "Tipo", "Receita/mês", "Custo estimado", "MC", "Status"],
            "rows": [{"cells": [
                t((c.get("nome") or "—")[:48], 600, "#0F1B3A"),
                t((c.get("tipo") or "—").capitalize()),
                t(brl(c.get("receita_mensal")), 600),
                t(brl(c.get("custo_estimado"))),
                b(f"{c.get('mc_pct','—')}%", "ok" if (c.get("mc_pct") or 0) >= 0 else "bad"),
                b((c.get("status") or "—").capitalize(), _tone_cls(c.get("status"))),
            ]} for c in contratos]}
    except Exception:  # noqa: BLE001
        pass
