"""Frente 4 — GRID real/contratual (cliente/posto × dia do mês) e MAPA DE PONTO de hoje com os
cinco estados. Telas genéricas do redesign (`table`), sem editar frontend.

Toda a régua mora em `people_management/ponto/mapa_de_ponto.py` (a mesma que a triagem e o
quadro ao vivo usam). Aqui só se pinta. Cada tela carrega `_meta` com os itens crus para os
oráculos compararem contra as fontes — o frontend ignora a chave.

Falha aqui NÃO cala: a tela aparece com o erro no título, em vez de sumir do menu.
"""
from __future__ import annotations

import logging
from datetime import datetime

from modules.operacional.controllers.redesign_data_controller import b, t
from modules.people_management.ponto import mapa_de_ponto as regua

logger = logging.getLogger(__name__)

_TONE = {"ok": "ok", "atendido_com_atraso": "warn", "atendido_posto_incorreto": "bad",
         "atendido_fora_de_escala": "info", "descoberto": "bad"}

# ponytail: cache de 60 s em memória do processo. A tela do mês lê ~800 turnos + ~2.000
# batidas; medido em 0,3 s no staging, então o cache é seguro de sobra, não necessidade.
# Cada worker tem o seu — quem quiser um só, materializa no banco.
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_S = 60


async def _cacheado(chave: str, coro_fn):
    import time as _time

    agora = _time.monotonic()
    hit = _CACHE.get(chave)
    if hit and agora - hit[0] < _TTL_S:
        return hit[1]
    val = await coro_fn()
    if len(_CACHE) > 8:
        _CACHE.clear()
    _CACHE[chave] = (agora, val)
    return val


def _onde(i: dict) -> str:
    if i.get("estado") == "descoberto":
        return "—"
    if i.get("dentro_geofence") is True:
        return "no posto"
    if i.get("posto_geofence") and i.get("posto_geofence") != i.get("post_id"):
        return f"geofence de OUTRO posto · {i.get('dist_m') or '?'} m"
    if i.get("dist_m") is not None:
        return f"fora de qualquer geofence · {i['dist_m']} m"
    return "sem posição" if i.get("batida_em") else "—"


def _tela_mapa(m: dict) -> dict:
    listados = [i for i in m["itens"] if i["estado"]] + m["fora_de_escala"]
    cont = {e: sum(1 for i in listados if i["estado"] == e) for e in regua.ESTADOS}
    rows = [{"cells": [
        t(i["posto"], 600, "#0F1B3A"), t(i["turno"]), t(i["nome"], 600, "#0F1B3A"),
        b(i["estado"].replace("_", " "), _TONE[i["estado"]]),
        t(i["batida_em"][11:16] if i["batida_em"] else "—", 600),
        t(_onde(i)),
    ], "filtro": i["posto"]} for i in sorted(listados, key=lambda x: (x["posto"], x["turno"], x["nome"]))]
    dia = datetime.fromisoformat(m["dia"])
    excl = m["excluidos"]
    sub = (f"{dia:%d/%m} às {m['agora'][11:16]} · {len(m['itens'])} turno(s) na escala · "
           f"ok {cont['ok']} · atraso {cont['atendido_com_atraso']} · posto incorreto {cont['atendido_posto_incorreto']} · "
           f"fora de escala {cont['atendido_fora_de_escala']} · descoberto {cont['descoberto']} · "
           f"ainda não venceram {m['nao_vencidos']}")
    if excl:
        sub += (f" · ⚠ {len(excl)} turno(s) de gente de férias/afastada/saindo, NÃO cobrados: "
                + "; ".join(f"{x['nome'].title()} ({x['posto']} {x['turno']})" for x in excl[:5]))
    tol = m["tolerancia_padrao_min"]
    sub += (f" · tolerância {tol} min" + (" (do banco)" if m["tolerancia_do_banco"] else " (quadro ao vivo; banco sem valor)")
            + " · fonte: shifts × gp_clock_punches × posts, régua = presença ao vivo + coorte do ponto")
    return {"title": "Mapa de ponto — hoje", "sub": sub, "cta": "—", "type": "table",
            "searchHint": "Buscar posto ou colaborador…", "grid": "1.6fr 0.8fr 1.6fr 1.2fr 0.6fr 1.4fr",
            "cols": ["Posto", "Turno", "Colaborador", "Estado", "Batida", "Onde"],
            "rows": rows or [{"cells": [t("Nenhum turno na escala de hoje", 500), t("—"), t("—"), t("—"), t("—"), t("—")]}],
            "_meta": m}


