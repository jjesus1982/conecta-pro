"""
redesign_builders/agendador.py — T4 (módulo NOVO, sem base no monólito).
Visibilidade do agendador de jobs (scheduler_tasks/executions). Só leitura.
Vazio real = "aguardando dado" — nunca fabricar.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "agendador"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    n_task = await _scalar(db, "SELECT count(*) FROM scheduler_tasks")
    n_exec = await _scalar(db, "SELECT count(*) FROM scheduler_executions")

    # ---- Visão geral (dash real de contagens) ----
    out["visao"] = {
        "title": "Agendador", "sub": "Jobs agendados e execuções — dados reais", "cta": "—", "type": "dash", "panelGrid": "1fr",
        "kpis": [
            {"v": str(n_task or 0), "l": "Tarefas agendadas", "icon": "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18", "color": "#0F1B3A"},
            {"v": str(n_exec or 0), "l": "Execuções registradas", "icon": "M3 3v18h18M7 14l3-3 3 3 5-6", "color": "#16A34A"},
        ],
        "panels": [
            {"title": "Estado", "rows": [{"left": "Fila de agendamento", "right": ("Vazia (aguardando dado)" if not n_task else f"{n_task} tarefas"),
                                          "color": "#64748B", "bg": "#F1F4FA"}]},
        ],
    }

    # ---- Tarefas (scheduler_tasks — honesto se vazio) ----
    await safe("tarefas", tbl(
        "Tarefas agendadas", f"{n_task or 0} tarefas (aguardando dado se vazio)",
        "—", ["Nome", "Tipo", "Categoria", "Cron", "Status"], "2fr 1fr 1fr 1.2fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(task_type::text,'—'), coalesce(category::text,'—'), coalesce(cron_expression,'—'), coalesce(status::text,'—') "
        "FROM scheduler_tasks ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').replace('_', ' ').capitalize(), "info"),
                   t((r[2] or '—').capitalize()), t(r[3]), b((r[4] or '—').capitalize(), "mut")]))

    # ---- Execuções (scheduler_executions — honesto se vazio) ----
    await safe("execucoes", tbl(
        "Execuções", f"{n_exec or 0} execuções (aguardando dado se vazio)",
        "—", ["Nº execução", "Status", "Iniciada", "Concluída", "Duração"], "1fr 1fr 1.2fr 1.2fr 1fr",
        "SELECT execution_number, coalesce(status::text,'—'), started_at, completed_at, duration_seconds "
        "FROM scheduler_executions ORDER BY started_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(str(r[0]) if r[0] is not None else '—', 600, "#0F1B3A"),
                   b((r[1] or '—').capitalize(), "info"), t(_fmtdate(r[2])), t(_fmtdate(r[3])),
                   t(f"{float(r[4]):.1f}s" if r[4] is not None else '—')]))

    return out
