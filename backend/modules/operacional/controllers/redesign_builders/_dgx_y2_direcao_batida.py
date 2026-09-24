"""DGX Y2 — a direção da batida: as duas réguas lado a lado (24/09/2026).

Duas abas em **g-ponto**: `ponto-divergencia-regua` (a evidência) e
`ponto-divergencia-regua-apurar` (o form que recalcula). Ambas leem/escrevem só
`ponto_divergencia_regua`, a tabela que `ponto/services/divergencia_regua.py` mantém —
**paralelo cego: nada aqui muda um minuto de folha, de espelho ou da tela de ponto**.

É a tela que o dono abre para decidir a §7.1 da `DGX_X4_pareador_unico.md` com evidência, não
com opinião: para cada pessoa×dia em que as duas réguas discordam, as batidas CRUAS (hora e
tipo), o que cada régua concluiu (pares e horas), a diferença, a causa provável e — quando há
turno lançado — qual das duas chega perto da jornada planejada.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` no FIM do `build()`; as abas ficam no FIM do g-ponto em `_dp_grupos`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesma mina de import circular da F1/W5/X2)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import _helpers, b, t  # noqa: E402
from modules.people_management.ponto.services.divergencia_regua import (  # noqa: E402
    TOL_REALIDADE_H,
    _br,
    _ensure,
    apurar,
    competencia_iso,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

ABAS = (
    ("ponto-divergencia-regua", "Direção da batida: A × B"),
    ("ponto-divergencia-regua-apurar", "Apurar direção da batida"),
)

#: Rótulo humano de cada causa e a cor do selo.
CAUSA_LABEL = {
    "tipo_errado_no_aparelho": ("tipo errado no aparelho", "bad"),
    "batida_faltando": ("batida faltando", "warn"),
    "batida_duplicada": ("batida duplicada", "warn"),
    "virada_de_meia_noite": ("virada de meia-noite", "mut"),
    "indeterminado": ("indeterminado", "mut"),
}

ACERTA_LABEL = {
    "A": ("régua A (folha)", "ok"),
    "B": ("régua B (tela)", "ok"),
    "empate": ("as duas batem", "ok"),
    "ambas_erram": ("as DUAS erram", "bad"),
    "sem_turno": ("sem turno lançado", "mut"),
}

_SQL_LINHAS = """
SELECT competencia, employee_id, employee_nome, dia, batidas, pares_a, horas_a, detalhe_a,
       pares_b, horas_b, detalhe_b, delta_h, causa, quem_acerta, mais_perto, horas_planejadas,
       observacao
  FROM ponto_divergencia_regua
 ORDER BY competencia DESC, abs(delta_h) DESC, employee_nome, dia
"""

#: competências com batida — as opções do form de apuração
_SQL_COMPS = """
SELECT DISTINCT to_char(punch_timestamp, 'YYYY-MM') FROM gp_clock_punches
 WHERE punch_timestamp >= now() - interval '18 months'
 ORDER BY 1 DESC LIMIT 18
