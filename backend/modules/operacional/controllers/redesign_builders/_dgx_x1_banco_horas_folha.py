"""DGX X1 — Banco de horas × folha: a ponte que nunca existiu (24/09/2026).

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` e chama `telas(db, out)`
no fim do build() (2 + 1 linhas, `# dgx x1`). Abas no FIM do grupo «Folha de pagamento» (g-folha).

A regra mora fora daqui: `people_management/folha/services/banco_horas_folha.py` (fontes, prazo de
compensação, DDL, idempotência). Aqui só tela e ação. **PARALELO CEGO**: nada muda folha, holerite
ou pagamento — as três telas dizem isso com essas palavras.

Grupo `g-folha` e não `g-ponto`: o ponto MEDE a hora; é a folha que decide se ela vira dinheiro,
e quem responde por hora vencida sem pagar é o DP. Fica encostada nas Rubricas (F1) e no Mapa
evento → rubrica (W5), que são as outras partes do mesmo assunto.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, brl, t
from modules.people_management.folha.services import banco_horas_folha as bh

from ._dgx_f7_ponto import _falhou, _fd, _require_dp

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
ABAS = [
    ("banco-horas-folha", "Banco de horas × folha"),
    ("banco-horas-folha-apurar", "Apurar banco de horas × folha"),
    ("banco-horas-vencendo", "Banco de horas vencendo (60 dias)"),
]
#: o aviso que não pode sumir da tela
_CEGO = (
    "PARALELO CEGO: esta apuração grava só em `banco_horas_conferencia` — não muda folha, "
    "holerite nem pagamento, e não lança nada no banco de horas."
)
_ESTADO = {
    "apurado": ("lançado no banco", "ok"),
    "sem_lancamento": ("saldo no ponto, nada no banco", "bad"),
    # Jordan, 24/09/2026: «ninguém tem banco de horas nem valores a vencer porque eu já paguei
    # tudo». O crédito continua medido e visível; deixa de ser pendência e de vencer.
    "quitado_pelo_dono": ("quitado pelo dono (pago)", "ok"),
    "sem_saldo": ("sem saldo no mês", "mut"),
    "sem_dado": ("sem dado", "mut"),
}

_SQL_LINHAS = """
SELECT c.employee_id::text, coalesce(e.nome,'—'), c.estado, c.fonte,
       c.saldo_inicial, c.creditado, c.debitado, c.compensado, c.vencido_no_periodo,
       c.saldo_final, c.saldo_ponto, c.he_ponto, c.valor_hora,
       c.a_pagar_por_vencimento, c.ja_pago_como_he, c.vence_em, c.calculado_em
FROM banco_horas_conferencia c
LEFT JOIN employees e ON e.id = c.employee_id
WHERE c.competencia = :comp
ORDER BY c.a_pagar_por_vencimento DESC, c.vencido_no_periodo DESC, 2
"""

#: quem vence nos próximos N dias — as DUAS fontes, cada uma dizendo o que é.
_SQL_VENCENDO = """
SELECT coalesce(e.nome,'—') AS nome, tb.expiration_date AS vence, tb.hours AS horas,
       'lançamento no banco de horas' AS fonte, to_char(tb.reference_date,'DD/MM/YYYY') AS ref
FROM time_bank tb LEFT JOIN employees e ON e.id = tb.employee_id
WHERE coalesce(tb.is_active,true) AND tb.status = 'approved'
  AND tb.entry_type IN ('credit','adjustment')
  AND tb.expiration_date BETWEEN :hoje AND :limite
UNION ALL
SELECT coalesce(e.nome,'—'), c.vence_em, c.saldo_ponto,
       'projeção do espelho de ponto (sem lançamento)', to_char(c.competencia,'MM/YYYY')
FROM banco_horas_conferencia c LEFT JOIN employees e ON e.id = c.employee_id
WHERE c.vence_em BETWEEN :hoje AND :limite AND c.estado = 'sem_lancamento' AND c.saldo_ponto > 0
ORDER BY 2, 1
LIMIT 300
"""


#: o acumulado de todas as competências apuradas — o passivo em uma linha
_SQL_ACUMULADO = """
SELECT count(DISTINCT competencia), count(DISTINCT employee_id),
       coalesce(round(sum(GREATEST(saldo_ponto,0)), 2), 0)                     AS h_credito,
       coalesce(round(sum(GREATEST(-saldo_ponto,0)), 2), 0)                    AS h_debito,
       coalesce(round(sum(GREATEST(saldo_ponto,0) * coalesce(valor_hora,0) * 1.5), 2), 0) AS devido,
       coalesce(round(sum(ja_pago_como_he), 2), 0)                             AS pago