def _tela_grade(g: dict) -> dict:
    de, ate = datetime.fromisoformat(g["de"]), datetime.fromisoformat(g["ate"])
    dias = [f"{de.year}-{de.month:02d}-{d:02d}" for d in range(1, ate.day + 1)]
    rows = []
    for p in g["postos"]:
        cells = [t(f"{p['cliente'].title()} · {p['posto']}", 600, "#0F1B3A")]
        tot_r = tot_c = 0
        for d in dias:
            c = p["dias"].get(d)
            if not c:
                cells.append(t("·", 400, "#CBD5E1"))
                continue
            tot_c += c["contratual"]
            tot_r += c["real"]
            if d > g["hoje"]:
                cells.append(t(f"—/{c['contratual']}", 400, "#94A3B8"))
            elif c["descoberto"]:
                cells.append(b(f"{c['real']}/{c['contratual']}", "bad"))
            elif c["pendente"]:
                cells.append(t(f"{c['real']}/{c['contratual']}", 500, "#64748B"))
            else:
                cells.append(t(f"{c['real']}/{c['contratual']}", 500, "#16A34A"))
        cells.append(t(f"{tot_r}/{tot_c}", 600, "#0F1B3A"))
        rows.append({"cells": cells, "filtro": p["cliente"].title()})
    n_desc = sum(c["descoberto"] for p in g["postos"] for c in p["dias"].values())
    return {"title": "Grid real/contratual", "cta": "—", "type": "table",
            "sub": (f"{de:%m/%Y} · {len(g['postos'])} posto(s) · real/contratual por dia · vermelho = turno descoberto "
                    f"({n_desc} no mês até hoje) · cinza = ainda não venceu · —/N = futuro · fonte: shifts × gp_clock_punches, "
                    "régua = presença ao vivo + coorte do ponto (férias/afastado não contam)"),
            "searchHint": "Buscar cliente ou posto…",
            "grid": "2.4fr " + " ".join(["0.5fr"] * len(dias)) + " 0.7fr",
            "cols": ["Cliente · Posto"] + [d[-2:] for d in dias] + ["Mês"],
            "rows": rows or [{"cells": [t("Nenhum turno na escala do mês", 500)] + [t("·")] * (len(dias) + 1)}],
            "_meta": g}


def _falhou(titulo: str, exc: Exception) -> dict:
    logger.error("frente 4: %s falhou: %s", titulo, exc, exc_info=True)
    return {"title": f"{titulo} — FALHOU", "sub": f"{type(exc).__name__}: {str(exc)[:300]}", "cta": "—",
            "type": "table", "searchHint": "", "grid": "1fr", "cols": ["Erro"],
            "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}]}


async def telas(db) -> dict:
    out: dict = {}
    agora = regua.agora_manaus()
    try:
        out["mapa-de-ponto"] = _tela_mapa(await _cacheado(f"mapa:{agora:%Y-%m-%d %H:%M}", lambda: regua.mapa_do_dia(db, agora=agora)))
    except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
        await db.rollback()
        out["mapa-de-ponto"] = _falhou("Mapa de ponto", exc)
    try:
        out["grid-real-contratual"] = _tela_grade(await _cacheado(
            f"grade:{agora:%Y-%m-%d %H:%M}", lambda: regua.grade_do_mes(db, agora.year, agora.month, agora=agora)))
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        out["grid-real-contratual"] = _falhou("Grid real/contratual", exc)
    return out
