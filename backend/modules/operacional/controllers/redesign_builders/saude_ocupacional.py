"""Saúde ocupacional (T1) — delega ao _build_saude do monólito e ESTENDE com
estabilidade (garantia de emprego) e alertas (ASOs vencidos). Leitura real; ação
legal (transmitir eSocial) segue GATED."""
from modules.operacional.controllers.redesign_data_controller import (
    S, _build_saude, _fmtdate, _helpers, _scalar, b, t,
)

SLUG = "saude-ocupacional"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_saude(db)  # base: visao, exames, epi, riscos, esocial, cat, afastamentos
    _, _safe, tbl = _helpers(db)

    # Estabilidade / garantia de emprego (CCT + Lei 8.213) — sst_afastamentos c/ gera_estabilidade
    try:
        n_est = await _scalar(db, "SELECT count(*) FROM sst_afastamentos WHERE gera_estabilidade=true")
        out["estabilidade"] = await tbl(
            "Estabilidade (garantia de emprego)", f"{n_est} colaborador(es) com estabilidade", "—",
            ["Colaborador", "Motivo", "Estável até", "Status"], "1.8fr 1.3fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.estabilidade_ate, coalesce(a.status::text,'—') "
            "FROM sst_afastamentos a LEFT JOIN employees e ON e.id::text=a.employee_id::text "
            "WHERE a.gera_estabilidade=true ORDER BY a.estabilidade_ate DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])),
                       b((r[3] or '—').replace('_', ' ').capitalize(), "ok")])
    except Exception:  # noqa: BLE001 — uma tela falha não derruba as demais
        pass

    # Alertas SST — ASOs vencidos (renovação de exame) — gp_asos
    try:
        n_venc = await _scalar(db, "SELECT count(*) FROM gp_asos WHERE data_validade < now()")
        out["alertas"] = await tbl(
            "Alertas SST — ASOs vencidos", f"{n_venc} ASOs vencidos (renovar exame)", "—",
            ["Colaborador", "Tipo", "Venceu em", "Status"], "1.8fr 1.2fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, coalesce(a.status::text,'—') "
            "FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id "
            "WHERE a.data_validade < now() ORDER BY a.data_validade DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])), b("Vencido", "bad")])
    except Exception:  # noqa: BLE001
        pass

    # Exames: painel de regularização PCMSO (composite) — FIDELIDADE: lógica EXATA do clássico
    # (último ASO por colaborador ATIVO), _get_pcmso_stats do sst_service → números batem (25).
    try:
        validos = await _scalar(
            db, "SELECT count(DISTINCT employee_id) FROM gp_asos WHERE status='realizado' "
                "AND (data_validade IS NULL OR data_validade >= current_date)")
        vencidos = await _scalar(
            db, "WITH ultimo_aso AS (SELECT DISTINCT ON (a.employee_id) a.employee_id, a.data_validade "
                "FROM gp_asos a WHERE a.data_validade IS NOT NULL ORDER BY a.employee_id, a.data_validade DESC) "
                "SELECT count(*) FROM ultimo_aso u JOIN employees e ON e.id=u.employee_id AND e.status='ativo' "
                "WHERE u.data_validade < current_date")
        ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        if "exames" in out and isinstance(out["exames"], dict):
            out["exames"].setdefault("panelGrid", "1fr")
            out["exames"]["panels"] = [{"title": "Regularização PCMSO (por colaborador ativo)", "rows": [
                {"left": "ASOs válidos", "right": str(validos or 0), **S["ok"]},
                {"left": "Colaboradores com ASO vencido", "right": str(vencidos or 0), **S["bad"]},
                {"left": "Pendentes (sem ASO válido)", "right": str(max(0, (ativos or 0) - (validos or 0))), **S["warn"]},
            ]}]
    except Exception:  # noqa: BLE001
        pass

    return out
