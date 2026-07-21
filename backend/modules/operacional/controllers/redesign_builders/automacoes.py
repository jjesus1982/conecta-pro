"""Redesign builder — Automações (NOVO módulo; era 100% mock).

Liga visao·workflows·execucoes lendo as tabelas reais de automação
(crm_workflows, crm_workflow_runs). Tabelas de workflow de IA (ai_workflows*)
estão vazias no clássico; uso as de CRM que têm dado real.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _helpers,
    b,
    t,
)

SLUG = "automacoes"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y %H:%M"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "success", "sucesso", "ok", "done"):
        return b(v or "—", "ok")
    if s in ("pendente", "rodando", "running", "aguardando", "queued", "em_andamento"):
        return b(v or "—", "warn")
    if s in ("inativo", "erro", "error", "failed", "falhou", "cancelado"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Visão — resumo real (workflows + execuções)
    await safe("visao", tbl(
        "Visão geral", "Resumo de automações", "—",
        ["Métrica", "Total"],
        "2fr 1fr",
        "SELECT 'Workflows', count(*)::text FROM crm_workflows "
        "UNION ALL SELECT 'Workflows ativos', count(*)::text FROM crm_workflows WHERE coalesce(is_active,false) "
        "UNION ALL SELECT 'Execuções', count(*)::text FROM crm_workflow_runs",
        lambda r: [t(r[0], 600, _ND), t(r[1], 600)]))

    # 2) Workflows — crm_workflows
    await safe("workflows", tbl(
        "Workflows", "Automações configuradas", "Novo workflow",
        ["Nome", "Gatilho", "Execuções", "Última execução", "Ativo"],
        "1.8fr 1.4fr 0.9fr 1.2fr 0.7fr",
        "SELECT coalesce(name,'—'), coalesce(trigger_event,'—'), coalesce(run_count,0), "
        "last_run_at, coalesce(is_active,false) FROM crm_workflows ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t((r[1] or "—").replace("_", " ")), t(str(r[2])),
                   t(_d(r[3])), (b("Ativo", "ok") if r[4] else b("—", "mut"))]))

    # 3) Execuções — crm_workflow_runs
    await safe("execucoes", tbl(
        "Execuções", "Histórico de execuções", "—",
        ["Entidade", "ID", "Status", "Detalhe", "Quando"],
        "1.2fr 1.4fr 0.9fr 2fr 1.2fr",
        "SELECT coalesce(entity_type,'—'), coalesce(entity_id::text,'—'), coalesce(status::text,'—'), "
        "coalesce(left(detail::text,90),'—'), created_at FROM crm_workflow_runs ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0], 600, _ND), t((r[1] or "—")[:24]), _bs(r[2]), t(r[3]), t(_d(r[4]))]))

    return out
