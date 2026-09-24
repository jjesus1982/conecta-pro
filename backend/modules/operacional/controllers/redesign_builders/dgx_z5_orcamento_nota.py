"""DGX Z5 — Do orçamento à nota: o emissor CONSOME, nunca cria (24/09/2026).

Duas portas de entrada para a nota, e nenhuma outra, porque foi o que o dono mandou:

    «os orçamentos são criados pelo Claude Cowork via conector Conecta PRO MCP, até termos o
     sistema todo pronto. Não vai criar orçamento dentro do emissor de nota: ou subo o arquivo,
     ou crio dentro do CRM etc. Obedecer o fluxo natural.»

  (A) `nfe-do-orcamento` — lista as propostas que já existem (CRM ou Cowork/MCP) e gera o
      rascunho de nota a partir de uma delas.
  (B) `nfe-do-arquivo`   — sobe o PDF/planilha/foto do orçamento, lê os itens, mostra cada um com
      a confiança da leitura e a linha de origem, e gera o mesmo rascunho.

Não existe «novo orçamento» aqui. O oráculo `test_oraculo_z5_orcamento_nota.py` varre este
arquivo e o serviço atrás de qualquer escrita em `proposals`/`proposal_items` — é a trava da
frase acima.

Duas telas de apoio fecham o ciclo: `nfe-rascunhos` (o rastro: de que proposta ou de que arquivo,
com hash, cada rascunho veio) e `nfe-rascunho-itens` (onde uma PESSOA escolhe o produto do
cadastro fiscal para o item que não casou — sem isso o item não vira linha de nota).

Nota de encaixe: este módulo NÃO tem o prefixo `_` de propósito. O `fiscal.py` não expõe `router`,
e criar um lá só para esta frente colidiria com Z1–Z4, que estão mexendo no mesmo arquivo nesta
onda. Sem `build`, sem `SLUG` e sem `EXTRA_MENU`, o discovery do `redesign_data_controller` só
monta o `router` daqui — as abas e a chamada de `telas()` ficam no `fiscal.py`, em 6 linhas.

NENHUMA transmissão à SEFAZ acontece aqui: o fim desta frente é um RASCUNHO. Emitir é da Z2/Z3,
e só em homologação.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto) — igual F11/V5.
router = APIRouter()

from modules.fiscal.services import orcamento_para_nota as svc  # noqa: E402
from modules.operacional.controllers.redesign_data_controller import b, brl, t  # noqa: E402

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:fiscal"))]
_ICO = "M9 11H3v10h6V11zM15 3H9v18h6V3zM21 7h-6v14h6V7z"

#: As abas desta frente — o `fiscal.py` as acrescenta no FIM do EXTRA_MENU dele.
ABAS = [
    {"id": "nfe-do-orcamento", "label": "NF-e a partir de um orçamento", "icon": _ICO, "grupo": "Do orçamento à nota"},
    {"id": "nfe-do-arquivo", "label": "NF-e a partir de um arquivo", "icon": _ICO, "grupo": "Do orçamento à nota"},
    {"id": "nfe-rascunhos", "label": "Rascunhos de nota (origem)", "icon": _ICO, "grupo": "Do orçamento à nota"},
    {"id": "nfe-rascunho-itens", "label": "Itens sem produto (casar)", "icon": _ICO, "grupo": "Do orçamento à nota"},
]

_SIT = {"rascunho": ("Rascunho", "warn"), "convertido": ("Virou nota", "ok"), "cancelado": ("Cancelado", "mut")}
_CASAMENTO = {
    "codigo": ("Casou pelo código", "ok"),
    "descricao": ("Casou pela descrição", "ok"),
    "manual": ("Escolhido por pessoa", "ok"),
    "nao_casado": ("Sem produto", "bad"),
}


def _br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _origem(origem_tipo: str, numero: str | None, arquivo: str | None, hash_: str | None) -> str:
    """O rastro em uma linha. Nota fiscal sem origem rastreável é problema na auditoria."""
    if origem_tipo == "proposta":
        return f"Proposta {numero or '(apagada)'}"
    return f"Arquivo {(arquivo or '—')[:38]} · sha {(hash_ or '')[:8]}"


async def _opcoes_produto(db: AsyncSession) -> list[dict]:
    if not await svc.cadastro_de_produto_existe(db):
        return []
    linhas = (
        await db.execute(
            text(
                "SELECT id, coalesce(codigo,'—'), descricao, coalesce(ncm,'—') FROM fin_produtos "
                " WHERE coalesce(ativo,true) ORDER BY descricao LIMIT 500"
            )
        )
    ).fetchall()
    return [{"value": str(r[0]), "label": f"{r[1]} · {r[2][:46]} · NCM {r[3]}"} for r in linhas]


# ── telas ───────────────────────────────────────────────────────────────────────────────────
async def telas(db: AsyncSession, out: dict | None = None) -> dict:
    await svc.ensure_schema(db)
    out = out if out is not None else {}

    # (A) orçamentos que já existem ─────────────────────────────────────────────────────────
    orcs = await svc.listar_orcamentos(db)
    fora = (
        await db.execute(
            text("SELECT status, count(*) FROM proposals WHERE NOT (status = ANY(:st)) GROUP BY 1 ORDER BY 2 DESC"),
            {"st": list(svc.STATUS_FATURAVEIS)},
        )
    ).fetchall()
    resto = " · ".join(f"{n} {s}" for s, n in fora) or "nenhuma"
    out["nfe-do-orcamento"] = {
        "title": "NF-e a partir de um orçamento",
        "sub": (
            f"{len(orcs)} proposta(s) aceita(s), prontas para faturar. Fora do faturável: {resto} — proposta em "
            "negociação ou recusada não vira documento fiscal. **O orçamento não nasce aqui**: ele vem do CRM ou "
            "do Claude Cowork pelo conector MCP. Esta tela só CONSOME o que já existe."
        ),
        "cta": "Ver rascunhos",
        "ctaTo": "nfe-rascunhos",
        "type": "table",
        "searchHint": "Buscar proposta ou cliente…",
        "grid": "1.3fr 2.2fr 0.9fr 0.6fr 1.1fr 1.2fr",
        "cols": ["Proposta", "Cliente", "Emissão", "Itens", "Soma dos itens", "Rascunho"],
        "rows": [
            {
                "cells": [
                    t(o["numero"], 600, _ND),
                    t((o["cliente"] or "—")[:54]),
                    t(_br(o["data"])),
                    b(str(o["qtd_itens"]), "ok" if o["qtd_itens"] else "bad"),
                    t(brl(o["total_itens"]), 600),
                    b("Já tem rascunho", "ok") if o["rascunho_id"] else b("—", "mut"),
                ],
                "actions": [
                    {
                        "title": f"Gerar rascunho de nota — {o['numero']}",
                        "endpoint": f"{_ACT}z5-rascunho-do-orcamento",
                        "method": "POST",
                        "btnLabel": "Abrir rascunho" if o["rascunho_id"] else "Gerar rascunho de nota",
                        "btnStyle": "outline" if o["rascunho_id"] else "solid",
                        "submitLabel": "Confirmar",
                        "okMsg": "Rascunho pronto — veja em «Rascunhos de nota».",
                        "fields": [
                            {
                                "key": "proposal_id",
                                "label": "proposta",
                                "type": "text",
                                "value": o["proposal_id"],
                                "span": "span 1",
                            }
                        ],
                    }
                ],
            }
            for o in orcs
        ]
        or [
            {
                "cells": [
                    t("Nenhuma proposta aceita", 500, "#94A3B8"),
                    t(f"Fora do faturável: {resto}"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                ]
            }
        ],
    }

    # (B) o arquivo do orçamento ────────────────────────────────────────────────────────────
    out["nfe-do-arquivo"] = {
        "title": "NF-e a partir de um arquivo",
        "sub": (
            "Suba o orçamento em PDF, DOCX, TXT ou foto (JPG/PNG) — planilha, exporte para PDF antes; .xlsx o "
            "leitor não abre. A leitura devolve cada item com a **confiança** e a **linha de origem**, e diz "
            "quais casaram com o cadastro fiscal de produto. Nada é transmitido: o resultado é um rascunho que "
            "uma pessoa confere. Subir o mesmo arquivo de novo abre o rascunho que já existe (o sha256 do "
            "conteúdo é a chave)."
        ),
        "cta": "Ler e gerar rascunho",
        "ctaTo": "nfe-rascunhos",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}z5-rascunho-do-arquivo",
            "multipart": True,
            "okMsg": "Orçamento lido.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "arquivo",
                "label": "Arquivo do orçamento* (PDF, DOCX, TXT, JPG, PNG)",
                "type": "file",
                "span": "span 2",
            },
            {"key": "cliente_nome", "label": "Cliente (se o arquivo não disser)", "type": "text", "span": "span 1"},
            {"key": "cliente_documento", "label": "CNPJ/CPF do cliente", "type": "text", "span": "span 1"},
        ],
    }

    # rastro — de onde veio cada rascunho ───────────────────────────────────────────────────
    rasc = (
        await db.execute(
            text(
                "SELECT r.id::text, r.origem_tipo, p.number, r.arquivo_nome, r.arquivo_hash, r.cliente_nome, "
                "       r.valor_total, r.status, r.criado_em, r.nfe_id::text, "
                "       (SELECT count(*) FROM fiscal_nota_rascunho_item i WHERE i.rascunho_id = r.id), "
                "       (SELECT count(*) FROM fiscal_nota_rascunho_item i WHERE i.rascunho_id = r.id "
                "         AND i.produto_id IS NULL) "
                "  FROM fiscal_nota_rascunho r LEFT JOIN proposals p ON p.id = r.proposal_id "
                " ORDER BY r.criado_em DESC LIMIT 300"
            )
        )
    ).fetchall()
    out["nfe-rascunhos"] = {
        "title": "Rascunhos de nota (origem)",
        "sub": (
            f"{len(rasc)} rascunho(s). Cada um guarda **de onde veio** — a proposta, ou o arquivo com o hash do "
            "conteúdo. É esse rastro que a auditoria cobra: nota fiscal sem origem rastreável não se defende. "
            "Emitir é da tela de NF-e; aqui o documento ainda não existe para o fisco."
        ),
        "cta": "Itens sem produto",
        "ctaTo": "nfe-rascunho-itens",
        "type": "table",
        "searchHint": "Buscar origem ou cliente…",
        "grid": "2.1fr 1.8fr 0.6fr 0.8fr 1.1fr 1fr",
        "cols": ["Origem", "Cliente", "Itens", "Sem produto", "Total", "Situação"],
        "rows": [
            {
                "cells": [
                    t(_origem(r[1], r[2], r[3], r[4]), 600, _ND),
                    t((r[5] or "—")[:44]),
                    b(str(r[10]), "ok" if r[10] else "mut"),
                    b(str(r[11]), "bad" if r[11] else "ok"),
                    t(brl(r[6]), 600),
                    b(*_SIT.get(r[7], (r[7], "info"))),
                ],
                "actions": (
                    [
                        {
                            "title": f"Cancelar o rascunho de {_origem(r[1], r[2], r[3], r[4])}",
                            "endpoint": f"{_ACT}z5-rascunho-cancelar",
                            "method": "POST",
                            "btnLabel": "Cancelar",
                            "btnStyle": "outline",
                            "submitLabel": "Confirmar cancelamento",
                            "okMsg": "Rascunho cancelado. Recarregue.",
                            "fields": [
                                {
                                    "key": "rascunho_id",
                                    "label": "rascunho",
                                    "type": "text",
                                    "value": r[0],
                                    "span": "span 1",
                                },
                                {
                                    "key": "motivo",
                                    "label": "Por quê? (fica no rastro)",
                                    "type": "text",
                                    "span": "span 2",
                                },
                            ],
                        }
                    ]
                    if r[7] == "rascunho"
                    else []
                ),
            }
            for r in rasc
        ]
        or [{"cells": [t("Nenhum rascunho ainda", 500, "#94A3B8"), t("—"), t("—"), t("—"), t("—"), t("—")]}],
    }

    # itens — onde a PESSOA escolhe o produto do item que não casou ─────────────────────────
    itens = (
        await db.execute(
            text(
                "SELECT i.id::text, r.origem_tipo, p.number, r.arquivo_nome, r.arquivo_hash, i.numero_item, "
                "       i.descricao, i.unidade, i.quantidade, i.valor_unitario, i.valor_total, i.casamento, "
                "       i.produto_codigo, i.ncm, i.ncm_sugerido, i.confianca, i.trecho_origem "
                "  FROM fiscal_nota_rascunho_item i JOIN fiscal_nota_rascunho r ON r.id = i.rascunho_id "
                "  LEFT JOIN proposals p ON p.id = r.proposal_id "
                " WHERE r.status <> 'cancelado' "
                " ORDER BY (i.produto_id IS NULL) DESC, r.criado_em DESC, i.numero_item LIMIT 600"
            )
        )
    ).fetchall()
    opts = await _opcoes_produto(db)
    sem_cadastro = not opts
    pendentes = sum(1 for i in itens if i[11] == "nao_casado")
    out["nfe-rascunho-itens"] = {
        "title": "Itens dos rascunhos — casar produto",
        "sub": (
            f"{len(itens)} item(ns), **{pendentes} sem produto** do cadastro fiscal. Item sem produto NÃO vira linha "
            "de nota: o NCM sai do cadastro, nunca do orçamento — foi NCM inexistente que a SEFAZ recusou em "
            "11/04/2026. A confiança e o trecho são da leitura do arquivo; item vindo de proposta não tem leitura."
            + (
                " ⚠️ O cadastro fiscal de produtos (`fin_produtos`, frente Z1) ainda não existe neste ambiente — "
                "sem ele não há o que escolher."
                if sem_cadastro
                else ""
            )
        ),
        "cta": "Voltar aos rascunhos",
        "ctaTo": "nfe-rascunhos",
        "type": "table",
        "searchHint": "Buscar item, produto ou origem…",
        "grid": "1.6fr 2fr 0.5fr 0.9fr 0.9fr 0.7fr 1.4fr 2fr",
        "cols": ["Origem", "Item", "Qtd", "Unitário", "Total", "Leitura", "Produto casado", "Trecho de origem"],
        "rows": [
            {
                "cells": [
                    t(_origem(i[1], i[2], i[3], i[4]), 500, _ND),
                    t(f"{i[5]}. {i[6][:46]}", 600),
                    t(f"{float(i[8]):.4f}".rstrip("0").rstrip(".") + f" {i[7]}"),
                    t(brl(i[9])),
                    t(brl(i[10]), 600),
                    b(f"{float(i[15]) * 100:.0f}%", "ok" if float(i[15]) >= 0.8 else "warn")
                    if i[15] is not None
                    else b("do CRM", "info"),
                    b(*_CASAMENTO.get(i[11], (i[11], "info")))
                    if i[11] == "nao_casado"
                    else t(f"{i[12] or '—'} · NCM {i[13] or '—'}", 600),
                    t((i[16] or ("NCM sugerido: " + i[14] if i[14] else "—"))[:64], 400, "#64748B"),
                ],
                "actions": (
                    [
                        {
                            "title": f"Escolher o produto do item {i[5]} — «{i[6][:40]}»",
                            "endpoint": f"{_ACT}z5-rascunho-casar-item",
                            "method": "POST",
                            "btnLabel": "Casar produto",
                            "btnStyle": "solid",
                            "submitLabel": "Confirmar",
                            "okMsg": "Produto vinculado. Recarregue.",
                            "fields": [
                                {
                                    "key": "item_id",
                                    "label": "item",
                                    "type": "text",
                                    "value": i[0],
                                    "span": "span 1",
                                },
                                {
                                    "key": "produto_id",
                                    "label": "Produto do cadastro fiscal*"
                                    + (f" (sugestão de NCM: {i[14]})" if i[14] else ""),
                                    "type": "select",
                                    "span": "span 2",
                                    "options": opts,
                                },
                            ],
                        }
                    ]
                    if i[11] == "nao_casado" and not sem_cadastro
                    else []
                ),
            }
            for i in itens
        ]
        or [
            {
                "cells": [
                    t("Nenhum item ainda", 500, "#94A3B8"),
                    t("Gere um rascunho de um orçamento ou de um arquivo"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                ]
            }
        ],
    }
    return out


# ── ações ───────────────────────────────────────────────────────────────────────────────────
@router.post("/action/z5-rascunho-do-orcamento", dependencies=_GATE)
async def rd_z5_rascunho_do_orcamento(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera (ou reabre) o rascunho de nota de uma proposta que JÁ EXISTE. Não cria proposta."""
    pid = (payload.get("proposal_id") or "").strip()
    if not pid:
        raise HTTPException(status_code=422, detail="Selecione a proposta.")
    try:
        r = await svc.preparar_rascunho(db, "proposta", proposal_id=pid, usuario=str(current_user.email))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "ok": True,
        "message": r["mensagem"],
        "rascunho_id": r["id"],
        "ja_existia": r["ja_existia"],
        "valor_total": float(r["valor_total"]),
        "qtd_itens": r["qtd_itens"],
        "itens_sem_produto": r.get("itens_sem_produto", 0),
    }