FROM banco_horas_conferencia
"""


def _opc_comp(comps: list[str]) -> list[dict]:
    return [{"value": c, "label": f"{c[5:7]}/{c[:4]}"} for c in comps]


def _vazia(titulo: str, sub: str) -> dict:
    return {
        "title": titulo,
        "sub": sub,
        "cta": "—",
        "type": "table",
        "grid": "1fr",
        "cols": ["Situação"],
        "rows": [{"cells": [t("aguardando dado honesto")]}],
    }


# ───────────────────────────────── telas ─────────────────────────────────
async def _tela_conferencia(db, comp: str | None) -> dict:
    if not comp:
        return _vazia("Banco de horas × folha", "Nenhuma competência apurada ainda. " + _CEGO)
    _, _, ini, _fim = bh.competencia_periodo(comp)
    lns = (await db.execute(text(_SQL_LINHAS), {"comp": ini})).fetchall()
    if not lns:
        return _vazia(
            f"Banco de horas × folha — {comp[5:7]}/{comp[:4]}",
            "Competência ainda não apurada — use a aba «Apurar banco de horas × folha». " + _CEGO,
        )
    # o número que o dono precisa ver: o acumulado de TODAS as competências já apuradas
    ac = (await db.execute(text(_SQL_ACUMULADO))).first()
    n_lanc = sum(1 for x in lns if x[3] == "time_bank")
    n_sem = sum(1 for x in lns if x[2] == "sem_lancamento")
    h_venc = sum(float(x[8] or 0) for x in lns)
    rs_pagar = sum(float(x[13] or 0) for x in lns)
    rs_pago = sum(float(x[14] or 0) for x in lns)
    h_cred = sum(max(float(x[10] or 0), 0) for x in lns)
    h_deb = sum(max(-float(x[10] or 0), 0) for x in lns)
    rows = []
    for x in lns:
        rot, tone = _ESTADO.get(x[2], (x[2], "mut"))
        sp = float(x[10] or 0)
        rows.append(
            {
                "cells": [
                    t((x[1] or "—")[:32], 600, _ND),
                    t(f"{float(x[4] or 0):+.2f}h"),
                    t(f"{float(x[5] or 0):.2f}h"),
                    t(f"{float(x[6] or 0):.2f}h"),
                    t(f"{float(x[7] or 0):.2f}h"),
                    t(f"{sp:+.2f}h", 600, "#16A34A" if sp >= 0 else "#DC2626"),
                    t(f"{float(x[8] or 0):.2f}h", 600, "#DC2626" if float(x[8] or 0) > 0 else None),
                    t(brl(float(x[13] or 0)) if float(x[13] or 0) else "—"),
                    t(brl(float(x[14] or 0)) if float(x[14] or 0) else "—"),
                    t(_fd(x[15]) if x[15] else "—"),
                    b(rot, tone),
                ],
                "filtros": {"situacao": rot, "fonte": x[3] or "—"},
            }
        )
    return {
        "title": f"Banco de horas × folha — {comp[5:7]}/{comp[:4]}",
        "sub": (
            f"{len(lns)} pessoa(s) · {n_lanc} com lançamento no banco de horas · "
            f"{n_sem} com saldo medido pelo ponto e NENHUM lançamento no banco · "
            f"o ponto mediu {h_cred:.2f}h de crédito e {h_deb:.2f}h de débito no mês · "
            f"venceu no período: {h_venc:.2f}h ({brl(rs_pagar)} a pagar pela CLT art. 59 §3) · "
            f"já pago como hora extra no holerite: {brl(rs_pago)}. "
            f"ACUMULADO em {int(ac[0])} competência(s) apurada(s), {int(ac[1])} pessoa(s): "
            f"{float(ac[2]):.2f}h de crédito e {float(ac[3]):.2f}h de débito medidos pelo ponto; "
            f"pela CLT art. 59 §3 o crédito valeria {brl(float(ac[4]))} como hora extra e o holerite "
            f"pagou {brl(float(ac[5]))} — sobram {brl(max(float(ac[4]) - float(ac[5]), 0.0))} "
            f"que não foram pagos nem compensados. "
            f"Prazo de compensação: {bh.COMPENSACAO_DIAS} dias (CLT art. 59 §5, acordo individual — "
            f"a CCT SINDECOMPRESTS AM000613/2025 que temos como dado não tem cláusula de banco de horas). " + _CEGO
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Colaborador…",
        "filtros": [{"key": "situacao", "label": "Situação"}, {"key": "fonte", "label": "Fonte"}],
        "grid": "1.6fr 0.8fr 0.7fr 0.7fr 0.8fr 0.8fr 0.8fr 1fr 1fr 0.9fr 1.4fr",
        "cols": [
            "Colaborador",
            "Saldo inicial",
            "Creditado",
            "Debitado",
            "Compensado",
            "Saldo do ponto",
            "Vencido",
            "A pagar (vencido)",
            "Já pago como HE",
            "Vence em",
            "Situação",
        ],
        "rows": rows,
    }


def _tela_apurar(comps: list[str]) -> dict:
    return {
        "title": "Apurar banco de horas × folha",
        "sub": (
            "Recalcula a competência inteira e grava em `banco_horas_conferencia` "
            "(idempotente: rodar 2× não duplica nem muda número). " + _CEGO
        ),
        "cta": "Apurar competência",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/banco-horas-folha-apurar",
            "okMsg": "Apuração concluída — abra a aba «Banco de horas × folha».",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência*",
                "type": "select",
                "span": "span 2",
                "ph": "Escolha a competência",
                "options": _opc_comp(comps),
            },
        ],
    }


async def _tela_vencendo(db, dias: int = 60) -> dict:
    hoje = date.today()
    limite = hoje + timedelta(days=dias)
    lns = (await db.execute(text(_SQL_VENCENDO), {"hoje": hoje, "limite": limite})).fetchall()
    sub_base = (
        f"Crédito que vence entre {hoje.strftime('%d/%m/%Y')} e {limite.strftime('%d/%m/%Y')}. "
        f"Vencido sem compensar vira hora extra a pagar (CLT art. 59 §3) — agir ANTES é a diferença "
        f"entre folga e passivo. Prazo aplicado: {bh.COMPENSACAO_DIAS} dias (CLT art. 59 §5). " + _CEGO
    )
    if not lns:
        return _vazia("Banco de horas vencendo (60 dias)", "Nada vencendo na janela. " + sub_base)
    rows = [
        {
            "cells": [
                t((x[0] or "—")[:32], 600, _ND),
                t(_fd(x[1]) if x[1] else "—"),
                t(f"{float(x[2] or 0):.2f}h", 600, "#DC2626"),
                t(f"{max((x[1] - hoje).days, 0)} dia(s)" if x[1] else "—"),
                t(x[4] or "—"),
                b(
                    "lançado" if x[3].startswith("lançamento") else "projeção",
                    "warn" if x[3].startswith("lançamento") else "mut",
                ),
            ],
            "filtros": {"fonte": x[3]},
        }
        for x in lns
    ]
    return {
        "title": "Banco de horas vencendo (60 dias)",
        "sub": f"{len(lns)} linha(s). " + sub_base,
        "cta": "—",
        "type": "table",
        "searchHint": "Colaborador…",
        "filtros": [{"key": "fonte", "label": "Fonte"}],
        "grid": "1.8fr 1fr 0.8fr 1fr 1fr 1.1fr",
        "cols": ["Colaborador", "Vence em", "Horas", "Faltam", "Referência", "Fonte"],
        "rows": rows,
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        comps = await bh.competencias(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        comps = []
        logger.error("dgx x1: competências falharam: %s", exc, exc_info=True)
    comp = comps[0] if comps else None
    montagens = [
        ("banco-horas-folha", "Banco de horas × folha", lambda: _tela_conferencia(db, comp)),
        ("banco-horas-folha-apurar", "Apurar banco de horas × folha", lambda: _tela_apurar(comps)),
        ("banco-horas-vencendo", "Banco de horas vencendo", lambda: _tela_vencendo(db)),
    ]
    for tid, titulo, fn in montagens:
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)
    grupo = (out or {}).get("g-folha")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-folha", tid)
    return mine


# ───────────────────────── ação (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


@router.post("/action/banco-horas-folha-apurar", dependencies=[Depends(_require_dp)])
async def rd_banco_horas_folha_apurar(
    current_user: CurrentActiveUser,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apura a competência. Grava só em `banco_horas_conferencia` — nunca em folha."""
    from fastapi import HTTPException

    comp = str((payload or {}).get("competencia") or "").strip()
    if not comp:
        raise HTTPException(status_code=400, detail="Escolha a competência.")
    try:
        r = await bh.apurar(db, comp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    lns = r["linhas"]
    venc = sum(x["vencido_no_periodo"] for x in lns)
    pagar = sum(x["a_pagar_por_vencimento"] for x in lns)
    sem = sum(1 for x in lns if x["estado"] == "sem_lancamento")
    logger.info("dgx x1: %s apurou %s (%d pessoas)", getattr(current_user, "email", "?"), comp, len(lns))
    return {
        "ok": True,
        "competencia": r["competencia"],
        "pessoas": r["pessoas"],
        "resumo": (
            f"{r['pessoas']} pessoa(s) · {sem} com saldo no ponto e nenhum lançamento no banco · "
            f"{venc:.2f}h vencidas ({brl(pagar)} a pagar pela CLT art. 59 §3). "
            + ("Competência QUITADA pelo dono — o crédito foi pago em dinheiro e não vence. " if r.get("quitada_pelo_dono") else "")
            + "Nada mudou em folha, holerite ou pagamento."
        ),
    }