"""


def _h(v) -> str:
    """Horas em `NNhMM` — o formato que o DP lê no espelho."""
    f = float(v or 0)
    sinal = "-" if f < 0 else ""
    f = abs(f)
    return f"{sinal}{int(f)}h{int(round((f - int(f)) * 60)):02d}"


def _batidas_txt(bat: list, dia: date) -> str:
    """As batidas cruas numa linha: `19:00 entrada · +00:00 saída · +01:00 saída*`.

    O `+` marca a batida do dia CIVIL seguinte — num plantão noturno metade das batidas é do
    dia seguinte, e sem a marca a linha parece fora de ordem. O `*` marca a batida que ABRIU
    par na régua A e a régua B recusou: é o mecanismo da divergência aparecendo na própria
    evidência, não numa nota de rodapé.
    """
    dd = dia.strftime("%d/%m")
    out = []
    for x in bat or []:
        tipo = (x.get("tipo") or "?").replace("_", " ")
        marca = "*" if x.get("abre_a") and not x.get("par_b") else ""
        hora = x.get("hora") or "?     "
        out.append(f"{'' if hora[:5] == dd else '+'}{hora[6:]} {tipo}{marca}")
    return " · ".join(out) or "—"


async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, _safe, _tbl = _helpers(db)

    linhas = [dict(r) for r in (await db.execute(text(_SQL_LINHAS))).mappings().all()]
    comps = [c for (c,) in (await db.execute(text(_SQL_COMPS))).all()]
    apuradas = sorted({ln["competencia"] for ln in linhas}, reverse=True)

    por_causa: dict[str, list[float]] = {}
    for ln in linhas:
        d = por_causa.setdefault(ln["causa"], [0, 0.0])
        d[0] += 1
        d[1] += abs(float(ln["delta_h"]))
    acerta: dict[str, int] = {}
    perto = {"A": 0, "B": 0}
    soma = 0.0
    for ln in linhas:
        acerta[ln["quem_acerta"]] = acerta.get(ln["quem_acerta"], 0) + 1
        if ln["mais_perto"] in perto:
            perto[ln["mais_perto"]] += 1
        soma += abs(float(ln["delta_h"]))
    pessoas = len({ln["employee_id"] for ln in linhas})

    resumo_causas = " · ".join(
        f"**{CAUSA_LABEL.get(c, (c, 'mut'))[0]}** {v[0]} dia(s), {_h(v[1])}"
        for c, v in sorted(por_causa.items(), key=lambda kv: -kv[1][1])
    )

    def _linha(r: dict) -> dict:
        causa_lbl, causa_cor = CAUSA_LABEL.get(r["causa"], (r["causa"], "mut"))
        ac_lbl, ac_cor = ACERTA_LABEL.get(r["quem_acerta"], (r["quem_acerta"], "mut"))
        d = float(r["delta_h"])
        return {
            "cells": [
                t(r["employee_nome"], 700, _ND),
                t(f"{r['dia'].strftime('%d/%m/%Y')}"),
                t(_batidas_txt(r["batidas"], r["dia"])),
                t(f"{_h(r['horas_a'])} ({r['pares_a']} par)", 700, _ND),
                t(f"{_h(r['horas_b'])} ({r['pares_b']} par)", 700, _ND),
                t(_h(d), 700, "#B91C1C" if abs(d) >= 1 else "#B45309"),
                t(_h(r["horas_planejadas"]) if r["horas_planejadas"] is not None else "—"),
                b(causa_lbl, causa_cor),
                b(ac_lbl, ac_cor),
            ],
            "docs": [
                {"label": "O que explica", "value": r["observacao"] or "—"},
                {
                    "label": "Régua A — cronológica (folha e fechamento)",
                    "value": " · ".join(f"{x['entrada']}→{x['saida']} = {x['horas']}h" for x in (r["detalhe_a"] or []))
                    or "nenhum par fechado",
                },
                {
                    "label": "Régua B — com direção (tela de ponto do DP)",
                    "value": " · ".join(
                        f"{x['entrada']}→{x['saida']} = {x['horas']}h"
                        + (" (com intervalo)" if x.get("intervalo") else "")
                        for x in (r["detalhe_b"] or [])
                    )
                    or "nenhum par fechado",
                },
                {
                    "label": "Mais perto da jornada planejada",
                    "value": {"A": "régua A", "B": "régua B"}.get(r["mais_perto"], "empate ou sem turno")
                    + " — desempate FRACO: chegar mais perto não é acertar.",
                },
            ],
            "filtro": {
                "Competência": _br(r["competencia"]),
                "Causa": causa_lbl,
                "Quem acerta": ac_lbl,
            },
        }

    mine["ponto-divergencia-regua"] = {
        "title": "Direção da batida: régua A (folha) × régua B (tela de ponto)",
        "sub": (
            f"**{len(linhas)} pessoa×dia** em que as duas réguas de pareamento discordam da HORA, "
            f"{pessoas} pessoa(s), Σ|Δ| **{_h(soma)}**"
            + (f" · competências apuradas: {', '.join(_br(c) for c in apuradas)}" if apuradas else "")
            + ". A régua A (`horas_service.parear_batidas`, a da FOLHA e do FECHAMENTO) ignora o "
            "`punch_type` de propósito — batida de noturno vem tipada errada com frequência. A régua B "
            "(`time_record_service._pair_punches`, a da TELA DE PONTO) tem a regra dura «saída não abre "
            "turno», que existe para não inventar 12 h de trabalho sobre o período de descanso. As duas "
            "nasceram de defeito real e cada uma acerta em dias diferentes. **Esta tela não escolhe e não "
            "muda nada** — mede, mostra a batida crua e diz a causa provável. "
            + (f"Por causa: {resumo_causas}. " if resumo_causas else "")
            + f"Quando há turno lançado, ganha a régua que fica a menos de {TOL_REALIDADE_H:.0f} h da "
            f"jornada planejada: régua A em {acerta.get('A', 0)}, régua B em {acerta.get('B', 0)}, "
            f"empate em {acerta.get('empate', 0)} — e **as DUAS erram em {acerta.get('ambas_erram', 0)}**, "
            f"{acerta.get('sem_turno', 0)} sem turno lançado. O `*` na coluna das batidas marca a batida "
            f"que a régua A usou para abrir turno e a régua B recusou."
            + ("" if linhas else " Nada apurado ainda — use a aba «Apurar direção da batida».")
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa, causa…",
        "grid": "1.5fr 0.8fr 2.6fr 1fr 1fr 0.7fr 0.8fr 1.3fr 1.2fr",
        "cols": [
            "Pessoa",
            "Dia",
            "Batidas cruas (hora · tipo)",
            "Régua A — folha",
            "Régua B — tela",
            "Δ",
            "Planejado",
            "Causa provável",
            "Quem bate com a realidade",
        ],
        "rows": [_linha(r) for r in linhas],
    }

    mine["ponto-divergencia-regua-apurar"] = {
        "title": "Apurar direção da batida",
        "sub": (
            "Roda as DUAS réguas sobre as mesmas batidas de uma competência e grava o que elas "
            "concluíram, dia a dia, em `ponto_divergencia_regua`. **Nenhum holerite, espelho ou "
            "registro de ponto é tocado** — a tabela existe só para ser lida por gente. Rodar duas "
            "vezes dá exatamente o mesmo resultado."
        ),
        "cta": "Apurar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "ponto-divergencia-regua-apurar",
            "okMsg": "Apurado — veja a aba «Direção da batida: A × B».",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência",
                "type": "select",
                "span": 2,
                "options": [{"value": c, "label": _br(c)} for c in comps],
                "value": comps[0] if comps else "",
            }
        ],
    }

    # a frente roda DEPOIS de `montar_grupos`: anexa as abas ao fim do g-ponto
    grupo = (out or {}).get("g-ponto")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-ponto", tid)
    if out is not None:
        out.update(mine)
    return mine


@router.post("/action/ponto-divergencia-regua-apurar")
async def rd_ponto_divergencia_regua_apurar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Reapura a competência. Escreve SÓ em `ponto_divergencia_regua` — paralelo cego."""
    try:
        comp = competencia_iso(payload.get("competencia") or "")
    except (ValueError, IndexError, AttributeError):
        raise HTTPException(status_code=400, detail="Competência: use MM/AAAA (ex.: 09/2026).") from None
    if comp > f"{date.today():%Y-%m}":
        raise HTTPException(status_code=400, detail=f"{_br(comp)} ainda não aconteceu.")
    r = await apurar(db, comp)
    causas = ", ".join(
        f"{CAUSA_LABEL.get(c, (c, ''))[0]}: {v['dias']} dia(s)/{v['horas']}h"
        for c, v in r["por_causa"].items()
        if v["dias"]
    )
    return {
        "ok": True,
        "message": (
            f"{_br(comp)}: {r['pessoas_com_batida']} pessoa(s) com batida, {r['pessoas_divergentes']} "
            f"com divergência de hora entre as duas réguas, em {r['dias_divergentes']} dia(s) — "
            f"Σ|Δ| {r['soma_abs_horas']} h. {causas or 'nenhuma divergência'}. "
            f"Quem bate com a jornada planejada: régua A {r['quem_acerta']['A']}, régua B "
            f"{r['quem_acerta']['B']}, empate {r['quem_acerta']['empate']}, as duas erram "
            f"{r['quem_acerta']['ambas_erram']}, sem turno {r['quem_acerta']['sem_turno']}. "
            f"Nenhum holerite, espelho ou registro de ponto foi tocado."
        ),
        "result": r,
    }
