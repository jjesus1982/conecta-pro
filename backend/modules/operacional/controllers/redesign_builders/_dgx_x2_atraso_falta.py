"""DGX X2 — conferência ponto × folha: atraso e falta justificada (24/09/2026).

Três abas em **g-folha**: `atraso-conferencia`, `falta-justificada-conferencia` e o form
`ponto-folha-apurar`. Todas leem `ponto_folha_conferencia`, a tabela que
`folha/services/atraso_falta_conferencia.py` escreve — **paralelo cego: nada aqui muda um
centavo da folha**, e as telas dizem isso em letras claras.

O R$ é ESTIMATIVA: minutos além da tolerância × valor-hora do holerite da própria pessoa
(base ÷ divisor da escala). Não é conta a pagar nem a receber — é a medida de uma lacuna.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` no FIM do `build()`; as abas ficam no FIM do g-folha em `_dp_grupos`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesma mina de import circular da F1/W5)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402
from modules.people_management.folha.services.atraso_falta_conferencia import (  # noqa: E402
    FRACAO_ENTRADA_AUSENTE,
    _ensure,
    apurar,
    competencia_iso,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

#: As abas, na ordem. Também listadas em `_dp_grupos.GRUPOS` (g-folha) para a composição do grupo
#: ficar num lugar só — mas quem as ANEXA é o bloco no fim de `telas()`, porque a frente roda
#: depois de `montar_grupos`.
ABAS = (
    ("atraso-conferencia", "Atraso: conferência"),
    ("falta-justificada-conferencia", "Falta justificada: conferência"),
    ("ponto-folha-apurar", "Apurar conferência ponto × folha"),
)

_SQL_LINHAS = """
SELECT competencia, tipo, employee_id, employee_nome, ponto_qtd, ponto_qtd_util,
       ponto_qtd_descartada, unidade, valor_hora, valor_estimado, folha_qtd, folha_valor,
       divergente, sentido, observacao, detalhe, apurado_em
  FROM ponto_folha_conferencia
 ORDER BY competencia DESC, valor_estimado DESC, employee_nome
"""

#: competências que o motor próprio emitiu — as opções do form de apuração
_SQL_COMPS = """
SELECT DISTINCT reference_year, reference_month FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus')
 ORDER BY 1 DESC, 2 DESC LIMIT 12
