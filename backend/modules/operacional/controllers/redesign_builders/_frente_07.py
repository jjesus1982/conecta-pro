"""Frente 07 — telas do CRM: "Calculado × Faturado" por contrato e simulação de precificação.

Anexado ao builder `crm.py` (duas linhas no fim do build() + router/menu no nível do módulo).
Tudo aqui SÓ LÊ: a simulação devolve resultado e não grava; a divergência é relatório.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.crm.services import precificacao_contrato as prec
from modules.crm.services.precificacao_modos import MODOS, ROTULO, ParametroAusente

# `b/brl/t` do redesign_data_controller entram tarde (dentro de telas): importar no topo fecha
# um ciclo — redesign_data_controller → descoberta → crm.py → _frente_07 (meio inicializado) →
# "cannot import name router" e o builder do crm INTEIRO cai. Medido no oráculo em 12/09.

_ICO = "M3 3v18h18M7 14l3-3 3 3 5-6"

MENU: list[dict] = [
    {"id": "calculado-vs-faturado", "label": "Calculado × Faturado", "icon": _ICO, "grupo": "Propostas & orçamento"},
    {"id": "simular-precificacao", "label": "Simular precificação", "icon": _ICO, "grupo": "Propostas & orçamento"},
]

_ENTRADAS = (
    ("postos", "Postos", "1"),
    ("montante", "Montante R$/mês", ""),
    ("horas", "Horas (diurnas)", ""),
    ("valor_hora", "Valor-hora R$", ""),
    ("valor_total", "Valor total fechado R$", ""),
    ("horas_mes", "Horas/mês", ""),
    ("horas_dia", "Horas/dia", ""),
    ("horas_noturnas", "Horas noturnas", ""),
    ("valor_hora_noturna", "Valor-hora noturna R$", ""),
    ("dias", "Dias (dias fixos)", ""),
    ("valor_dia", "Valor/dia R$", ""),
)


def _tom(pct) -> str:
    if pct is None:
        return "info"
    return "ok" if pct >= 0 else ("warn" if pct > -10 else "bad")


async def telas(db) -> dict:
    from modules.operacional.controllers.redesign_data_controller import b, brl, t

    out: dict = {}
    comp = date.today().strftime("%Y-%m")
    try:
        linhas = await prec.relatorio_calculado_vs_faturado(db, comp)
        com = [r for r in linhas if isinstance(r["divergencia_reais"], (int, float))]
        abaixo = [r for r in com if r["divergencia_reais"] < 0]
        rows = []
        for r in linhas:
            calc, fat = r["preco_calculado"], r["faturado"]
            aus = ", ".join(r["parametros_ausentes"]) or "—"
            motivo = r["motivo_sem_calculo"] or r["motivo_sem_faturado"] or ""
            rows.append(
                {
                    "cells": [
                        t(r["contract_number"], 600, "#0F1B3A"),
                        t((r["cliente"] or "—")[:34]),
                        t(str(r["efetivo"])),
                        t(brl(r["custo_calculado"]) if isinstance(r["custo_calculado"], (int, float)) else "sem dado"),
                        t(brl(calc) if isinstance(calc, (int, float)) else "sem dado", 600),
                        t(
                            (brl(fat) if isinstance(fat, (int, float)) else "sem dado")
                            + (f" · {r['fonte_faturado']}" if r["fonte_faturado"] else "")
                        ),
                        b(
                            f"{brl(r['divergencia_reais'])} ({r['divergencia_pct']:+.1f}%)"
                            if r["divergencia_reais"] is not None
                            else (motivo[:40] or "—"),
                            _tom(r["divergencia_pct"]),
                        ),
                        t(
                            aus[:48] + ("" if not r["hipoteses"] else " · " + "; ".join(r["hipoteses"])[:80]),
                            400,
                            "#64748B",
                        ),
                    ]
                }
            )
        out["calculado-vs-faturado"] = {
            "title": "Calculado × Faturado",
            "sub": (
                f"Competência {comp} · {len(linhas)} contrato(s) ativo(s) · {len(com)} com os dois números · "
                f"{len(abaixo)} faturado(s) ABAIXO do calculado. Custo = motor CCT × efetivo dos postos (+ reserva "
                f"técnica, PLR sindicato e taxa admin quando confirmados). Faturado = NFS-e da competência ou valor "
                f"do contrato. Relatório para o dono: NADA aqui muda preço."
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Contrato ou cliente…",
            "grid": "1fr 1.6fr 0.5fr 1fr 1fr 1.3fr 1.4fr 1.8fr",
            "cols": [
                "Contrato",
                "Cliente",
                "Efetivo",
                "Custo calculado",
                "Preço calculado",
                "Faturado · fonte",
                "Divergência (fat − calc)",
                "Parâmetros ausentes · hipóteses",
            ],
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001 — tela nunca derruba o módulo, mas diz por quê
        await db.rollback()
        out["calculado-vs-faturado"] = {
            "title": "Calculado × Faturado",
            "sub": f"Sem dado: {str(e)[:160]}",
            "cta": "—",
            "type": "table",
            "grid": "1fr",
            "cols": ["Situação"],
            "rows": [{"cells": [t("aguardando dado honesto")]}],
        }

    ctrs = (
        await db.execute(
            text(
                "SELECT c.contract_number, cl.name FROM contracts c JOIN clients cl ON cl.id=c.client_id "
                " WHERE c.status='active' ORDER BY c.monthly_value DESC"
            )
        )
    ).all()
    out["simular-precificacao"] = {
        "title": "Simular precificação de contrato",
        "sub": (
            "Devolve o custo calculado (efetivo × custo CCT + reserva técnica + PLR sindicato + taxa admin) e, "
            "se você escolher um modo de cálculo, o total pelo modo (montante, hora, valor fechado, horas, "
            "dias fixos 5x2/6x1/SDF com feriados da CCT). SÓ SIMULA — não grava preço em contrato nenhum. "
            "Parâmetro sem confirmação do dono aparece como ausente, não como 0."
        ),
        "cta": "Simular",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/simular-precificacao",
            "showResult": True,
            "okMsg": "Simulação concluída (nada foi gravado).",
        },
        "fields": [
            {
                "key": "contrato",
                "label": "Contrato*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": n, "label": f"{n} · {nome}"} for n, nome in ctrs],
            },
            {"key": "competencia", "label": "Competência (AAAA-MM)", "type": "text", "span": "span 1", "value": comp},
            {
                "key": "modo",
                "label": "Modo de cálculo",
                "type": "select",
                "span": "span 1",
                "value": "",
                "options": [{"value": "", "label": "— preço do motor CCT (sem modo)"}]
                + [{"value": m, "label": ROTULO[m]} for m in MODOS],
            },
        ]
        + [{"key": k, "label": lab, "type": "text", "span": "span 1", "value": v} for k, lab, v in _ENTRADAS],
    }
    return out


router = APIRouter()


@router.post("/action/simular-precificacao")
async def _simular(_=Depends(get_current_active_user), payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """FORM da tela: devolve o resultado, não grava nada."""
    entradas = {k: payload.get(k) for k, _l, _v in _ENTRADAS if payload.get(k) not in (None, "")}
    try:
        s = await prec.simular_contrato(
            db,
            (payload.get("contrato") or "").strip(),
            payload.get("competencia") or None,
            payload.get("modo") or None,
            entradas,
        )
    except (ParametroAusente, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # o painel de resultado mostra escalares e 1 nível de dict — listas viram texto
    res = {
        "ok": True,
        "message": f"Simulação de {s['contrato']} em {s['competencia']} — nada gravado.",
        "contrato": s["contrato"],
        "cliente": s["cliente"],
        "competencia": s["competencia"],
        "efetivo": s["efetivo"],
        "valor_contrato": s["valor_contrato"],
        "custo_mao_de_obra": s["custo_mao_de_obra"],
        "custo_calculado": s["custo_calculado"],
        "preco_calculado": s["preco_calculado"],
        "componentes": {k: (v if v is not None else "ausente") for k, v in s["componentes"].items()},
        "parametros": {
            c: (
                f"{p['valor']} · {'APLICADO' if p['aplicavel'] else p['motivo']}"
                if p["valor"] is not None
                else p["motivo"]
            )
            for c, p in s["parametros"].items()
        },
        "motivo_sem_calculo": s["motivo_sem_calculo"] or "—",
        "hipoteses": "; ".join(s["hipoteses"]) or "—",
        "avisos": "; ".join(s["avisos"]) or "—",
    }
    if s.get("modo"):
        res["modo"] = {k: v for k, v in s["modo"].items() if not isinstance(v, (list, dict))}
    return res
