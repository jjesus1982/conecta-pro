"""DGX W2 — Fatura como DOCUMENTO (`/Faturas` do DGX), 24/09/2026.

O que foi cavado antes de construir (sandbox = cópia de produção de 23/09):
  · `receivable_accounts`: 52 linhas (31 de origem 'contrato', R$ 1.110.989,70) — é o RECEBÍVEL,
    o registro do que é devido. Nasce de `gerar_recebiveis` (contrato × competência), tem um valor
    só, sem itens, sem número próprio e sem papel. Não é a fatura.
  · `fin_faturas` / `fin_fatura_itens`: `to_regclass` NULL — não existiam.
  · `contract_items`: 16 linhas, mas só 2 dos 14 contratos ativos as têm; `posts.salario_base`
    (a vaga da T3) está NULL em 17/17. Por isso «a partir do contrato» usa os itens do contrato
    quando existem com valor, e senão UMA linha com o `monthly_value` — nunca número inventado.
  · `fin_recibos` (F11): numeração sequencial sem buraco com `pg_advisory_xact_lock`. Copiada aqui.
  · `fin_condicoes_pagamento` (4 semeadas) e `fin_codigos_servico` (8, LC 116) — reusados nos
    selects; nenhum cadastro novo foi criado.
  · `crm_fontes_pagadoras` (F12, 0 linhas hoje): quem PAGA pode não ser quem contrata. A fatura
    sai no nome da fonte quando há — e `receivable_accounts.fonte_pagadora_id` já existia.
  · NFS-e (`modules/fiscal`) NÃO é tocada: a nota é o documento fiscal, a fatura é o comercial que
    a antecede. `fin_faturas.nfse_id` fica como elo para quem quiser amarrar depois.

Regra em `modules/financial/services/fin_faturas.py` (o oráculo chama ela direto).
Prefixo `_` = o discovery pula; `financeiro.py` inclui `router` e chama `telas(db, out)` antes de
`montar_grupos` (abas em `_fin_grupos.GRUPOS`). DDL idempotente em `fin_faturas.ensure`.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db
from modules.financial.services import fin_faturas as svc

logger = logging.getLogger(__name__)

#: ANTES do import do data_controller (mesmo motivo do F1: o ciclo de import fecha com o router pronto).
router = APIRouter()



# Import TARDIO de propósito: `_dgx_f11_financeiro` importa o `redesign_data_controller`, que
# importa os builders — inclusive este. No topo, o ciclo fecha com o F11 ainda pela metade e o
# builder do Financeiro inteiro deixa de carregar («cannot import name '_comp' from partially
# initialized module», visto em 24/09/2026 na saída de um oráculo). Delegar mantém a fonte única.
def _comp(v):
    from modules.operacional.controllers.redesign_builders._dgx_f11_financeiro import _comp as _f  # noqa: PLC0415

    return _f(v)


def _dec(v):
    from modules.operacional.controllers.redesign_builders._dgx_f11_financeiro import _dec as _f  # noqa: PLC0415

    return _f(v)


from modules.operacional.controllers.redesign_data_controller import (  # noqa: E402
    _helpers,
    b,
    brl,
    doc,
    t,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:financeiro"))]

#: ids de tela que este arquivo entrega — o oráculo confere que cada um tem aba em `_fin_grupos`.
IDS = ("faturas", "fatura-nova", "fatura-itens", "faturas-copiar-lote")

_BADGE = {
    "rascunho": "mut",
    "emitida": "info",
    "enviada": "warn",
    "paga": "ok",
    "cancelada": "bad",
}

#: uma linha por item: `descrição | quantidade | valor unitário | LC 116 (opcional)`.
_PH_ITENS = "Posto de portaria 24h | 2 | 20.306,00 | 11.02\nAdicional noturno | 1 | 1.200,00"


def itens_texto(txt: str) -> list[dict]:
    """Mesma gramática de item do F9/U5: uma linha por item, campos separados por `|`."""
    out: list[dict] = []
    for ln in (txt or "").splitlines():
        if not ln.strip():
            continue
        p = [x.strip() for x in ln.split("|")]
        if len(p) < 3:
            raise HTTPException(
                status_code=400,
                detail=f"Item «{ln[:40]}»: use `descrição | quantidade | valor unitário` (LC 116 opcional no fim).",
            )
        try:
            qtd = Decimal(p[1].replace(".", "").replace(",", ".")) if p[1] else Decimal("1")
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Item «{p[0][:40]}»: quantidade inválida.") from None
        out.append(
            {
                "descricao": p[0],
                "quantidade": qtd,
                "valor_unitario": _dec(p[2], f"Item «{p[0][:30]}» — valor unitário"),
                "_lc116": p[3] if len(p) > 3 else None,
            }
        )
    return out


async def _resolver_lc116(db: AsyncSession, itens: list[dict]) -> list[dict]:
    """`11.02` → id de `fin_codigos_servico` (F11). Código desconhecido fica sem vínculo, não erra."""
    codigos = {str(i.get("_lc116")).strip() for i in itens if i.get("_lc116")}
    mapa: dict[str, int] = {}
    if codigos:
        for r in (
            await db.execute(
                text("SELECT item_lc116, id FROM fin_codigos_servico WHERE item_lc116 = ANY(:c)"),
                {"c": list(codigos)},
            )
        ).fetchall():
            mapa[r[0]] = r[1]
    for i in itens:
        lc = str(i.pop("_lc116", "") or "").strip()
        if lc and lc in mapa:
            i["codigo_servico_id"] = mapa[lc]
    return itens


def _data(v, rotulo: str) -> date:
    try:
        return date.fromisoformat(str(v or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{rotulo}: data inválida.") from None


async def _opts(db: AsyncSession, sql: str, vazio: str, params: dict | None = None) -> list[dict]:
    rows = (await db.execute(text(sql), params or {})).fetchall()
    return [{"value": "", "label": vazio}] + [{"value": str(r[0]), "label": r[1]} for r in rows]


# ── TELAS ───────────────────────────────────────────────────────────────────────────────────
async def telas(db, out: dict | None = None) -> dict:
    await svc.ensure(db)
    mine, _safe, _tbl = _helpers(db)
    out = out if out is not None else {}
    hoje = date.today()
    comp_atual = f"{hoje.year:04d}-{hoje.month:02d}"

    cli_opts = await _opts(db, "SELECT id::text, name FROM clients WHERE ativo ORDER BY name", "— escolha o cliente —")
    ctr_opts = await _opts(
        db,
        "SELECT c.id::text, coalesce(c.contract_number,'s/nº')||' · '||coalesce(cl.name,'?') "
        "  FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id "
        " WHERE c.status = 'active' ORDER BY cl.name",
        "— sem contrato (fatura avulsa) —",
    )
    cond_opts = await _opts(
        db,
        "SELECT id, nome||' ('||parcelas||'x)' FROM fin_condicoes_pagamento WHERE ativo ORDER BY id",
        "— à combinar —",
    )
    fp_opts = await _opts(
        db,
        "SELECT f.id, f.razao_social||' (paga por '||coalesce(c.name,'?')||')' FROM crm_fontes_pagadoras f "
        "  LEFT JOIN clients c ON c.id = f.cliente_id WHERE f.ativo ORDER BY c.name, f.razao_social",
        "— o próprio cliente —",
    )
    comps = [
        r[0]
        for r in (
            await db.execute(text("SELECT DISTINCT competencia FROM fin_faturas ORDER BY competencia DESC"))
        ).fetchall()
    ]

    # 1) Lista de faturas ─────────────────────────────────────────────────────────────────
    linhas = (
        await db.execute(
            text(
                "SELECT f.id, f.numero, f.competencia, f.vencimento, f.valor_total, f.status, "
                "       coalesce(fp.razao_social, c.name, '—'), ct.contract_number, f.receivable_id::text, "
                "       (SELECT count(*) FROM fin_fatura_itens i WHERE i.fatura_id = f.id), "
                "       (fp.id IS NOT NULL) "
                "  FROM fin_faturas f "
                "  LEFT JOIN clients c ON c.id = f.cliente_id "
                "  LEFT JOIN crm_fontes_pagadoras fp ON fp.id = f.fonte_pagadora_id "
                "  LEFT JOIN contracts ct ON ct.id = f.contrato_id "
                " ORDER BY f.competencia DESC, coalesce(f.numero, 999999), f.id DESC LIMIT 400"
            )
        )
    ).fetchall()

    svc_opts = await _opts(
        db,
        "SELECT id, item_lc116||' — '||left(descricao, 60) FROM fin_codigos_servico WHERE ativo ORDER BY item_lc116",
        "— sem código —",
    )

    def _acao(titulo, endpoint, btn, fid, *, estilo="outline", confirm=None, ok="Feito. Recarregue."):
        a = {
            "title": titulo,
            "endpoint": f"{_ACT}{endpoint}",
            "method": "POST",
            "btnLabel": btn,
            "btnStyle": estilo,
            "submitLabel": "Confirmar",
            "okMsg": ok,
            "fields": [{"key": "id", "label": "id", "type": "text", "value": str(fid), "span": "span 1"}],
        }
        if confirm:
            a["confirm"] = confirm
        return a

    def _linha(r):
        fid, num, comp, venc, valor, status, sacado, ctr, rec, n_itens, tem_fp = r
        acts = []
        if status == "rascunho":
            acts.append(
                {
                    "title": f"Incluir item na fatura rascunho #{fid}",
                    "endpoint": f"{_ACT}fatura-item",
                    "method": "POST",
                    "btnLabel": "+ Item",
                    "btnStyle": "outline",
                    "submitLabel": "Incluir",
                    "okMsg": "Item incluído. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(fid), "span": "span 1"},
                        {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2"},
                        {"key": "quantidade", "label": "Quantidade*", "type": "number", "value": "1", "span": "span 1"},
                        {"key": "valor_unitario", "label": "Valor unitário (R$)*", "type": "text", "span": "span 1"},
                        {
                            "key": "codigo_servico_id",
                            "label": "Código de serviço (LC 116)",
                            "type": "select",
                            "span": "span 2",
                            "options": svc_opts,
                        },
                    ],
                }
            )
            acts.append(
                _acao(
                    f"Emitir a fatura rascunho #{fid}",
                    "fatura-emitir",
                    "Emitir",
                    fid,
                    estilo="primary",
                    confirm="Emitir dá à fatura um NÚMERO definitivo e trava os itens. Confira antes.",
                    ok="Fatura emitida. Recarregue.",
                )
            )
        if status in ("emitida", "enviada") and not rec:
            acts.append(
                _acao(
                    f"Gerar a conta a receber da fatura nº {num:05d}",
                    "fatura-gerar-conta",
                    "Gerar conta",
                    fid,
                    confirm="Cria o título em Contas a Receber com o valor da fatura. NÃO recebe — a baixa é outro ato.",
                    ok="Conta a receber criada. Recarregue.",
                )
            )
        if status != "cancelada":
            acts.append(
                {
                    "title": f"Copiar a fatura {('nº ' + format(num, '05d')) if num else '#' + str(fid)} para outra competência",
                    "endpoint": f"{_ACT}fatura-copiar",
                    "method": "POST",
                    "btnLabel": "Copiar",
                    "btnStyle": "outline",
                    "submitLabel": "Copiar",
                    "okMsg": "Cópia criada em rascunho. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(fid), "span": "span 1"},
                        {
                            "key": "competencia",
                            "label": "Competência de destino (MM/AAAA)*",
                            "type": "text",
                            "span": "span 1",
                            "ph": f"{(hoje.month % 12) + 1:02d}/{hoje.year}",
                        },
                    ],
                }
            )
            acts.append(
                _acao(
                    f"Cancelar a fatura {('nº ' + format(num, '05d')) if num else '#' + str(fid)}",
                    "fatura-cancelar",
                    "Cancelar",
                    fid,
                    confirm="Cancelar não apaga: a fatura fica no histórico marcada como cancelada. "
                    "Fatura com conta a receber PAGA não pode ser cancelada.",
                    ok="Fatura cancelada. Recarregue.",
                )
            )
        return {
            "cells": [
                t(f"{num:05d}" if num else "rascunho", 700, _ND if num else "#94A3B8"),
                t(f"{comp[5:7]}/{comp[:4]}"),
                t(sacado + (" ·fonte" if tem_fp else ""), 600, _ND),
                t(ctr or "—"),
                t(f"{n_itens}"),
                t(venc.strftime("%d/%m/%Y") if venc else "—"),
                t(brl(valor), 700),
                b(status.capitalize(), _BADGE.get(status, "mut")),
                b("conta gerada", "ok") if rec else b("sem conta", "mut"),
            ],
            "filtro": f"{comp[5:7]}/{comp[:4]}",
            "docs": [doc(f"Fatura {num:05d}" if num else f"Rascunho #{fid}", f"/api/v1/redesign/faturas/{fid}/pdf")],
            "actions": acts,
        }

    mine["faturas"] = {
        "title": "Faturas",
        "sub": "O DOCUMENTO comercial que o cliente confere item a item, antes da NFS-e. Nasce rascunho (sem número), "
        "«Emitir» dá o número definitivo e trava os itens, «Gerar conta» cria o título em Contas a Receber "
        "(não recebe). Fatura ≠ recebível: o recebível é o registro contábil do devido; a fatura é o papel. "
        "Quando o cliente tem fonte pagadora, a fatura sai no nome de quem PAGA.",
        "cta": "Nova fatura",
        "ctaTo": "fatura-nova",
        "type": "table",
        "searchHint": "Buscar por número, cliente ou contrato…",
        "grid": "0.8fr 0.7fr 1.6fr 1fr 0.5fr 0.8fr 1fr 0.8fr 0.9fr",
        "cols": ["Nº", "Comp.", "Sacado", "Contrato", "Itens", "Vencimento", "Total", "Status", "Conta"],
        "rows": [_linha(r) for r in linhas],
        "docs": [
            doc(
                f"Imprimir lote de {comp_atual[5:7]}/{comp_atual[:4]}",
                f"/api/v1/redesign/faturas/lote/pdf?competencia={comp_atual}",
            )
        ],
    }
    if not linhas:
        mine["faturas"]["empty"] = (
            "Nenhuma fatura ainda. «Nova fatura» monta uma a partir do contrato (puxa os itens) ou a mão."
        )

    # 2) Nova fatura ──────────────────────────────────────────────────────────────────────
    mine["fatura-nova"] = {
        "title": "Nova fatura",
        "sub": "Escolha o CONTRATO e deixe os itens em branco: puxa os itens do contrato (ou o valor mensal, se ele "
        "não tiver itens). Ou digite os itens a mão, um por linha. Nasce em RASCUNHO — só existe número depois de emitir.",
        "cta": "Criar rascunho",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}fatura-salvar",
            "okMsg": "Fatura criada em rascunho. Confira os itens e emita.",
            "showResult": True,
        },
        "fields": [
            {"key": "cliente_id", "label": "Cliente", "type": "select", "span": "span 2", "options": cli_opts},
            {
                "key": "contrato_id",
                "label": "Contrato (puxa os itens quando os itens ficam em branco)",
                "type": "select",
                "span": "span 2",
                "options": ctr_opts,
            },
            {
                "key": "fonte_pagadora_id",
                "label": "Fonte pagadora (quem paga, se não for o cliente)",
                "type": "select",
                "span": "span 2",
                "options": fp_opts,
            },
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "value": f"{hoje.month:02d}/{hoje.year}",
            },
            {"key": "vencimento", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {
                "key": "periodo_inicio",
                "label": "Período de prestação — início (vazio = 1º do mês)",
                "type": "date",
                "span": "span 1",
            },
            {
                "key": "periodo_fim",
                "label": "Período — fim (vazio = último dia do mês)",
                "type": "date",
                "span": "span 1",
            },
            {
                "key": "condicao_pagamento_id",
                "label": "Condição de pagamento",
                "type": "select",
                "span": "span 2",
                "options": cond_opts,
            },
            {
                "key": "descricao_padrao",
                "label": "Descrição padrão (texto que sai no corpo da fatura)",
                "type": "textarea",
                "span": "span 2",
                "ph": "Prestação de serviços de portaria conforme contrato, competência MM/AAAA.",
            },
            {
                "key": "itens",
                "label": "Itens — um por linha: descrição | quantidade | valor unitário | LC 116 (opcional)",
                "type": "textarea",
                "span": "span 2",
                "ph": _PH_ITENS,
            },
            {"key": "observacao", "label": "Observação interna", "type": "text", "span": "span 2"},
        ],
    }

    # 3) Itens por fatura ─────────────────────────────────────────────────────────────────
    itens = (
        await db.execute(
            text(
                "SELECT i.id, f.id, f.numero, f.status, i.descricao, i.quantidade, i.valor_unitario, i.valor_total, "
                "       s.item_lc116, coalesce(fp.razao_social, c.name, '—'), f.competencia "
                "  FROM fin_fatura_itens i "
                "  JOIN fin_faturas f ON f.id = i.fatura_id "
                "  LEFT JOIN fin_codigos_servico s ON s.id = i.codigo_servico_id "
                "  LEFT JOIN clients c ON c.id = f.cliente_id "
                "  LEFT JOIN crm_fontes_pagadoras fp ON fp.id = f.fonte_pagadora_id "
                " ORDER BY f.competencia DESC, coalesce(f.numero, 999999), f.id DESC, i.id LIMIT 1000"
            )
        )
    ).fetchall()
    mine["fatura-itens"] = {
        "title": "Itens das faturas",
        "sub": "A discriminação que sai no PDF. Item só entra ou sai enquanto a fatura é RASCUNHO — emitida, "
        "os itens travam (é documento, não rascunho). Use o seletor para ver uma fatura de cada vez.",
        "type": "table",
        "searchHint": "Buscar item…",
        "grid": "0.8fr 1.4fr 2.2fr 0.6fr 1fr 1fr 0.7fr",
        "cols": ["Fatura", "Sacado", "Descrição", "Qtd.", "Valor unit.", "Total", "LC 116"],
        "rows": [
            {
                "cells": [
                    t(f"{r[2]:05d}" if r[2] else f"rascunho #{r[1]}", 700, _ND if r[2] else "#94A3B8"),
                    t(r[9], 600),
                    t(r[4]),
                    t(f"{float(r[5]):.0f}" if float(r[5]) == int(float(r[5])) else f"{float(r[5]):.3f}"),
                    t(brl(r[6])),
                    t(brl(r[7]), 700),
                    t(r[8] or "—"),
                ],
                "filtro": f"{r[2]:05d}" if r[2] else f"rascunho #{r[1]}",
                "actions": (
                    [
                        {
                            "title": f"Excluir «{r[4][:40]}» da fatura rascunho #{r[1]}",
                            "endpoint": f"{_ACT}fatura-item-excluir",
                            "method": "POST",
                            "btnLabel": "Excluir",
                            "btnStyle": "outline",
                            "submitLabel": "Excluir",
                            "okMsg": "Item excluído. Recarregue.",
                            "fields": [
                                {"key": "id", "label": "id", "type": "text", "value": str(r[1]), "span": "span 1"},
                                {
                                    "key": "item_id",
                                    "label": "item",
                                    "type": "text",
                                    "value": str(r[0]),
                                    "span": "span 1",
                                },
                            ],
                        }
                    ]
                    if r[3] == "rascunho"
                    else []
                ),
            }
            for r in itens
        ],
    }
    if not itens:
        mine["fatura-itens"]["empty"] = "Sem itens — crie uma fatura primeiro."

    # 4) Copiar em lote ───────────────────────────────────────────────────────────────────
    comp_opts = [{"value": "", "label": "— escolha —"}] + [{"value": c, "label": f"{c[5:7]}/{c[:4]}"} for c in comps]
    mine["faturas-copiar-lote"] = {
        "title": "Copiar faturas em lote",
        "sub": "O «copiar em lote» do DGX: todas as faturas vivas de uma competência viram rascunho da competência "
        "seguinte, com período e vencimento andando o mesmo número de meses. Rodar duas vezes NÃO duplica — "
        "cada contrato só tem uma fatura viva por competência. As cópias nascem em rascunho: confira e emita.",
        "cta": "Copiar lote",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}faturas-copiar-lote",
            "okMsg": "Lote copiado — as cópias estão em rascunho.",
            "gated": True,
            "showResult": True,
            "confirm": "Vai criar N faturas em rascunho de uma vez. Nenhuma é emitida e nenhuma conta a receber "
            "é gerada por este botão.",
        },
        "fields": [
            {
                "key": "origem",
                "label": "Competência de origem*",
                "type": "select" if comp_opts[1:] else "text",
                "span": "span 1",
                "options": comp_opts,
                "ph": "MM/AAAA",
            },
            {
                "key": "destino",
                "label": "Competência de destino*",
                "type": "text",
                "span": "span 1",
                "ph": f"{(hoje.month % 12) + 1:02d}/{hoje.year}",
            },
            {
                "key": "contratos",
                "label": "Contratos (vazio = todos os da competência de origem)",
                "type": "select",
                "span": "span 2",
                "options": ctr_opts,
            },
        ],
    }
    out.update(mine)
    return mine


# ── AÇÕES ───────────────────────────────────────────────────────────────────────────────────
def _id(payload: dict) -> int:
    try:
        return int(str(payload.get("id") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Fatura não informada.") from None


def _por(u) -> str:
    return getattr(u, "email", None) or str(u.id)


@router.post("/action/fatura-salvar", dependencies=_GATE)
async def rd_fatura_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Cria a fatura em RASCUNHO. Sem itens digitados + contrato escolhido = itens do contrato."""
    await svc.ensure(db)
    itens = await _resolver_lc116(db, itens_texto(payload.get("itens")))
    fid = await svc.criar(
        db,
        {
            "cliente_id": payload.get("cliente_id"),
            "contrato_id": payload.get("contrato_id"),
            "fonte_pagadora_id": payload.get("fonte_pagadora_id"),
            "competencia": _comp(payload.get("competencia")),
            "periodo_inicio": _data(payload["periodo_inicio"], "Período — início")
            if str(payload.get("periodo_inicio") or "").strip()
            else None,
            "periodo_fim": _data(payload["periodo_fim"], "Período — fim")
            if str(payload.get("periodo_fim") or "").strip()
            else None,
            "vencimento": _data(payload.get("vencimento"), "Vencimento"),
            "condicao_pagamento_id": payload.get("condicao_pagamento_id"),
            "descricao_padrao": payload.get("descricao_padrao"),
            "observacao": payload.get("observacao"),
            "itens": itens,
        },
        _por(current_user),
    )
    d = await svc.dados_documento(db, fid)
    return {
        "ok": True,
        "id": fid,
        "message": f"Fatura em rascunho #{fid} — {len(d['itens'])} item(ns), {brl(d['valor'])}. "
        "Confira em «Faturas» e clique Emitir para dar o número.",
        "doc": {
            "label": f"Rascunho #{fid}",
            "url": f"/api/v1/redesign/faturas/{fid}/pdf",
            "fmt": "pdf",
            "mode": "blob",
        },
    }