"""


def _br(comp: str) -> str:
    a, m = comp.split("-")
    return f"{m}/{a}"


def _hm(minutos) -> str:
    m = int(float(minutos or 0))
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, _safe, _tbl = _helpers(db)

    linhas = [dict(r) for r in (await db.execute(text(_SQL_LINHAS))).mappings().all()]
    comps = [f"{int(a):04d}-{int(m):02d}" for a, m in (await db.execute(text(_SQL_COMPS))).all()]
    apuradas = sorted({ln["competencia"] for ln in linhas}, reverse=True)
    faltam = [c for c in comps if c not in apuradas]

    # ── atraso ────────────────────────────────────────────────────────────────────────────
    atr = [ln for ln in linhas if ln["tipo"] == "atraso"]
    tot_min = sum(float(x["ponto_qtd"]) for x in atr)
    tot_rs = sum(float(x["valor_estimado"]) for x in atr)
    tot_desc = sum(float(x["ponto_qtd_descartada"]) for x in atr)

    def _linha_atraso(r: dict) -> dict:
        n_turnos = len(r["detalhe"] or [])
        susp = int(float(r["ponto_qtd_descartada"] or 0))
        return {
            "cells": [
                t(r["employee_nome"], 700, _ND),
                t(_br(r["competencia"])),
                t(f"{n_turnos} turno(s)"),
                t(_hm(r["ponto_qtd"])),
                t(_hm(r["ponto_qtd_util"]), 700, _ND),
                t(brl(r["valor_hora"]) + "/h" if r["valor_hora"] else "sem holerite"),
                t(brl(r["valor_estimado"]), 700, _ND),
                b("NÃO — sem rubrica", "bad"),
                t(_hm(susp), 500, "#B45309") if susp else t("—"),
            ],
            "docs": [{"label": "Como foi medido", "value": r["observacao"] or "—"}]
            + [
                {
                    "label": f"{d['dia'][8:10]}/{d['dia'][5:7]} · {d['turno']} · {d['posto'][:28]}",
                    "value": (
                        f"bateu {d['batida'][11:16]} ({d['fonte']}) — {d['minutos']} min depois do início, "
                        f"{d['alem_tolerancia']} além da tolerância de {d['tolerancia_min']} min"
                        + (" · ENTRADA AUSENTE: fora da conta de dinheiro" if d["entrada_ausente"] else "")
                    ),
                }
                for d in sorted(r["detalhe"] or [], key=lambda x: x["dia"])
            ],
            "filtro": {"Competência": _br(r["competencia"]), "Estado": "com atraso" if r["divergente"] else "sem"},
        }

    mine["atraso-conferencia"] = {
        "title": "Atraso: o que o ponto mediu × o que a folha descontou",
        "sub": (
            f"{len(atr)} pessoa(s) · {_hm(tot_min)} de atraso medidos pela régua do mapa de ponto (frente 04) · "
            f"estimativa **{brl(tot_rs)}**. A folha descontou **R$ 0,00**: o motor não produz o evento «atraso» "
            f"e não existe rubrica de atraso em `rubricas_folha` (medido em 24/09/2026). O valor é ESTIMATIVA — "
            f"minutos ALÉM da tolerância × valor-hora do holerite da própria pessoa (base ÷ divisor da escala) — "
            f"e esta tela não muda um centavo de nada. {_hm(tot_desc)} ficaram FORA da conta: turno cujo «atraso» "
            f"alcança {FRACAO_ENTRADA_AUSENTE:.0%} da jornada é batida de ENTRADA faltando, não atraso. "
            + ("Competências sem apuração: " + ", ".join(_br(c) for c in faltam) + "." if faltam else "")
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa…",
        "grid": "1.8fr 0.8fr 0.8fr 0.8fr 0.9fr 1fr 1fr 1.2fr 0.9fr",
        "cols": [
            "Pessoa",
            "Competência",
            "Turnos",
            "Atraso total",
            "Além da tolerância",
            "Valor-hora",
            "R$ estimado",
            "Descontado?",
            "Entrada ausente",
        ],
        "rows": [_linha_atraso(r) for r in atr],
    }

    # ── falta justificada ─────────────────────────────────────────────────────────────────
    fj = [ln for ln in linhas if ln["tipo"] == "falta_justificada"]
    n_div = sum(1 for x in fj if x["divergente"])
    passivo = sum(float(x["valor_estimado"]) for x in fj if x["divergente"])
    descontado = sum(float(x["folha_valor"]) for x in fj)

    def _linhas_falta(r: dict) -> list[dict]:
        base_filtro = {"Competência": _br(r["competencia"]), "Estado": "divergente" if r["divergente"] else "ok"}
        desconto = f"{int(float(r['folha_qtd']))} dia(s) · {brl(r['folha_valor'])}" if float(r["folha_qtd"]) else "não"
        docs = [{"label": "O que a apuração concluiu", "value": r["observacao"] or "—"}]
        if not (r["detalhe"] or []):
            return [
                {
                    "cells": [
                        t(r["employee_nome"], 700, _ND),
                        t(_br(r["competencia"])),
                        t("—"),
                        t("(sem justificativa nem atestado)"),
                        t("—"),
                        t(desconto, 700, _ND),
                        b("sem abono", "mut"),
                    ],
                    "docs": docs,
                    "filtro": base_filtro,
                }
            ]
        return [
            {
                "cells": [
                    t(r["employee_nome"], 700, _ND),
                    t(_br(r["competencia"])),
                    t(
                        f"{d['dia'][8:10]}/{d['dia'][5:7]}"
                        + (f" +{int(d['dias']) - 1}d" if int(d["dias"]) > 1 else "")
                        + (" (data da criação)" if d.get("dia_por_criacao") else "")
                    ),
                    t((d["motivo"] or d["categoria"] or "—")[:90]),
                    t(f"{d['aprovada_por']}" + (f" · {d['aprovada_em'][:10]}" if d.get("aprovada_em") else "")),
                    t(desconto, 700, "#B91C1C" if r["divergente"] else _ND),
                    b("DESCONTOU MESMO ASSIM", "bad") if r["divergente"] else b("não descontou", "ok"),
                ],
                "docs": docs,
                "filtro": base_filtro,
            }
            for d in sorted(r["detalhe"], key=lambda x: x["dia"])
        ]

    mine["falta-justificada-conferencia"] = {
        "title": "Falta justificada × falta descontada",
        "sub": (
            f"{len(fj)} pessoa(s) com falta descontada ou abono no período · **{n_div} divergência(s)**, "
            f"estimativa de passivo {brl(passivo)}. A folha descontou {brl(descontado)} em 1051/1053, lendo "
            f"`time_sheets.unjustified_absent_days` — e **nunca** consulta `gp_justifications` nem "
            f"`sst_afastamentos`. Linha vermelha = a pessoa tinha justificativa aprovada ou atestado no dia e "
            f"mesmo assim levou desconto: passivo. Linha verde = abonado e não descontado, o caminho certo. "
            f"Esta tela não muda um centavo de holerite nenhum."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa, motivo…",
        "grid": "1.6fr 0.8fr 0.9fr 2fr 1.2fr 1.1fr 1.3fr",
        "cols": [
            "Pessoa",
            "Competência",
            "Dia",
            "Motivo da justificativa",
            "Aprovada por",
            "Descontou na folha?",
            "Situação",
        ],
        "rows": [row for r in fj for row in _linhas_falta(r)],
    }

    # ── form de apuração ──────────────────────────────────────────────────────────────────
    mine["ponto-folha-apurar"] = {
        "title": "Apurar conferência ponto × folha",
        "sub": "Recalcula a conferência de uma competência: minutos de atraso pela régua do mapa de ponto, faltas "
        "descontadas com justificativa aprovada e abonos que não foram descontados. Escreve só na tabela de "
        "conferência (`ponto_folha_conferencia`) — **nenhum holerite é tocado**. Rodar duas vezes dá o mesmo "
        "resultado.",
        "cta": "Apurar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "ponto-folha-apurar",
            "okMsg": "Apurado — veja as abas «Atraso: conferência» e «Falta justificada: conferência».",
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
    # a frente roda DEPOIS de `montar_grupos`: anexa as abas ao fim do g-folha, como a W3 faz
    grupo = (out or {}).get("g-folha")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-folha", tid)
    if out is not None:
        out.update(mine)
    return mine


@router.post("/action/ponto-folha-apurar")
async def rd_ponto_folha_apurar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Reapura a competência. Escreve SÓ em `ponto_folha_conferencia` — paralelo cego."""
    try:
        comp = competencia_iso(payload.get("competencia") or "")
    except (ValueError, IndexError, AttributeError):
        raise HTTPException(status_code=400, detail="Competência: use MM/AAAA (ex.: 09/2026).") from None
    if comp > f"{date.today():%Y-%m}":
        raise HTTPException(status_code=400, detail=f"{_br(comp)} ainda não aconteceu.")
    r = await apurar(db, comp)
    return {
        "ok": True,
        "message": (
            f"{_br(comp)}: {r['linhas']} linha(s). Atraso — {r['atraso']['pessoas']} pessoa(s), "
            f"{r['atraso']['minutos']} min ({r['atraso']['minutos_alem']} além da tolerância), estimativa "
            f"{brl(r['atraso']['valor'])}, descontado na folha R$ 0,00. "
            f"Falta justificada — {r['passivo']['pessoas']} pessoa(s) descontadas COM abono "
            f"({brl(r['passivo']['valor'])} de passivo estimado); {r['ok']['pessoas']} abonada(s) sem desconto. "
            f"Nenhum holerite foi tocado."
        ),
        "result": r,
    }
