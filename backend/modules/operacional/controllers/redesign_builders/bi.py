"""
redesign_builders/bi.py — T4 (Fase 2, fidelidade).
O BI clássico mostra Receita×Despesa (6m) + DRE do mês + margem; o redesign só
tinha 4 KPIs. Traz o dado REAL (bank_transactions / billing_rules), mesma fonte
do clássico `/financial/bi/overview`. Só leitura, SQL agregada (sem I/O lento no
render — regra A5).
"""

from sqlalchemy import text  # noqa: F401

from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    S,
    _helpers,
    _scalar,
    b,
    brl,
    t,
)
from modules.operacional.controllers.redesign_data_controller import (
    _build_bi as _base,
)

SLUG = "bi"

_ICO_X5 = "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"

EXTRA_MENU: list[dict] = [
    {"id": "receita-despesa", "label": "Receita × Despesa", "icon": "M3 3v18h18M7 14l3-3 3 3 5-6"},
    {
        "id": "dre",
        "label": "DRE do mês",
        "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5",
    },
    # dgx x5 — itens escritos aqui, e não importados do `_dgx_x5_decisoes`, porque aquele
    # módulo importa o `redesign_data_controller` de volta: um import no TOPO fecha o ciclo e
    # o discovery engole o `bi` inteiro com um log de «partially initialized module».
    {"id": "decisoes-do-dono", "label": "Decisões do dono", "icon": _ICO_X5},
    {"id": "decisao-registrar", "label": "Registrar decisão", "icon": _ICO_X5},
]


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Receita × Despesa (últimos 6 meses) — bank_transactions ----
    await safe(
        "receita-despesa",
        tbl(
            "Receita × Despesa (6 meses)",
            "Fluxo realizado por mês — dados reais do extrato",
            "—",
            ["Mês", "Receita", "Despesa", "Resultado", "Transações"],
            "1fr 1.2fr 1.2fr 1.2fr 1fr",
            "SELECT to_char(date_trunc('month', transaction_date), 'MM/YYYY'), "
            "ROUND(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END)::numeric,2), "
            "ROUND(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2), "
            "ROUND(SUM(amount)::numeric,2), COUNT(*) "
            "FROM bank_transactions WHERE transaction_date >= date_trunc('month', CURRENT_DATE - interval '5 months') "
            "GROUP BY 1, date_trunc('month', transaction_date) ORDER BY date_trunc('month', transaction_date) DESC",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(brl(r[1]), 600, "#16A34A"),
                t(brl(r[2]), 600, "#C2410C"),
                b(brl(r[3]), "ok" if (r[3] or 0) >= 0 else "bad"),
                t(str(r[4])),
            ],
        ),
    )

    # ---- DRE do mês (categorias de bank_transactions) — pivot manual ----
    async def _dre():
        row = (
            await db.execute(
                text(
                    "SELECT "
                    "ROUND(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END)::numeric,2) receita, "
                    "ROUND(SUM(CASE WHEN category='folha_pagamento' AND amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) folha, "
                    "ROUND(SUM(CASE WHEN category='fornecedores' AND amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) fornec, "
                    "ROUND(SUM(CASE WHEN category='impostos' AND amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) impostos, "
                    "ROUND(SUM(CASE WHEN category='operacional' AND amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) oper, "
                    "ROUND(SUM(CASE WHEN category='beneficios' AND amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) benef, "
                    "ROUND(SUM(amount)::numeric,2) resultado, "
                    "ROUND(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END)::numeric,2) despesa_total "
                    "FROM bank_transactions WHERE date_trunc('month', transaction_date)=date_trunc('month', CURRENT_DATE)"
                )
            )
        ).fetchone()
        rec = float(row[0] or 0)
        _cat = sum(float(row[i] or 0) for i in (1, 2, 3, 4, 5))  # despesa já categorizada
        _outros = float(row[7] or 0) - _cat  # resíduo não categorizado (fecha com o resultado)
        linhas = [
            ("Receita bruta", float(row[0] or 0), "ok"),
            ("(−) Folha de pagamento", -float(row[1] or 0), "bad"),
            ("(−) Fornecedores", -float(row[2] or 0), "bad"),
            ("(−) Impostos", -float(row[3] or 0), "bad"),
            ("(−) Operacional", -float(row[4] or 0), "bad"),
            ("(−) Benefícios", -float(row[5] or 0), "bad"),
            ("(−) Outros custos", -_outros, "bad"),
            ("(=) Resultado do mês", float(row[6] or 0), "ok" if (row[6] or 0) >= 0 else "bad"),
        ]
        rows = []
        for nome, val, tone in linhas:
            pct = (val / rec * 100) if rec else 0
            rows.append(
                {
                    "cells": [
                        t(nome, 600, "#0F1B3A"),
                        b(brl(val), tone),
                        t(f"{pct:+.1f}%" if nome != "Receita bruta" else "100%"),
                    ]
                }
            )
        return {
            "title": "DRE do mês",
            "sub": "Demonstrativo do mês corrente por categoria — extrato real",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar…",
            "grid": "2fr 1.2fr 1fr",
            "cols": ["Linha", "Valor", "% s/ receita"],
            "rows": rows,
        }

    await safe("dre", _dre())

    from ._dgx_x5_decisoes import telas as _x5_telas  # dgx x5

    out.update(await _x5_telas(db, out))  # dgx x5 — decisões do dono com número ao vivo
    return out


# As ações (`POST /api/v1/redesign/action/decisao-*`) entram pelo `router` que o discovery
# procura NESTE módulo. Importado no FIM de propósito: se o ciclo acontecer, `EXTRA_MENU` e
# `build` já existem e o `bi` não some do menu por causa do plug.
from ._dgx_x5_decisoes import router  # noqa: E402, F401 — dgx x5