@router.post("/action/fatura-item", dependencies=_GATE)
async def rd_fatura_item(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await svc.ensure(db)
    try:
        qtd = Decimal(str(payload.get("quantidade") or "1").replace(",", "."))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Quantidade inválida.") from None
    total = await svc.item_incluir(
        db,
        _id(payload),
        {
            "descricao": payload.get("descricao"),
            "quantidade": qtd,
            "valor_unitario": _dec(payload.get("valor_unitario"), "Valor unitário"),
            "codigo_servico_id": payload.get("codigo_servico_id"),
        },
    )
    return {"ok": True, "message": f"Item incluído — fatura agora em {brl(total)}."}


@router.post("/action/fatura-item-excluir", dependencies=_GATE)
async def rd_fatura_item_excluir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await svc.ensure(db)
    try:
        item_id = int(str(payload.get("item_id") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Item não informado.") from None
    total = await svc.item_excluir(db, _id(payload), item_id)
    return {"ok": True, "message": f"Item excluído — fatura agora em {brl(total)}."}


@router.post("/action/fatura-emitir", dependencies=_GATE)
async def rd_fatura_emitir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Dá o número definitivo. Não é dinheiro que sai — é documento que nasce; gate de cargo basta."""
    numero = await svc.emitir(db, _id(payload), _por(current_user))
    return {
        "ok": True,
        "numero": numero,
        "message": f"Fatura nº {numero:05d} emitida. Itens travados.",
        "doc": {
            "label": f"Fatura {numero:05d}",
            "url": f"/api/v1/redesign/faturas/{_id(payload)}/pdf",
            "fmt": "pdf",
            "mode": "blob",
        },
    }


@router.post("/action/fatura-gerar-conta", dependencies=_GATE)
async def rd_fatura_gerar_conta(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """O «GerarConta» do DGX. Registra o devido pelo caminho existente; NÃO recebe (baixa é outro ato)."""
    return await svc.gerar_conta(db, _id(payload), current_user.id)


@router.post("/action/fatura-copiar", dependencies=_GATE)
async def rd_fatura_copiar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await svc.ensure(db)
    destino = _comp(payload.get("competencia"))
    novo = await svc.copiar(db, _id(payload), destino, _por(current_user))
    await db.commit()
    if novo is None:
        return {
            "ok": True,
            "message": f"Este contrato já tem fatura viva em {destino[5:7]}/{destino[:4]} — nada a copiar.",
        }
    return {"ok": True, "id": novo, "message": f"Cópia criada em rascunho #{novo} para {destino[5:7]}/{destino[:4]}."}


@router.post("/action/faturas-copiar-lote", dependencies=_GATE)
async def rd_faturas_copiar_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    ctr = str(payload.get("contratos") or "").strip()
    return await svc.copiar_lote(
        db,
        _comp(payload.get("origem")),
        _comp(payload.get("destino")),
        [ctr] if ctr else None,
        _por(current_user),
    )


@router.post("/action/fatura-cancelar", dependencies=_GATE)
async def rd_fatura_cancelar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await svc.cancelar(db, _id(payload), _por(current_user))


# ── PDF ─────────────────────────────────────────────────────────────────────────────────────
# `/lote/pdf` ANTES de `/{fid}/pdf`: rota literal tem de casar primeiro.
@router.get("/faturas/lote/pdf", summary="Faturas da competência em PDF (uma por página)")
async def rd_faturas_lote_pdf(
    competencia: str = Query(..., description="MM/AAAA ou AAAA-MM"),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    comp = _comp(competencia)
    ids = [
        int(x)
        for x in (
            await db.execute(
                text(
                    "SELECT id FROM fin_faturas WHERE competencia = :m AND status <> 'cancelada' "
                    " ORDER BY coalesce(numero, 999999), id"
                ),
                {"m": comp},
            )
        )
        .scalars()
        .all()
    ]
    if not ids:
        raise HTTPException(status_code=404, detail=f"Nenhuma fatura em {comp[5:7]}/{comp[:4]}.")
    pdf = await svc.pdf_lote(db, ids)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="faturas-{comp}.pdf"'},
    )


@router.get("/faturas/{fid}/pdf", summary="Fatura em PDF (padrão-ouro)")
async def rd_fatura_pdf(fid: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import Response

    pdf = await svc.pdf_lote(db, [fid])
    d = await svc.dados_documento(db, fid)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="fatura-{d["numero"]}.pdf"'},
    )