@router.post("/action/z5-rascunho-do-arquivo", dependencies=_GATE)
async def rd_z5_rascunho_do_arquivo(
    current_user: CurrentActiveUser,
    arquivo: UploadFile = File(...),
    cliente_nome: str = Form(""),
    cliente_documento: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lê o arquivo do orçamento e gera o rascunho. A prévia dos itens volta no resultado."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(dados) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 15MB).")
    nome = arquivo.filename or "orcamento"
    # o mesmo arquivo de novo NÃO paga outra leitura por LLM: o sha256 do conteúdo responde antes
    ja = await svc.rascunho_existente(db, arquivo_hash=hashlib.sha256(dados).hexdigest())
    if ja:
        return {
            "ok": True,
            "message": "Este arquivo já foi lido e virou rascunho. Abri o que existe, em «Rascunhos de nota».",
            "rascunho_id": ja,
            "ja_existia": True,
            "sha256_do_arquivo": hashlib.sha256(dados).hexdigest(),
        }
    try:
        lido = await svc.itens_do_arquivo(db, nome, dados)
        itens = await svc.casar_produtos(db, lido["itens"])
        r = await svc.preparar_rascunho(
            db,
            "arquivo",
            arquivo_nome=nome,
            arquivo_bytes=dados,
            itens=itens,
            cliente_nome=cliente_nome or lido.get("documento") or nome,
            cliente_documento=cliente_documento,
            usuario=str(current_user.email),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # prévia: o painel de resultado do front renderiza `nome` + `chave` (subtítulo) + `valor`
    previa = [
        {
            "nome": f"{i['descricao'][:48]} · {i['quantidade']} {i['unidade']}",
            "chave": (
                f"leitura {float(i.get('confianca') or 0) * 100:.0f}% · "
                + (
                    f"casado: {i.get('produto_codigo') or i.get('produto_descricao') or '—'}"
                    if i.get("produto_id")
                    else f"SEM PRODUTO — {i.get('motivo') or 'escolha na tela de itens'}"
                )
                + f" · origem: «{(i.get('trecho_origem') or '—')[:60]}»"
            ),
            "valor": float(i["valor_total"]),
        }
        for i in itens
    ]
    return {
        "ok": True,
        "message": r["mensagem"] + " Abra «Rascunhos de nota» para seguir.",
        "rascunho_id": r["id"],
        "ja_existia": r["ja_existia"],
        "documento_lido": lido.get("documento") or "—",
        "sha256_do_arquivo": lido["hash"],
        "valor_total": float(r["valor_total"]),
        "itens_sem_produto": r.get("itens_sem_produto", sum(1 for i in itens if not i.get("produto_id"))),
        "itens": previa,
    }


@router.post("/action/z5-rascunho-casar-item", dependencies=_GATE)
async def rd_z5_casar_item(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A PESSOA escolhe o produto do cadastro fiscal para um item pendente. Nunca automático."""
    iid = (payload.get("item_id") or "").strip()
    pid = (payload.get("produto_id") or "").strip()
    if not iid or not pid:
        raise HTTPException(status_code=422, detail="Informe o item e o produto.")
    try:
        r = await svc.casar_item_manual(db, iid, int(pid), usuario=str(current_user.email))
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"ok": True, "message": f"Item vinculado a «{r['produto']}» (NCM {r['ncm'] or '—'})."}


@router.post("/action/z5-rascunho-cancelar", dependencies=_GATE)
async def rd_z5_cancelar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancela o rascunho. Não apaga: o rastro fica, e a origem volta a aceitar um rascunho novo."""
    rid = (payload.get("rascunho_id") or "").strip()
    if not rid:
        raise HTTPException(status_code=422, detail="Informe o rascunho.")
    n = (
        await db.execute(
            text(
                "UPDATE fiscal_nota_rascunho SET status = 'cancelado', atualizado_em = now(), "
                "  observacao = coalesce(observacao || ' | ', '') || :m "
                " WHERE id = CAST(:r AS uuid) AND status = 'rascunho' RETURNING 1"
            ),
            {
                "r": rid,
                "m": f"cancelado por {current_user.email}: {(payload.get('motivo') or 'sem motivo').strip()[:120]}",
            },
        )
    ).first()
    if not n:
        raise HTTPException(status_code=422, detail="Rascunho não encontrado ou já não está em rascunho.")
    await db.commit()
    return {"ok": True, "message": "Rascunho cancelado — o rastro de origem continua guardado."}


@router.get("/z5-rascunho/{rascunho_id}/itens-para-nota", dependencies=_GATE)
async def rd_z5_itens_para_nota(
    rascunho_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O que a Z3 chama para abrir o rascunho: os itens prontos, ou a recusa com quem falta.

    Read-only. Não emite, não transmite, não escreve — é a porta que a tela de NF-e consome.
    """
    try:
        itens = await svc.itens_para_nota(db, rascunho_id)
    except svc.ProdutoNaoCasadoError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    cab = (
        await db.execute(
            text(
                "SELECT r.origem_tipo, p.number, r.arquivo_nome, r.arquivo_hash, r.cliente_nome, "
                "       r.cliente_documento, r.valor_total "
                "  FROM fiscal_nota_rascunho r LEFT JOIN proposals p ON p.id = r.proposal_id "
                " WHERE r.id = CAST(:r AS uuid)"
            ),
            {"r": rascunho_id},
        )
    ).first()
    return {
        "ok": True,
        "origem": _origem(cab[0], cab[1], cab[2], cab[3]) if cab else "—",
        "origem_tipo": cab[0] if cab else None,
        "proposta": cab[1] if cab else None,
        "arquivo_sha256": cab[3] if cab else None,
        "cliente_nome": cab[4] if cab else None,
        "cliente_documento": cab[5] if cab else None,
        "valor_total": float(cab[6]) if cab else 0.0,
        "itens": [{k: (float(v) if hasattr(v, "quantize") else v) for k, v in i.items()} for i in itens],
    }
