"""DGX AA1 — Compra → catálogo → orçamento: o miolo do fluxo que o dono desenhou (24/09/2026).

O dono: *«baseado nas notas fiscais de compra da Conecta Eletrônica cadastrar os produtos, ter
cuidado com duplicidades, pois aí na hora de fazer o orçamento fazemos pelo CRM, já estará lá com
toda a descrição, só seleciona o item e as quantidades»*. E: *«nos produtos cadastrados deixem sem
valor — quando eu for fazer os orçamentos eu edito o preço»*.

A regra e a medição moram em `financial/services/catalogo_compra.py` (docstring lá: por que
`products` é a fonte única, por que casar por código é falso, por que «mesmo NCM» não é «mesmo
produto»). Aqui só tela e ação.

**Por que em Suprimentos e não no Fiscal:** o catálogo comercial é `products`, e é de Suprimentos
que ele é alimentado (a nota de compra chega aqui, `materiais`/`almoxarifado` da F9 leem daqui).
No Fiscal o mesmo item aparece como CADASTRO PARA EMITIR (`produtos-fiscais`, da Z1) — outra
pergunta. O elo entre os dois é `fin_produtos.product_id`, criado quando alguém aprova aqui.

**Nada entra sozinho:** a tela mostra a proposta com o porquê e o score de cada linha, e quem
aprova é gente. `classificar` não cria produto nenhum.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto) — igual Z1.
router = APIRouter()

from modules.financial.services import catalogo_compra as cc  # noqa: E402
from modules.operacional.controllers.redesign_data_controller import b, brl, t  # noqa: E402

logger = logging.getLogger(__name__)
_ACT = "/api/v1/redesign/action/"
_ICO = "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
_GRUPO = "Materiais & estoque"

ABAS = [
    ("catalogo-candidatos", "Compra → catálogo (aprovar)"),
    ("catalogo-aprovar-lote", "Aprovar em lote"),
    ("catalogo-produtos", "Catálogo vindo da compra"),
]
MENU: list[dict] = [{"id": i, "label": r, "icon": _ICO, "grupo": _GRUPO} for i, r in ABAS]

_TOM = {"novo": "info", "igual": "warn", "variacao": "ok"}
_ROTULO = {"novo": "Novo", "igual": "Já existe", "variacao": "Variação"}


def _quem(u) -> str:
    return (
        str((u or {}).get("email") or (u or {}).get("nome") or "usuário")
        if isinstance(u, dict)
        else str(getattr(u, "email", None) or getattr(u, "nome", None) or "usuário")
    )


def _ids(payload: dict) -> list[int]:
    bruto = payload.get("ids") if isinstance(payload.get("ids"), list) else str(payload.get("ids") or "")
    if isinstance(bruto, list):
        return [int(x) for x in bruto if str(x).strip().isdigit()]
    return [int(x) for x in bruto.replace(";", ",").split(",") if x.strip().isdigit()]


# --------------------------------------------------------------------------------- telas


async def _tela_candidatos(db) -> dict:
    linhas = (
        await db.execute(
            text(
                "SELECT c.id, c.item_code, c.descricao, coalesce(c.ncm,'—'), coalesce(c.unidade,'—'), "
                "       c.custo_unitario, c.classe, c.score, c.motivo, coalesce(p.name,''), c.alvo_product_id "
                "  FROM fin_catalogo_candidatos c "
                "  LEFT JOIN products p ON p.id = c.alvo_product_id "
                " WHERE c.status = 'pendente' "
                " ORDER BY CASE c.classe WHEN 'igual' THEN 0 WHEN 'variacao' THEN 1 ELSE 2 END, c.score DESC, c.item_code"
            )
        )
    ).fetchall()
    conta = {k: sum(1 for r in linhas if r[6] == k) for k in cc.CLASSES}
    rows = []
    for r in linhas:
        cid, item_code, desc, ncm, un, custo, classe, score, motivo, alvo_nome, alvo_pid = r
        acoes = [
            {
                "title": f"Aprovar «{str(desc)[:40]}»",
                "endpoint": f"{_ACT}catalogo-aprovar",
                "method": "POST",
                "btnLabel": "Aprovar",
                "btnStyle": "solid",
                "submitLabel": "Confirmar",
                "okMsg": "Aprovado. Recarregue a aba.",
                "fields": [{"key": "ids", "label": "id", "type": "text", "value": str(cid), "span": "span 1"}],
            },
            {
                "title": f"Descartar «{str(desc)[:40]}» (não entra no catálogo)",
                "endpoint": f"{_ACT}catalogo-rejeitar",
                "method": "POST",
                "btnLabel": "Descartar",
                "btnStyle": "outline",
                "submitLabel": "Confirmar",
                "okMsg": "Descartado. Recarregue a aba.",
                "fields": [{"key": "ids", "label": "id", "type": "text", "value": str(cid), "span": "span 1"}],
            },
        ]
        # A régua guarda o parecido mesmo quando não teve certeza. Este botão é o «o humano
        # confirma o que a régua não soube» — sem ele, o jeito de corrigir seria duplicar.
        if alvo_pid is not None:
            acoes.append(
                {
                    "title": (
                        f"Marcar «{str(desc)[:36]}» como JÁ EXISTENTE — é «{str(alvo_nome)[:36]}»"
                        if classe == "novo"
                        else f"Marcar «{str(desc)[:36]}» como produto NOVO (não é «{str(alvo_nome)[:30]}»)"
                    ),
                    "endpoint": f"{_ACT}catalogo-reclassificar",
                    "method": "POST",
                    "btnLabel": "É este produto" if classe == "novo" else "É novo mesmo",
                    "btnStyle": "outline",
                    "submitLabel": "Confirmar",
                    "okMsg": "Reclassificado. Recarregue a aba.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(cid), "span": "span 1"},
                        {
                            "key": "classe",
                            "label": "classe",
                            "type": "text",
                            "value": "igual" if classe == "novo" else "novo",
                            "span": "span 1",
                        },
                    ],
                }
            )
        rows.append(
            {
                "cells": [
                    t(str(item_code), 600, "#0F1B3A"),
                    t(str(desc)[:64]),
                    b(_ROTULO.get(classe, classe), _TOM.get(classe, "info")),
                    t(f"{float(score or 0):.2f}"),
                    t(str(ncm)),
                    t(str(un)),
                    t(brl(custo) + " (custo)" if custo else "—"),
                    t(str(motivo)[:150]),
                ],
                "actions": acoes,
            }
        )
    return {
        "title": "Compra → catálogo: a proposta",
        "sub": (
            f"{len(linhas)} linha(s) de nota de compra aguardando decisão · {conta.get('novo', 0)} novo(s), "
            f"{conta.get('igual', 0)} já existe(m), {conta.get('variacao', 0)} variação(ões). "
            "«Novo» é o padrão SEGURO: fundir é o ato perigoso, então a régua só funde com sinal limpo. "
            "O valor da coluna é o CUSTO da nota — nunca vira preço de venda (decisão do dono em 24/09)."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar descrição, código ou motivo…",
        "cols": ["Código na nota", "Descrição do fornecedor", "Classe", "Semelhança", "NCM", "Un.", "Custo", "Por quê"],
        "grid": "1fr 2.4fr 0.9fr 0.8fr 0.9fr 0.5fr 1fr 3fr",
        "rows": rows,
    }


async def _tela_lote(db) -> dict:
    r = await cc.resumo(db)
    pend = r["pendente"]
    return {
        "title": "Aprovar em lote",
        "sub": (
            f"Pendentes: {pend.get('novo', 0)} novo(s) · {pend.get('igual', 0)} já existe(m) · "
            f"{pend.get('variacao', 0)} variação(ões). Já decididos: {r.get('aprovado', 0)} aprovado(s), "
            f"{r.get('rejeitado', 0)} descartado(s). Cada linha aprovada grava quem, quando, com que "
            "semelhança e por qual motivo — fusão sem registro é o defeito que esta tela existe para impedir."
        ),
        "cta": "—",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "catalogo-aprovar-lote",
            "okMsg": "Feito — veja a aba «Catálogo vindo da compra».",
            "showResult": True,
            "confirm": (
                "Vai cadastrar/ligar todos os pendentes da classe escolhida, com o seu nome gravado como "
                "quem decidiu. Nenhum preço de venda é escrito."
            ),
        },
        "fields": [
            {
                "key": "classe",
                "label": "O que aprovar*",
                "type": "select",
                "span": "span 2",
                "options": [
                    {"value": "novo", "label": "Só os NOVOS — cria produto no catálogo"},
                    {"value": "igual", "label": "Só os JÁ EXISTENTES — não cria nada, só liga"},
                    {
                        "value": "tudo",
                        "label": "Tudo — novos, já existentes e variações (a variação precisa do representante)",
                    },
                ],
            }
        ],
    }


async def _tela_catalogo(db) -> dict:
    linhas = (
        await db.execute(
            text(
                "SELECT p.code, p.name, coalesce(p.unit_of_measure,'—'), coalesce(p.ncm,'—'), "
                "       c.item_code, c.classe, c.decidido_por, c.decidido_em, "
                "       (SELECT count(*) FROM fin_catalogo_candidatos v "
                "         WHERE v.product_id = p.id AND v.classe = 'variacao' AND v.status = 'aprovado') AS variacoes, "
                "       coalesce(f.codigo,'') AS fiscal "
                "  FROM fin_catalogo_candidatos c "
                "  JOIN products p ON p.id = c.product_id "
                "  LEFT JOIN fin_produtos f ON f.product_id = p.id "
                " WHERE c.status = 'aprovado' AND c.classe <> 'variacao' "
                " ORDER BY c.decidido_em DESC NULLS LAST, p.code"
            )
        )
    ).fetchall()
    tot = (await db.execute(text("SELECT count(*) FROM products WHERE coalesce(ativo, true)"))).scalar() or 0
    elos = (await db.execute(text("SELECT count(*) FROM fin_produtos WHERE product_id IS NOT NULL"))).scalar() or 0
    fis = (await db.execute(text("SELECT count(*) FROM fin_produtos"))).scalar() or 0
    return {
        "title": "Catálogo vindo da compra",
        "sub": (
            f"{len(linhas)} produto(s) decidido(s) aqui · catálogo `products` tem {tot} item(ns) ativos "
            f"e é a FONTE ÚNICA — é dele que o orçamento do CRM lê (`crm/services/catalogo.py`) · "
            f"face fiscal `fin_produtos`: {fis} linha(s), {elos} já ligada(s) ao produto comercial. "
            "Nenhuma linha tem preço de venda: o dono digita o preço do dia no orçamento."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar produto, código ou quem aprovou…",
        "cols": [
            "Código",
            "Produto",
            "Un.",
            "NCM",
            "Item na nota",
            "Como entrou",
            "Variações",
            "Face fiscal",
            "Aprovado por",
        ],
        "grid": "1fr 2.6fr 0.5fr 0.9fr 1fr 1fr 0.8fr 1fr 1.6fr",
        "rows": [
            {
                "cells": [
                    t(str(r[0]), 600, "#0F1B3A"),
                    t(str(r[1])[:60]),
                    t(str(r[2])),
                    t(str(r[3])),
                    t(str(r[4])),
                    b(_ROTULO.get(r[5], r[5]), _TOM.get(r[5], "info")),
                    t(f"{r[8]} tamanho(s)" if r[8] else "—"),
                    b("ligada", "ok") if r[9] else b("sem face fiscal", "warn"),
                    t(str(r[6] or "—")[:26]),
                ]
            }
            for r in linhas
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    out = out if out is not None else {}
    try:
        await cc._ensure(db)
        await cc.classificar_se_houver_novidade(db)
        out["catalogo-candidatos"] = await _tela_candidatos(db)
        out["catalogo-aprovar-lote"] = await _tela_lote(db)
        out["catalogo-produtos"] = await _tela_catalogo(db)
    except Exception:
        logger.exception("dgx aa1: falha ao montar as telas do catálogo")
    return out


# --------------------------------------------------------------------------------- ações


@router.post("/action/catalogo-aprovar")
async def rd_catalogo_aprovar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    r = await cc.aprovar(db, _ids(payload or {}), _quem(current_user))
    div = " · NCM divergente, NÃO sobrescrito: " + "; ".join(r["divergencias"][:5]) if r["divergencias"] else ""
    return {
        "ok": True,
        "result": r,
        "message": (
            f"{r['total']} candidato(s) aprovado(s) · {r['criados']} produto(s) criado(s) SEM preço · "
            f"{r['elos_fiscais']} elo(s) com o cadastro fiscal{div}"
        ),
    }


@router.post("/action/catalogo-rejeitar")
async def rd_catalogo_rejeitar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    n = await cc.rejeitar(db, _ids(payload or {}), _quem(current_user))
    return {"ok": True, "result": {"descartados": n}, "message": f"{n} candidato(s) descartado(s)."}


@router.post("/action/catalogo-reclassificar")
async def rd_catalogo_reclassificar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """O humano confirma o que a régua não soube: «é este produto» / «é novo mesmo»."""
    p = payload or {}
    r = await cc.reclassificar(db, int(str(p.get("id") or 0) or 0), str(p.get("classe") or ""), _quem(current_user))
    return {"ok": True, "result": r, "message": f"Candidato {r['item_code']} agora é «{r['classe']}»."}


@router.post("/action/catalogo-aprovar-lote")
async def rd_catalogo_aprovar_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Aprova todos os pendentes de uma classe. «tudo» inclui as variações, que precisam do pai."""
    classe = str((payload or {}).get("classe") or "").strip()
    onde = "" if classe == "tudo" else " AND classe = :c"
    ids = [
        r[0]
        for r in (
            await db.execute(
                text(f"SELECT id FROM fin_catalogo_candidatos WHERE status = 'pendente'{onde} ORDER BY id"),
                {} if classe == "tudo" else {"c": classe},
            )
        ).fetchall()
    ]
    r = await cc.aprovar(db, ids, _quem(current_user))
    div = " · NCM divergente, NÃO sobrescrito: " + "; ".join(r["divergencias"][:8]) if r["divergencias"] else ""
    return {
        "ok": True,
        "result": r,
        "message": (
            f"{r['total']} candidato(s) aprovado(s) · {r['criados']} produto(s) criado(s) SEM preço de venda · "
            f"{r['elos_fiscais']} elo(s) com o cadastro fiscal{div}"
        ),
    }
