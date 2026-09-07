"""Relatórios (T1) — delega ao _build_relatorios e preenche a 'central' com o hub de
navegação (cards) que o clássico mostra (Central de Relatórios PDF). Os relatórios em si
(operacional/financeiro/comercial) já são menu items com dado real."""
from datetime import date as _date

from modules.operacional.controllers.redesign_data_controller import _build_relatorios, _scalar, doc

SLUG = "relatorios"
EXTRA_MENU: list[dict] = [
    {"id": "kpis-recalcular", "label": "Recalcular KPIs", "icon": "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"},
]


async def build(db) -> dict:
    out = await _build_relatorios(db)
    # Hub 'Central de Relatórios' — cards por categoria (fidelidade ao clássico; nav é o menu).
    try:
        _ano = _date.today().year
        n_nfse = await _scalar(db, "SELECT count(*) FROM nfse_manaus_historico")
        n_colab = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        n_contr = await _scalar(db, "SELECT count(*) FROM contracts")
        out["central"] = {
            "title": "Central de Relatórios",
            "sub": "Dashboards executivos e relatórios — dados reais da operação",
            "type": "cards",
            "cards": [
                {"title": "Operacional", "sub": "Presença, escalas, postos e ocorrências",
                 "badge": f"{n_colab or 0} colaboradores", "color": "#0F1B3A", "bg": "rgba(15,27,58,0.08)"},
                {"title": "Financeiro", "sub": "DRE, fluxo de caixa, contas e saldos",
                 "badge": f"{n_nfse or 0} NFS-e", "color": "#16A34A", "bg": "#E7F7ED"},
                {"title": "Comercial", "sub": "Funil, propostas, contratos e MRR",
                 "badge": f"{n_contr or 0} contratos", "color": "#2563EB", "bg": "#EAF0FF"},
                {"title": "Dashboards Executivos", "sub": "KPIs consolidados da operação",
                 "badge": "Executivo", "color": "#B45309", "bg": "#FFFBEB"},
            ],
            # Relatórios PDF do hub — rotas curl-provadas (200 application/pdf ~267KB), gated financeiro.
            "docs": [
                doc("DRE (PDF)", f"/api/v1/financial/relatorios/dre/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
                doc("Balancete (PDF)", f"/api/v1/financial/relatorios/balancete/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
                doc("Fluxo de caixa (PDF)", f"/api/v1/financial/relatorios/fluxo-caixa/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # Fio solto (2026-08-10): o recálculo dos KPIs executivos existia sem botão — os
    # painéis mostravam número velho e não havia como forçar a atualização pela tela.
    out["kpis-recalcular"] = {
        "title": "Recalcular KPIs executivos",
        "sub": "Refaz o cálculo dos indicadores a partir do banco. Use quando o painel "
               "parecer defasado. Só recalcula — não altera lançamento nenhum.",
        "cta": "Recalcular", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/kpis-recalcular",
                   "okMsg": "Recálculo dos KPIs disparado"},
        "fields": [],
    }
    return out
