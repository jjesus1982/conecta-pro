"""Revisão do LALUR — a fila de despesas sem decisão, e a decisão por linha.

Passo 3 da tarefa C8 do plano de 26/09. O livro existe desde 27/09 (`lalur_service`), mas
um livro cuja fila só se preenche pelo terminal é prateleira: quem decide é o contador, e
ele decide por linha, olhando o histórico.

O que esta tela NÃO faz, de propósito: não sugere código. Oferece os campos e exige o
código do Anexo para adição/exclusão — «A.069, despesas não NECESSÁRIAS» não é derivável do
plano de contas, e um código sugerido errado é um erro que ninguém revisa. Uma linha só
sai da fila com decisão registrada; «não revisado» nunca vira «dedutível» por omissão.

Trimestre corrente por padrão (Lucro Real trimestral). Só a Eletrônica: a Patrimonial é
Simples e não tem LALUR.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, brl, t

logger = logging.getLogger(__name__)

_END = "/api/v1/redesign/action/"
SLUG = "lalur-revisao"
#: A empresa do Lucro Real. Mesmo id de `apuracao_lucro_real_service.EMPRESA_PRINCIPAL_ID`.
ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
LIMITE_LINHAS = 200

CODIGOS_COMUNS = [
    {"value": "", "label": "— (obrigatório para adição/exclusão) —"},
    {"value": "A.069", "label": "A.069 — despesas não necessárias à atividade"},
    {"value": "A.154", "label": "A.154 — multas por infração fiscal"},
    {"value": "A.011", "label": "A.011 — provisões não dedutíveis (exceto férias e 13º)"},
    {"value": "A.036", "label": "A.036 — brindes"},
    {"value": "A.049", "label": "A.049 — doações não dedutíveis"},
    {"value": "outro", "label": "outro — digite no campo ao lado"},
]


def _trimestre_corrente() -> tuple[int, int, list[str]]:
    hoje = date.today()
    tri = (hoje.month - 1) // 3 + 1
    meses = [f"{hoje.year}-{m:02d}" for m in range((tri - 1) * 3 + 1, tri * 3 + 1)]
    return hoje.year, tri, meses


async def telas(db, out: dict) -> None:  # noqa: ARG001 — mesma assinatura dos irmãos
    from modules.financial.services import lalur_service as L  # noqa: N812, PLC0415

    ano, tri, meses = _trimestre_corrente()
    try:
        fila = await run_in_threadpool(L.fila_de_revisao, ELETRONICA, meses, LIMITE_LINHAS)
        faltam = await run_in_threadpool(L.pendencias, ELETRONICA, meses)
        pa_i = await run_in_threadpool(L.parte_a, ELETRONICA, meses, "I")
    except Exception as exc:  # noqa: BLE001
        out[SLUG] = {
            "title": "Revisão do LALUR",
            "type": "table",
            "cta": "—",
            "sub": f"indisponível: {type(exc).__name__}: {exc}"[:220],
            "cols": ["—"],
            "grid": "1fr",
            "rows": [{"cells": [t("O livro não respondeu — veja o log.", 500)]}],
        }
        return

    linhas = []
    for f in fila:
        linhas.append(
            {
                "cells": [
                    t(f["competencia"], 600, "#0F1B3A"),
                    t(f["conta"], 500),
                    t(brl(f["valor"]), 600),
                    t((f["historico"] or "—")[:90]),
                    t(f["documento"] or "—", 500, "#64748B"),
                    b("sem decisão", "warn"),
                ],
                "filtros": {"conta": f["conta"], "competencia": f["competencia"]},
                "_meta": {"entry_id": f["entry_id"], "valor": f["valor"]},
                "actions": [
                    {
                        "title": f"Decidir — {f['conta']} · {brl(f['valor'])}",
                        "endpoint": f"{_END}lalur-decidir?entry_id={f['entry_id']}",
                        "method": "POST",
                        "btnLabel": "Decidir",
                        "submitLabel": "Registrar no livro",
                        "btnStyle": "outline",
                        "fields": [
                            {
                                "key": "decisao",
                                "label": "Decisão*",
                                "type": "select",
                                "span": "span 2",
                                "options": [
                                    {"value": "D", "label": "Dedutível — fica como está"},
                                    {"value": "A", "label": "Adição — não dedutível (exige código do Anexo I)"},
                                    {
                                        "value": "E",
                                        "label": "Exclusão — receita não tributável (exige código do Anexo II)",
                                    },
                                ],
                                "value": "",
                            },
                            {
                                "key": "codigo_rfb",
                                "label": "Código do Anexo (IN 1700)",
                                "type": "select",
                                "options": CODIGOS_COMUNS,
                                "value": "",
                            },
                            {"key": "codigo_outro", "label": "Outro código", "type": "text", "value": ""},
                            {
                                "key": "tributo",
                                "label": "Tributo",
                                "type": "select",
                                "value": "ambos",
                                "options": [
                                    {"value": "ambos", "label": "IRPJ e CSLL"},
                                    {"value": "I", "label": "só IRPJ"},
                                    {"value": "C", "label": "só CSLL"},
                                ],
                            },
                            {
                                "key": "valor",
                                "label": "Valor (R$) — parcial se for abrir em partes",
                                "type": "number",
                                "value": f"{f['valor']:.2f}",
                            },
                            {
                                "key": "historico",
                                "label": "Histórico* (o que justifica — vai para a fiscalização)",
                                "type": "text",
                                "span": "span 2",
                                "value": "",
                            },
                        ],
                    }
                ],
            }
        )

    out[SLUG] = {
        "title": "Revisão do LALUR",
        "type": "table",
        "cta": "—",
        "sub": (
            f"{tri}º trimestre/{ano} · {faltam} despesa(s) sem decisão (mostrando até {LIMITE_LINHAS}, por valor "
            f"decrescente) · {pa_i['lancamentos']} ajuste(s) já decidido(s) no IRPJ. Uma linha só sai daqui com decisão "
            "registrada: dedutível, adição ou exclusão — e adição/exclusão exigem o código do Anexo. Para abrir uma "
            "despesa em partes (ex.: DAS = principal + multa + juros), registre a parte com o valor parcial e repita."
        ),
        "searchHint": "Buscar conta ou histórico…",
        "filterLabel": "Conta",
        "grid": "0.7fr 0.8fr 0.9fr 2.4fr 1fr 0.9fr",
        "cols": ["Competência", "Conta", "Valor", "Histórico", "Documento", "Situação"],
        "rows": linhas
        or [{"cells": [t("Nenhuma despesa do trimestre sem decisão — Parte A fechada.", 500)] + [t("—")] * 5}],
        "kpis": [
            {"v": str(faltam), "l": "Sem decisão no trimestre", "color": "#B45309" if faltam else "#16A34A"},
            {"v": str(pa_i["lancamentos"]), "l": "Ajustes decididos (IRPJ)", "color": "#0F1B3A"},
        ],
    }


# ───────────────────────────────── AÇÕES ─────────────────────────────────
router = APIRouter()


@router.post("/action/lalur-decidir")
async def rd_lalur_decidir(
    current_user: CurrentActiveUser,  # noqa: ARG001 — exigido pela porta; quem decidiu vai no histórico
    entry_id: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),  # noqa: ARG001 — assinatura da porta; o livro usa a própria conexão
) -> dict:
    from modules.financial.services import lalur_service as L  # noqa: N812, PLC0415

    p = {k: (str(v).strip() if v is not None else "") for k, v in (payload or {}).items()}
    try:
        eid = int(entry_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Lançamento inválido — recarregue a tela.") from None
    decisao = p.get("decisao", "").upper()
    if decisao not in ("D", "A", "E"):
        raise HTTPException(status_code=400, detail="Escolha a decisão: dedutível, adição ou exclusão.")
    codigo = p.get("codigo_rfb", "")
    if codigo == "outro":
        codigo = p.get("codigo_outro", "")
    if decisao in ("A", "E") and not codigo:
        raise HTTPException(
            status_code=422,
            detail="Adição e exclusão exigem o código do Anexo da IN 1700. Sem código a linha não se defende.",
        )
    historico = p.get("historico", "")
    if len(historico) < 8:
        raise HTTPException(
            status_code=422,
            detail="Histórico curto demais — escreva o que justifica a decisão; é o que a fiscalização lê.",
        )
    try:
        valor = (
            float(p.get("valor", "").replace(".", "").replace(",", "."))
            if "," in p.get("valor", "")
            else float(p.get("valor", "") or 0)
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Valor inválido.") from None
    if valor <= 0:
        raise HTTPException(status_code=400, detail="Valor tem de ser positivo — o sinal é a decisão.")
    quem = getattr(current_user, "email", None) or getattr(current_user, "id", "?")
    hist = f"{historico} [decidido por {quem} em {date.today():%d/%m/%Y}]"
    # A competência é a do lançamento, não a de hoje: decisão fora da competência da despesa
    # cairia em outro período e o ajuste não bateria com o razão.
    _, _, meses = _trimestre_corrente()
    linha = next(
        (f for f in await run_in_threadpool(L.fila_de_revisao, ELETRONICA, meses, 100000) if f["entry_id"] == str(eid)),
        None,
    )
    if not linha:
        raise HTTPException(
            status_code=409, detail="Essa despesa já tem decisão (ou não é deste trimestre) — recarregue a tela."
        )
    tributos = ("I", "C") if p.get("tributo", "ambos") == "ambos" else (p["tributo"],)
    ids = []
    try:
        for trib in tributos:
            ids.append(
                await run_in_threadpool(
                    L.decidir,
                    ELETRONICA,
                    str(eid),
                    linha["competencia"],
                    trib,
                    decisao,
                    valor,
                    hist,
                    codigo_rfb=codigo or None,
                )
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "ok": True,
        "lancamentos": ids,
        "message": f"Registrado no livro: {L.TIPOS[decisao]} — {brl(valor)}.",
        "toast": "Decisão registrada",
    }
