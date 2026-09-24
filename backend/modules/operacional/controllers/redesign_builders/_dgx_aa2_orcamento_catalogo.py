"""DGX AA2 — o item do orçamento vem do CATÁLOGO, não de texto livre (24/09/2026).

    «na hora de fazer o orçamento, fazemos pelo crm, já estará lá com toda a descrição,
     só seleciona o item e as quantidades»  — Jordan, 24/09/2026

A tela `orcamento-catalogo` lista o catálogo (`products`, 867 itens do Bling) e dá a cada linha
o botão **«Usar no orçamento»**: código, descrição, unidade e NCM já vêm do produto; a pessoa
escolhe a proposta, o CNPJ emissor, digita a **quantidade** e o **preço do dia**. Mais nada.

O preço chega VAZIO — sem sugestão, sem último preço, sem margem — porque é isso que o dono
pediu em 24/09. A regra mora em `modules/crm/services/item_do_catalogo.py` e o oráculo
`scripts/orq/test_oraculo_aa2_orcamento_catalogo.py` a vigia por AST e por comportamento.

Busca: o campo «Buscar…» do topo filtra por QUALQUER célula da linha — então serve tanto para
código quanto para descrição, que é como o dono procura (ele não decora código). ⚠️ A busca é
literal: o catálogo tem «câmera» em 30 linhas e «camera» em 28, e nenhum dos dois termos acha
as 58. Isso é defeito do CATÁLOGO (dois jeitos de escrever a mesma palavra, herdados do Bling),
e a correção é da frente AA1 — está no §7 do relatório.

Prefixo `_` = o discovery pula. `crm.py` importa `router` e chama `telas(db, out)` no fim do
`build()`; a aba entra no grupo «Propostas & orçamento» via `MENU`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t

logger = logging.getLogger(__name__)
router = APIRouter()

_ICO = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 11h6"

MENU = [
    {
        "id": "orcamento-catalogo",
        "label": "Catálogo → item do orçamento",
        "icon": _ICO,
        "grupo": "Propostas & orçamento",
    }
]

#: O catálogo como ele é. Nenhuma coluna de preço entra nesta consulta — de propósito, e o
#: oráculo confere por AST que nenhuma delas aparece neste arquivo.
SQL_CATALOGO = """
SELECT p.id::text, coalesce(p.code,'—'), p.name, coalesce(p.unit_of_measure,'un'),
       coalesce(p.ncm,''), coalesce(p.brand, p.manufacturer, ''),
       (SELECT count(*) FROM proposal_items i WHERE i.produto_id = p.id)
  FROM products p
 WHERE coalesce(p.ativo,true)
 ORDER BY p.name
 LIMIT 1000
"""
# ponytail: LIMIT 1000 cobre as 867 de hoje e a tela renderiza todas (a busca é client-side —
# cortar em 300 esconderia 567 do campo de busca, que é justamente o que o dono usa). Se o
# catálogo passar de ~2 mil itens, a busca precisa virar server-side.

SQL_PROPOSTAS = """
SELECT id::text, coalesce(number,'—') || ' · ' || coalesce(client_name,'—')
  FROM proposals
 WHERE coalesce(is_active,true) AND status::text IN ('draft','approved')
 ORDER BY created_at DESC LIMIT 200
