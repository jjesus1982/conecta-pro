"""DGX W3 — Hora extra classificada: faturada ao cliente × custo nosso × cobertura (24/09/2026).

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` e chama `telas(db, out)`
no fim do build() (2 + 1 linhas, `# dgx w3`). Abas no FIM do grupo "Ponto & Jornada" (g-ponto).

A regra mora fora daqui: `people_management/ponto/he_classificacao.py` (fonte da HE, sugestão,
idempotência, DDL). Aqui só tela e ação. NADA muda folha nem preço de contrato: o R$ é
ESTIMATIVA e as três telas dizem isso com essa palavra.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, brl, t
from modules.people_management.ponto import he_classificacao as hc

from ._dgx_f7_ponto import _falhou, _fd, _require_dp

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"
ABAS = [
    ("he-classificar", "HE: classificar"),
    ("he-classificar-lote", "HE: confirmar/reclassificar em lote"),
    ("he-por-contrato", "HE por contrato"),
]
_OPC_MOTIVO = [
    {"value": k, "label": f"{rot} ({'repassável' if rep else 'custo nosso'})"} for k, (rot, rep) in hc.MOTIVOS.items()
]


def _rotulo(motivo: str) -> str:
    return hc.MOTIVOS.get(motivo, (motivo, False))[0]


async def _comps(db) -> list[str]:
    return await hc.competencias(db) or []


def _opc_comp(comps: list[str]) -> list[dict]:
    return [{"value": c, "label": f"{c[5:7]}/{c[:4]}"} for c in comps]


# ───────────────────────────────── telas ─────────────────────────────────
async def _tela_classificar(db, comp: str | None) -> dict:
    if not comp:
        return {
            "title": "HE: classificar",
            "sub": "Nenhuma competência com hora extra no espelho de ponto ainda.",
            "cta": "—",
            "type": "table",
            "grid": "1fr",
            "cols": ["Situação"],
            "rows": [{"cells": [t("aguardando dado honesto")]}],
        }
    lev = await hc.levantar(db, comp)
    lns = await hc.linhas(db, comp)
    pend = [x for x in lns if not x["classificado_em"]]
    rep = [x for x in lns if x["repassavel"]]
    horas_rep = round(sum(x["horas"] for x in rep), 2)
    horas_tot = round(sum(x["horas"] for x in lns), 2)
    reais_rep = round(sum(x["reais"] for x in rep), 2)
    sem_expl = [x for x in lns if x["motivo"] == "falta_de_efetivo"]
    rows = []
    for x in lns:
        rot = _rotulo(x["motivo"])
        assinado = bool(x["classificado_em"])
        rows.append(
            {
                "cells": [
                    t(x["nome"][:32], 600, _ND),
                    t(_fd(x["data"])),
                    t(f"{x['horas']:.2f}h"),
                    b(hc.TIPOS.get(x["tipo"], x["tipo"]), "warn" if x["tipo"] == "he100" else "info"),
                    b(rot, "ok" if x["repassavel"] else "mut"),
                    b("Repassável" if x["repassavel"] else "Custo nosso", "ok" if x["repassavel"] else "bad"),
                    t(brl(x["reais"]) if x["valor_hora"] else "sem valor-hora"),
                    t(x["posto"][:24]),
                    t(x["contrato"]),
                    b(
                        f"confirmada {_fd(x['classificado_em'], '%d/%m')}" if assinado else "sugestão",
                        "ok" if assinado else "warn",
                    ),
                ],
                "filtros": {
                    "motivo": rot,
                    "situacao": "confirmada" if assinado else "sugestão",
                    "repasse": "repassável" if x["repassavel"] else "custo nosso",
                },
                "actions": [] if assinado else _acoes_linha(x),
            }
        )
    return {
        "title": f"HE: classificar — {comp[5:7]}/{comp[:4]}",
        "sub": (
            f"{len(lns)} dia(s)-pessoa de hora extra ({horas_tot:.2f}h) · {len(pend)} aguardando confirmação · "
            f"{len(rep)} repassável(is) ao cliente ({horas_rep:.2f}h ≈ {brl(reais_rep)} ESTIMADO) · "
            f"{len(sem_expl)} sem explicação (nascem «falta de efetivo», custo nosso). "
            f"A HE vem do espelho de ponto (dia a dia); o motivo é SUGERIDO por cobertura ou movimentação do dia e só "
            f"vale depois que alguém confirma. O R$ é ESTIMATIVA (horas × fator × valor-hora do espelho) — "
            f"não é o valor da folha e nada aqui muda folha ou preço de contrato. "
            f"Levantamento desta abertura: {lev['novas']} linha(s) nova(s)."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Colaborador, posto ou contrato…",
        "filtros": [
            {"key": "motivo", "label": "Motivo"},
            {"key": "repasse", "label": "Repasse"},
            {"key": "situacao", "label": "Situação"},
        ],
        "grid": "1.6fr 0.8fr 0.6fr 0.8fr 1.4fr 1fr 1fr 1.2fr 1fr 1.1fr",
        "cols": [
            "Colaborador",
            "Dia",
            "Horas",
            "Tipo",
            "Motivo sugerido",
            "Repasse",
            "R$ estimado",
            "Posto",
            "Contrato",
            "Situação",
        ],
        "rows": rows,
    }


def _acoes_linha(x: dict) -> list[dict]:
    quem = f"{x['nome']} · {_fd(x['data'])} · {x['horas']:.2f}h {hc.TIPOS.get(x['tipo'], x['tipo'])}"
    return [
        {
            "title": f"Confirmar a classificação de {quem}",
            "endpoint": f"{_END}he-confirmar?id={x['id']}",
            "method": "POST",
            "btnLabel": "Confirmar",
            "submitLabel": "Confirmar",
            "btnStyle": "primary",
            "okMsg": "Classificação confirmada. Recarregue a tela.",
            "fields": [],
        },
        {
            "title": f"Reclassificar {quem} — motivo atual: {_rotulo(x['motivo'])}",
            "endpoint": f"{_END}he-reclassificar?id={x['id']}",
            "method": "POST",
            "btnLabel": "Reclassificar",
            "submitLabel": "Gravar",
            "okMsg": "Motivo trocado. Recarregue a tela.",
            "fields": [
                {"key": "motivo", "label": "Novo motivo*", "type": "select", "span": "span 2", "options": _OPC_MOTIVO},
                {
                    "key": "repassavel",
                    "label": "Repassável ao cliente",
                    "type": "select",
                    "span": "span 1",
                    "options": [
                        {"value": "", "label": "Como o motivo manda"},
                        {"value": "1", "label": "Sim — o cliente paga"},
                        {"value": "0", "label": "Não — custo nosso"},
                    ],
                },
                {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "ph": "opcional"},
            ],
        },
    ]


def _tela_lote(comps: list[str]) -> dict:
    return {
        "title": "HE: confirmar / reclassificar em lote",
        "sub": (
            "Trabalha a competência inteira ou só um motivo de cada vez. «Confirmar» assina as sugestões sem mudar "
            "nada (horas, motivo e repasse ficam como estão). «Reclassificar» troca o motivo — e o repasse acompanha "
            "o motivo, a menos que você diga o contrário. Nada aqui muda folha nem preço de contrato."
        ),
        "cta": "Aplicar",
        "type": "form",
        "submit": {
            "endpoint": f"{_END}he-classificar-lote",
            "okMsg": "Lote aplicado — veja o resultado.",
            "showResult": True,
            "confirm": "A ação vale para TODAS as linhas da competência que casam com o filtro. Confirma?",
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência*",
                "type": "select",
                "span": "span 1",
                "options": _opc_comp(comps),
            },
            {
                "key": "acao",
                "label": "Ação*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "confirmar", "label": "Confirmar as sugestões (não muda nada)"},
                    {"value": "reclassificar", "label": "Reclassificar (troca o motivo)"},
                ],
            },
            {
                "key": "motivo_atual",
                "label": "Só as linhas com este motivo",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "Todas as linhas da competência"}] + _OPC_MOTIVO,
            },
            {
                "key": "motivo_novo",
                "label": "Novo motivo (só para «Reclassificar»)",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "—"}] + _OPC_MOTIVO,
            },
            {
                "key": "repassavel",
                "label": "Repassável ao cliente",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "", "label": "Como o motivo manda"},
                    {"value": "1", "label": "Sim — o cliente paga"},
                    {"value": "0", "label": "Não — custo nosso"},
                ],
            },
            {"key": "observacao", "label": "Observação", "type": "text", "span": "span 2", "ph": "opcional"},
        ],
    }


async def _tela_por_contrato(db, comp: str | None) -> dict:
    if not comp:
        return {
            "title": "HE por contrato",
            "sub": "Nenhuma competência com hora extra no espelho de ponto ainda.",
            "cta": "—",
            "type": "table",
            "grid": "1fr",
            "cols": ["Situação"],
            "rows": [{"cells": [t("aguardando dado honesto")]}],
        }
    res = await hc.resumo_por_contrato(db, comp)
    tot_rep = round(sum(a["reais_repassavel"] for a in res), 2)
    tot_nao = round(sum(a["reais_nao_repassavel"] for a in res), 2)
    sem_vh = sum(a["sem_valor_hora"] for a in res)
    rows = [
        {
            "cells": [
                t(a["contrato"], 600, _ND),
                t(str(a["linhas"])),
                t(f"{a['horas_repassavel']:.2f}h"),
                t(brl(a["reais_repassavel"])),
                t(f"{a['horas_nao_repassavel']:.2f}h"),
                t(brl(a["reais_nao_repassavel"])),
                b(
                    f"{a['pendentes']} a confirmar" if a["pendentes"] else "tudo confirmado",
                    "warn" if a["pendentes"] else "ok",
                ),
            ],
            "filtros": {"contrato": a["contrato"]},
        }
        for a in res
    ]
    return {
        "title": f"HE por contrato — {comp[5:7]}/{comp[:4]}",
        "sub": (
            f"{len(res)} agrupamento(s) · repassável ≈ {brl(tot_rep)} · custo nosso ≈ {brl(tot_nao)}. "
            f"O R$ é ESTIMATIVA: horas × fator do tipo (50% = 1,5 · 100% = 2,0) × valor-hora da pessoa no espelho "
            f"de ponto. NÃO é o valor pago na folha (lá a HE sai por outra régua) e NÃO é uma cobrança emitida. "
            + (f"{sem_vh} linha(s) sem valor-hora no espelho entram como R$ 0,00. " if sem_vh else "")
            + "Contrato «—» = posto sem contrato amarrado (ou cliente com mais de um contrato ativo)."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Contrato…",
        "filtros": [{"key": "contrato", "label": "Contrato"}],
        "grid": "1.2fr 0.7fr 1fr 1.2fr 1fr 1.2fr 1.2fr",
        "cols": [
            "Contrato",
            "Linhas",
            "Horas repassáveis",
            "R$ repassável (estim.)",
            "Horas custo nosso",
            "R$ custo nosso (estim.)",
            "Situação",
        ],
        "rows": rows,
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        comps = await _comps(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        comps = []
        logger.error("dgx w3: competências falharam: %s", exc, exc_info=True)
    comp = comps[0] if comps else None
    montagens = [
        ("he-classificar", "HE: classificar", lambda: _tela_classificar(db, comp)),
        ("he-classificar-lote", "HE: lote", lambda: _tela_lote(comps)),
        ("he-por-contrato", "HE por contrato", lambda: _tela_por_contrato(db, comp)),
    ]
    for tid, titulo, fn in montagens:
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)
    grupo = (out or {}).get("g-ponto")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-ponto", tid)
    return mine


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _quem(current_user) -> str:
    return str(getattr(current_user, "email", None) or getattr(current_user, "id", "") or "")[:120]


def _tri(v) -> bool | None:
    s = str(v or "").strip().lower()
    if s in ("1", "true", "sim"):
        return True
    if s in ("0", "false", "nao", "não"):
        return False
    return None


@router.post("/action/he-confirmar", dependencies=[Depends(_require_dp)])
async def rd_he_confirmar(current_user: CurrentActiveUser, id: int, db: AsyncSession = Depends(get_db)) -> dict:  # noqa: A002 — `id` é o nome do query param na URL da ação
    n = await hc.confirmar(db, ids=[id], quem=_quem(current_user), so_pendentes=False)
    if not n:
        raise HTTPException(status_code=404, detail="Linha de HE não encontrada.")
    return {"ok": True, "message": "Classificação confirmada — horas e valor não mudaram."}


@router.post("/action/he-reclassificar", dependencies=[Depends(_require_dp)])
async def rd_he_reclassificar(
    current_user: CurrentActiveUser,
    id: int,  # noqa: A002 — nome do query param na URL da ação
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        n = await hc.reclassificar(
            db,
            novo_motivo=str(payload.get("motivo") or ""),
            ids=[id],
            repassavel=_tri(payload.get("repassavel")),
            observacao=str(payload.get("observacao") or "").strip() or None,
            quem=_quem(current_user),
        )
    except hc.HEClassificacaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    if not n:
        raise HTTPException(status_code=404, detail="Linha de HE não encontrada.")
    return {"ok": True, "message": "Motivo trocado — horas e valor não mudaram."}


@router.post("/action/he-classificar-lote", dependencies=[Depends(_require_dp)])
async def rd_he_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    comp = str(payload.get("competencia") or "").strip()
    acao = str(payload.get("acao") or "").strip()
    filtro = str(payload.get("motivo_atual") or "").strip() or None
    if acao not in ("confirmar", "reclassificar"):
        raise HTTPException(status_code=400, detail="Escolha Confirmar ou Reclassificar.")
    try:
        if acao == "confirmar":
            n = await hc.confirmar(db, competencia=comp, motivo=filtro, quem=_quem(current_user))
            msg = f"{n} linha(s) confirmada(s) em {comp[5:7]}/{comp[:4]} — nenhuma hora e nenhum valor mudou."
        else:
            n = await hc.reclassificar(
                db,
                novo_motivo=str(payload.get("motivo_novo") or ""),
                competencia=comp,
                motivo=filtro,
                repassavel=_tri(payload.get("repassavel")),
                observacao=str(payload.get("observacao") or "").strip() or None,
                quem=_quem(current_user),
            )
            msg = f"{n} linha(s) reclassificada(s) em {comp[5:7]}/{comp[:4]} — nenhuma hora e nenhum valor mudou."
    except hc.HEClassificacaoErro as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"ok": True, "message": msg, "resultado": {"linhas": n, "competencia": comp, "acao": acao}}
