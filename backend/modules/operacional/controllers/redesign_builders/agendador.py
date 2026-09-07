"""Agendador — o que REALMENTE roda: o `beat_schedule` do Celery e as falhas que chegaram ao sino.

Antes lia `scheduler_tasks`/`scheduler_executions`, cinco tabelas que nunca receberam uma linha
(0 registros em 07/09/2026) enquanto o beat rodava 141 tarefas — a tela dizia "fila vazia" para
um agendador em plena atividade. Não existe registro de execução bem-sucedida (o Celery não
guarda resultado aqui); o que existe de verdade é: a grade declarada e as falhas (task_failure e
retorno ok=False) que `task_falha` grava no sino. É isso que a tela mostra.
"""
from __future__ import annotations

import logging

from modules.operacional.controllers.redesign_data_controller import (
    _fmtdate,
    _helpers,
    _scalar,
    b,
    t,
)

logger = logging.getLogger(__name__)

_SINO_FALHAS = "FROM communication_notifications WHERE title LIKE 'Tarefa agendada%%'"


def _agenda_str(sch) -> str:
    """crontab → 'm h dM M dS'; intervalo → 'a cada Ns'. Sem inventar: o que não reconhece, repr."""
    for attrs in (("_orig_minute", "_orig_hour", "_orig_day_of_month", "_orig_month_of_year", "_orig_day_of_week"),):
        if all(hasattr(sch, a) for a in attrs):
            return " ".join(str(getattr(sch, a)) for a in attrs)
    seg = getattr(sch, "run_every", None)
    if seg is not None:
        s = int(getattr(seg, "total_seconds", lambda: seg)())
        return f"a cada {s // 3600}h" if s % 3600 == 0 else f"a cada {s // 60}min" if s % 60 == 0 else f"a cada {s}s"
    if isinstance(sch, (int, float)):
        return f"a cada {int(sch)}s"
    return repr(sch)[:40]


def _grade() -> list[tuple[str, str, str, str]]:
    try:
        from celery_app import app  # noqa: PLC0415 — a grade mora no processo, não no banco
        sched = app.conf.beat_schedule or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[agendador] beat_schedule indisponível: %s", exc)
        return []
    return sorted((nome, str(cfg.get("task", "—")), _agenda_str(cfg.get("schedule")),
                   str((cfg.get("options") or {}).get("queue") or "celery")) for nome, cfg in sched.items())


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    grade = _grade()
    filas = sorted({g[3] for g in grade})
    f7 = await _scalar(db, f"SELECT count(*) {_SINO_FALHAS} AND created_at > now() - interval '7 days'") or 0
    f24 = await _scalar(db, f"SELECT count(*) {_SINO_FALHAS} AND created_at > now() - interval '24 hours'") or 0
    ult = await _scalar(db, f"SELECT max(created_at) {_SINO_FALHAS}")

    out["visao"] = {
        "title": "Agendador", "sub": "Grade do Celery beat (declarada no código) e falhas que chegaram ao sino",
        "cta": "—", "type": "dash", "panelGrid": "1fr 1fr",
        "kpis": [
            {"v": str(len(grade)), "l": "Tarefas na grade (beat)", "icon": "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18", "color": "#0F1B3A"},
            {"v": str(len(filas)), "l": "Filas", "icon": "M3 3v18h18M7 14l3-3 3 3 5-6", "color": "#0F1B3A"},
            {"v": str(f24), "l": "Falhas 24h", "icon": "M12 9v4m0 4h.01M12 2 2 20h20L12 2z", "color": "#C2410C" if f24 else "#16A34A"},
            {"v": str(f7), "l": "Falhas 7 dias", "icon": "M12 9v4m0 4h.01M12 2 2 20h20L12 2z", "color": "#B45309" if f7 else "#16A34A"},
        ],
        "panels": [
            {"title": "Por fila", "rows": [{"left": f, "right": f"{sum(1 for g in grade if g[3] == f)} tarefas",
                                            "color": "#0F1B3A", "bg": "#F1F4FA"} for f in filas]
             or [{"left": "Grade indisponível neste processo", "right": "—", "color": "#64748B", "bg": "#F1F4FA"}]},
            {"title": "Estado", "rows": [
                {"left": "Última falha no sino", "right": _fmtdate(ult) if ult else "nenhuma", "color": "#64748B", "bg": "#F1F4FA"},
                {"left": "Execuções bem-sucedidas", "right": "não são registradas (Celery sem backend de resultado)",
                 "color": "#64748B", "bg": "#F1F4FA"},
            ]},
        ],
    }

    out["tarefas"] = {
        "title": "Tarefas agendadas", "sub": f"{len(grade)} entradas do beat_schedule — minuto hora dia-mês mês dia-semana",
        "cta": "—", "type": "table", "cols": ["Nome", "Task", "Agenda", "Fila"], "grid": "2fr 2fr 1.4fr 1fr",
        "rows": [{"cells": [t(n, 600, "#0F1B3A"), t(tk), t(ag), b(q, "info")]} for n, tk, ag, q in grade],
    }

    await safe("execucoes", tbl(
        "Falhas de execução", f"{f7} nos últimos 7 dias — o que task_failure / retorno ok=False mandou ao sino",
        "—", ["Quando", "Tarefa", "Erro", "Lida"], "1fr 1.6fr 3fr 0.6fr",
        f"SELECT created_at, title, coalesce(body,'—'), read_at IS NOT NULL {_SINO_FALHAS} ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(_fmtdate(r[0]), 600, "#0F1B3A"), t((r[1] or "—").replace("Tarefa agendada falhou: ", "").replace("Tarefa agendada devolveu falha: ", "")[:60]),
                   t((r[2] or "—")[:160]), b("sim", "ok") if r[3] else b("não", "warn")]))
    return out
