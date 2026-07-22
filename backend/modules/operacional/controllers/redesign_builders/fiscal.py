"""Fiscal (T1) — delega ao _build_fiscal e liga o menu json 'certidoes' às CNDs reais
(ged_certidoes) que já são montadas como 'certidoes-cnd'. Ação fiscal (transmitir) segue GATED.
nfse-multi/sped/ecac/consultor = capacidade sem tabela → honesto vazio."""
from modules.operacional.controllers.redesign_data_controller import (
    IC, _ICF, _build_fiscal, _scalar, brl,
)

SLUG = "fiscal"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_fiscal(db)
    # O item de menu json 'certidoes' estava vazio; aponta pras mesmas CNDs reais.
    if "certidoes-cnd" in out:
        out["certidoes"] = out["certidoes-cnd"]

    # FIDELIDADE ao hub clássico (/modulos/fiscal): o clássico HEADLINEIA "NFS-e Emitidas"
    # (nfse_emitidas_nacional, fonte autoritativa cStat 100 = 86) e "Certidões" (ged_certidoes = 9),
    # NÃO o histórico importado (nfse_manaus_historico = 831). A visão redesign mostrava 831 como
    # KPI principal → divergia do que o Jordan vê no clássico. Alinhamos os KPIs da visão aos
    # MESMOS números do clássico (86/9), mantendo obrigações + faturamento como contexto. O
    # histórico (831) segue disponível na aba 'nfse'. Números provados: 86 e 9 batem o clássico.
    try:
        n_emit = await _scalar(db, "SELECT count(*) FROM nfse_emitidas_nacional") or 0
        n_cnd = await _scalar(db, "SELECT count(*) FROM ged_certidoes") or 0
        obr_pend = await _scalar(
            db, "SELECT count(*) FROM fiscal_obligations "
                "WHERE status::text NOT IN ('pago','paga','concluido','concluida')") or 0
        fat12 = await _scalar(
            db, "SELECT coalesce(sum(valor_servicos),0) FROM nfse_manaus_historico "
                "WHERE data_emissao >= (SELECT max(data_emissao) FROM nfse_manaus_historico) - interval '12 months'") or 0
        if isinstance(out.get("painel"), dict):
            out["painel"]["kpis"] = [
                {"v": str(n_emit), "l": "NFS-e Emitidas", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {"v": str(n_cnd), "l": "Certidões", "icon": _ICF["chart"], "color": "#16A34A" if n_cnd else "#C2410C"},
                {"v": str(obr_pend), "l": "Obrigações em aberto", "icon": IC["alert"], "color": "#C2410C" if obr_pend else "#0F1B3A"},
                {"v": brl(fat12), "l": "Faturamento (12m)", "icon": _ICF["money"], "color": "#0F1B3A"},
            ]
    except Exception:  # noqa: BLE001 — a visão não pode derrubar o módulo
        pass
    return out
