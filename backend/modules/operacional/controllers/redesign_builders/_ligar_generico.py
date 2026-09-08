"""Helpers para ligar rotas que só existiam por API (revisão 100%, 08/09/2026).

`chamar(fn, db, **kw)` chama um handler de controller direto (sem HTTP), entregando sessão async ou
síncrona conforme a assinatura e descartando kwargs que a função não aceita. `tabela_de_lista` e
`painel_de_dict` transformam a resposta (lista de dicts / dict) em tela do redesign sem conhecer o
formato de antemão — o dado é REAL (vem do mesmo código da API), só a moldura é genérica."""
from __future__ import annotations

import inspect
import logging
from typing import Any

from modules.operacional.controllers.redesign_data_controller import S, b, brl, t

logger = logging.getLogger(__name__)


async def chamar(fn, db, **kw) -> Any:
    sig = inspect.signature(fn)
    args: dict[str, Any] = {}
    sync_sess = None
    for name, p in sig.parameters.items():
        ann = str(p.annotation)
        if name in ("db", "session"):
            if "AsyncSession" in ann or ann in ("<class 'inspect._empty'>", "inspect._empty"):
                args[name] = db
            else:
                from core.database.session import SyncSessionLocal
                sync_sess = SyncSessionLocal()
                args[name] = sync_sess
        elif name in kw:
            args[name] = kw[name]
        elif name in ("current_user", "user", "_user", "_u", "_"):
            args[name] = kw.get("current_user") or {"id": None, "role": "admin"}
        elif p.default is inspect._empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            args[name] = None
    try:
        res = fn(**args)
        if inspect.isawaitable(res):
            res = await res
    finally:
        if sync_sess is not None:
            sync_sess.close()
    if hasattr(res, "model_dump"):
        res = res.model_dump()
    return res


def _fmt(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, float):
        return brl(v) if abs(v) >= 100 else f"{v:.2f}".replace(".", ",")
    if isinstance(v, (list, dict)):
        return f"{len(v)} item(ns)"
    return str(v)[:60]


def _lista_em(res, chaves=("items", "itens", "dados", "data", "results", "lista", "rows", "consultas", "prazos", "pendencias", "condominios")):
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in chaves:
            if isinstance(res.get(k), list):
                return res[k]
        for v in res.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def tabela_de_lista(title: str, sub: str, res, cols: list[str] | None = None, max_cols: int = 7,
                    actionsfn=None, docsfn=None) -> dict:
    """Lista de dicts → tela 'table'. Colunas = as primeiras chaves escalares do 1º item."""
    itens = [x for x in _lista_em(res) if isinstance(x, dict)]
    if not cols:
        cols = [k for k, v in (itens[0].items() if itens else []) if not isinstance(v, (list, dict))][:max_cols]
    cols = cols or ["Resultado"]
    rows = []
    for it in itens[:300]:
        cells = [t(_fmt(it.get(c)), 600 if i == 0 else 500, "#0F1B3A" if i == 0 else "#334155") for i, c in enumerate(cols)]
        row = {"cells": cells}
        if docsfn:
            row["docs"] = [d for d in (docsfn(it) or []) if d]
        if actionsfn:
            row["actions"] = [a for a in (actionsfn(it) or []) if a]
        rows.append(row)
    if not itens and isinstance(res, dict):
        rows = [{"cells": [t(f"{k}: {_fmt(v)}", 500)]} for k, v in res.items() if not isinstance(v, (list, dict))][:20]
        cols = ["Resultado"]
    grid = " ".join(["1.4fr"] + ["1fr"] * (len(cols) - 1))
    return {"title": title, "sub": sub, "cta": "—", "type": "table", "searchHint": "Buscar…",
            "grid": grid, "cols": [c.replace("_", " ").capitalize() for c in cols], "rows": rows}


def painel_de_dict(title: str, sub: str, res, kpis_de: list[str] | None = None) -> dict:
    """Dict → tela 'dash': escalares viram linhas; até 4 viram KPI."""
    res = res if isinstance(res, dict) else {"resultado": res}
    escalares = [(k, v) for k, v in res.items() if not isinstance(v, (list, dict)) and not str(k).startswith("_")]
    kpis_keys = kpis_de or [k for k, _ in escalares[:4]]
    kpis = [{"v": _fmt(res.get(k)), "l": str(k).replace("_", " ").capitalize(), "icon": "M3 3v18h18", "color": "#0F1B3A"} for k in kpis_keys if k in res]
    panels = [{"title": "Detalhe", "rows": [{"left": str(k).replace("_", " ").capitalize(), "right": _fmt(v), **S["mut"]} for k, v in escalares] or [{"left": "—", "right": "sem dado", **S["mut"]}]}]
    for k, v in res.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            panels.append({"title": str(k).replace("_", " ").capitalize(), "rows": [
                {"left": " · ".join(f"{kk}: {_fmt(vv)}" for kk, vv in list(it.items())[:4] if not isinstance(vv, (list, dict)))[:120],
                 "right": "", **S["info"]} for it in v[:30]]})
        elif isinstance(v, dict) and v:
            panels.append({"title": str(k).replace("_", " ").capitalize(), "rows": [
                {"left": str(kk).replace("_", " ").capitalize(), "right": _fmt(vv), **S["mut"]} for kk, vv in v.items() if not isinstance(vv, (list, dict))][:30]})
    return {"title": title, "sub": sub, "type": "dash", "panelGrid": "1fr 1fr", "kpis": kpis, "panels": panels}


def selecionar(key, label, options, span="span 2", ph="Selecione"):
    return {"key": key, "label": label, "type": "select", "span": span, "ph": ph, "options": options}


def badge_status(v: str) -> dict:
    s = (v or "—").lower()
    tone = "ok" if s in ("ok", "ativo", "active", "concluida", "concluída", "sucesso", "assinado", "entregue", "valida", "válida") else \
        "bad" if s in ("erro", "vencido", "vencida", "cancelada", "cancelado", "critico", "crítico") else \
        "warn" if s in ("pendente", "agendada", "aberto", "em_andamento", "parcial") else "info"
    return b((v or "—").replace("_", " ").capitalize(), tone)