"""

SQL_EMPRESAS = "SELECT id::text, razao_social FROM empresas ORDER BY razao_social"


async def _opcoes(db, sql: str, vazio: str) -> list[dict]:
    """Opções do select. O modal de ação por-linha NÃO desenha placeholder próprio: sem uma
    primeira opção vazia, o select MOSTRA a primeira empresa e MANDA string vazia — escolha
    que ninguém fez indo para dentro de um orçamento."""
    from sqlalchemy import text as _t

    try:
        linhas = (await db.execute(_t(sql))).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        return [{"value": "", "label": vazio}]
    return [{"value": "", "label": vazio}] + [{"value": str(a), "label": str(c)} for a, c in linhas]


async def garantir_elo(db) -> None:
    """DDL do elo, tolerante a falha. Chamada por `crm.py` ANTES de montar `proposta-itens` —
    aquela tela passou a ler `i.produto_id`, e uma coluna que ainda não existe faria a tela
    inteira sumir (o `tbl` está dentro de um try/except que engole)."""
    from modules.crm.services.item_do_catalogo import garantir_coluna

    try:
        await garantir_coluna(db)
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning("AA2: não consegui garantir proposal_items.produto_id")


async def telas(db, out: dict) -> None:
    await garantir_elo(db)

    _, _safe, tbl = _helpers(db)
    props = await _opcoes(db, SQL_PROPOSTAS, "Selecione a proposta…")
    emps = await _opcoes(db, SQL_EMPRESAS, "Selecione o CNPJ emissor…")

    def _acao(r):
        return [
            {
                "title": f"Usar no orçamento — {r[1]} · {r[2]}",
                "endpoint": "/api/v1/redesign/action/orcamento-item-catalogo",
                "method": "POST",
                "btnLabel": "Usar no orçamento",
                "btnStyle": "primary",
                "submitLabel": "Adicionar ao orçamento",
                "okMsg": "Item adicionado ao orçamento. Recarregue a tela de itens.",
                # `fixed` = vai no corpo sem virar caixa na tela. Campo `hidden` aqui
                # apareceria como uma caixa de texto com um UUID dentro, editável.
                "fixed": {"produto_id": r[0]},
                "fields": [
                    {
                        "key": "proposal_id",
                        "label": "Proposta (rascunho ou aprovada)*",
                        "type": "select",
                        "span": "span 2",
                        "options": props,
                    },
                    {
                        "key": "empresa_id",
                        "label": "CNPJ que emite este item*",
                        "type": "select",
                        "span": "span 2",
                        "options": emps,
                    },
                    {
                        "key": "quantidade",
                        "label": f"Quantidade* (em {r[3]})",
                        "type": "number",
                        "span": "span 1",
                        "value": "1",
                    },
                    # ⛔ SEM `value`: o preço do dia é digitado por quem orça. O catálogo não
                    # sugere preço — decisão do dono em 24/09/2026. O oráculo checa isto no AST.
                    {
                        "key": "preco_digitado",
                        "label": "Preço do dia (R$)*",
                        "type": "number",
                        "span": "span 1",
                        "ph": "digite o preço de hoje",
                    },
                    {
                        "key": "desconto_percent",
                        "label": "Desconto (%)",
                        "type": "number",
                        "span": "span 1",
                        "ph": "0",
                    },
                    {
                        "key": "observacao",
                        "label": "Observação (só se o catálogo não descrever)",
                        "type": "text",
                        "span": "span 2",
                    },
                ],
            }
        ]

    try:
        from sqlalchemy import text as _t

        total = (await db.execute(_t("SELECT count(*) FROM products WHERE coalesce(ativo,true)"))).scalar() or 0
        com_ncm = (
            await db.execute(_t("SELECT count(*) FROM products WHERE coalesce(ativo,true) AND coalesce(ncm,'')<>''"))
        ).scalar() or 0
        out["orcamento-catalogo"] = await tbl(
            "Catálogo → item do orçamento",
            f"{total} produtos ({com_ncm} com NCM). Escolha o item, digite a quantidade e o PREÇO DO DIA — "
            "o catálogo não sugere preço. Itens de serviço/mão de obra ainda vivem em outro cadastro "
            "(aba «Produtos (catálogo)») e não entram aqui: a unificação é a frente AA1.",
            "",
            ["Código", "Descrição (é por aqui que se busca)", "Unidade", "NCM", "Marca", "Já usado"],
            "0.7fr 3.2fr 0.6fr 0.9fr 1fr 0.7fr",
            SQL_CATALOGO,
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                t(r[2]),
                t(r[3]),
                t(r[4] or "—") if r[4] else b("sem NCM", "mut"),
                t(r[5] or "—"),
                b(f"{r[6]}×", "info") if r[6] else t("—"),
            ],
            hint="Buscar por código ou descrição…",
            actionsfn=_acao,
        )
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception("AA2: tela do catálogo não montou")


@router.post("/action/orcamento-item-catalogo")
async def rd_action_orcamento_item_catalogo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    """Adiciona ao orçamento um item que É um produto do catálogo.

    Casca fina: toda a regra (preço vazio = recusa, identidade vinda do produto, elo gravado)
    mora em `modules/crm/services/item_do_catalogo.py`, que é o que o oráculo chama.
    """
    from modules.crm.services.item_do_catalogo import adicionar_item_do_catalogo

    try:
        item = await adicionar_item_do_catalogo(
            db,
            proposal_id=(payload.get("proposal_id") or "").strip(),
            produto_id=(payload.get("produto_id") or "").strip(),
            empresa_id=(payload.get("empresa_id") or "").strip(),
            quantidade=payload.get("quantidade"),
            # O formulário manda `preco_digitado`; `unit_price` fica como apelido para quem
            # chamar a rota de fora (Hermes, script). Nenhum dos dois tem default.
            preco_digitado=payload.get("preco_digitado") or payload.get("unit_price"),
            desconto_percent=payload.get("desconto_percent"),
            observacao=(payload.get("observacao") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception("AA2: falha ao adicionar item do catálogo")
        raise HTTPException(status_code=400, detail=f"Não deu para adicionar o item: {e}") from None
    ncm = f" · NCM {item['ncm']}" if item["ncm"] else " · sem NCM no catálogo"
    return {
        "ok": True,
        "id": item["id"],
        "message": f"{item['code']} · {item['name'][:60]}{ncm} — {item['quantity']:g} {item['unit']} "
        f"× {brl(item['unit_price'])} = {brl(item['total'])}",
    }
