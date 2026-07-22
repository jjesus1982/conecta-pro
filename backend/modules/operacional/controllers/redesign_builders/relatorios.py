"""Relatórios (T1) — delega ao _build_relatorios e preenche a 'central' com o hub de
navegação (cards) que o clássico mostra (Central de Relatórios PDF). Os relatórios em si
(operacional/financeiro/comercial) já são menu items com dado real."""
from modules.operacional.controllers.redesign_data_controller import _build_relatorios, _scalar

SLUG = "relatorios"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_relatorios(db)
    # Hub 'Central de Relatórios' — cards por categoria (fidelidade ao clássico; nav é o menu).
    try:
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
        }
    except Exception:  # noqa: BLE001
        pass
    return out
