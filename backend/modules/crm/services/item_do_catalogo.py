"""Item do orçamento escolhido no CATÁLOGO — com o preço do dia digitado (frente DGX AA2).

O que isto resolve
------------------
Até 24/09/2026 o item de um orçamento do CRM era **texto livre**: alguém digitava nome, unidade
e preço na mão. Medido em produção: `proposal_items` tem 177 linhas e **`code` vazio em 177/177**.
A consequência está a duas telas daqui — a frente Z5 (orçamento aprovado → rascunho de nota) tem
de casar o item com o produto **pela descrição**, porque não há outro fio entre os dois.

Aqui o item passa a carregar `produto_id`, e a descrição/código/unidade vêm do catálogo prontos.

A regra que este arquivo existe para PROTEGER
---------------------------------------------
    «nos produtos cadastrados, deixem sem valor, quando eu for fazer os orçamentos eu edito o
     preço, por que os preços variam muito, tem muitas constantes, então quando eu orçar pego o
     preço do dia e edito na hora»  — Jordan, 24/09/2026

Então: **o catálogo entrega identidade (código, descrição, unidade, NCM) e NUNCA preço.** Não há
preço sugerido, não há "último preço", não há margem. Preço vazio é RECUSA, não é zero — zero
seria um item de graça no orçamento do cliente, que é pior que um erro visível.

É por isso que `adicionar_item_do_catalogo` recebe o preço como veio do formulário (string) em
vez de um float com default: um `float = 0.0` na assinatura seria exatamente o preenchimento
automático que o dono cancelou, escrito de um jeito que ninguém percebe na revisão.

Fonte do catálogo: `products` (867 linhas, importadas do Bling em 27/08/2026; 193 com NCM). Ver
a §«premissa» do relatório `auditoria/frentes/DGX_AA2_orcamento_catalogo.md` — a casa tem outros
dois cadastros de produto e a unificação é a frente AA1.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Elo item do orçamento → produto do catálogo. Idempotente: roda a cada acesso à tela.
#: NÃO entra no model SQLAlchemy de propósito — `ProposalItem` é lido por dezenas de caminhos
#: (CRM clássico, PDF da proposta, Z5) e uma coluna no ORM antes da coluna no banco derruba
#: todos eles. Aqui a leitura e a escrita são por SQL explícito.
DDL = (
    "ALTER TABLE proposal_items ADD COLUMN IF NOT EXISTS produto_id uuid",
    "CREATE INDEX IF NOT EXISTS ix_proposal_items_produto_id ON proposal_items (produto_id)",
    "COMMENT ON COLUMN proposal_items.produto_id IS "
    "'Produto do catálogo (products.id) de onde vieram código, descrição, unidade e NCM. "
    "NULO = item digitado à mão (é o caso dos 177 itens anteriores a 24/09/2026). "
    "Jamais carrega preço: o preço do dia é digitado por quem orça.'",
)

#: O que o catálogo entrega ao item. Repare no que NÃO está aqui: nenhuma coluna de preço.
SQL_PRODUTO = """
SELECT id::text, code, name, coalesce(unit_of_measure,'un'), coalesce(ncm,''), coalesce(description,'')
  FROM products
 WHERE id = CAST(:p AS uuid) AND coalesce(ativo,true)
"""


async def garantir_coluna(db: AsyncSession) -> None:
    """DDL idempotente. Chamada pela tela e por cada ação."""
    for ddl in DDL:
        await db.execute(text(ddl))
    await db.commit()


async def buscar_produto(db: AsyncSession, produto_id: str) -> dict | None:
    r = (await db.execute(text(SQL_PRODUTO), {"p": str(produto_id)})).fetchone()
    if not r:
        return None
    return {"id": r[0], "code": r[1], "name": r[2], "unit": r[3], "ncm": r[4], "description": r[5]}


def _numero(valor, oque: str) -> float:
    """Converte o que foi DIGITADO. Vazio é recusa — nunca default."""
    if valor is None or str(valor).strip() == "":
        raise ValueError(f"Digite {oque}.")
    from modules.operacional.controllers.redesign_data_controller import _brl_norm

    try:
        return float(_brl_norm(valor))
    except (TypeError, ValueError):
        raise ValueError(f"{oque.capitalize()} não é um número: {valor!r}") from None


async def adicionar_item_do_catalogo(
    db: AsyncSession,
    *,
    proposal_id: str,
    produto_id: str,
    empresa_id: str,
    quantidade,
    preco_digitado,
    desconto_percent=None,
    observacao: str | None = None,
    opcional: bool = False,
) -> dict:
    """Adiciona à proposta um item que É um produto do catálogo.

    `preco_digitado` vazio levanta `ValueError`: o preço do dia é do humano, e o catálogo não
    tem o que sugerir (as seis colunas de preço de `products` estão zeradas nas 867 linhas, por
    decisão do dono). `quantidade` idem.

    Reusa `ProposalRepository.add_item` — é ele que recalcula `proposals.subtotal/total` e que
    recusa proposta já fechada. Depois grava o elo por SQL (a coluna não está no ORM).
    """
    from modules.crm.repositories.proposal_repository import ProposalRepository
    from modules.crm.schemas.proposal import ProposalItemCreate

    await garantir_coluna(db)

    qtd = _numero(quantidade, "a quantidade")
    if qtd <= 0:
        raise ValueError("A quantidade tem de ser maior que zero.")
    preco = _numero(preco_digitado, "o preço do dia (o catálogo não sugere preço)")
    if preco < 0:
        raise ValueError("O preço não pode ser negativo.")
    desc = 0.0 if desconto_percent in (None, "") else _numero(desconto_percent, "o desconto")

    prod = await buscar_produto(db, produto_id)
    if not prod:
        raise ValueError("Produto do catálogo não encontrado (ou inativo).")
    if not str(empresa_id or "").strip():
        raise ValueError("Escolha qual CNPJ emite este item.")

    item = await ProposalRepository(db).add_item(
        proposal_id,
        ProposalItemCreate(
            code=prod["code"],
            name=prod["name"],
            # Descrição do catálogo quando existe; senão o campo fica com o que a pessoa
            # escreveu de observação. Nunca uma descrição inventada.
            description=(prod["description"] or observacao or None),
            unit=prod["unit"],
            quantity=qtd,
            unit_price=preco,
            discount_percent=desc,
            is_optional=opcional,
            empresa_id=empresa_id,
        ),
    )
    if not item:
        raise ValueError("Proposta não encontrada ou já enviada — item só entra em rascunho/aprovada.")

    await db.execute(
        text("UPDATE proposal_items SET produto_id = CAST(:pr AS uuid) WHERE id = CAST(:i AS uuid)"),
        {"pr": prod["id"], "i": str(item.id)},
    )
    await db.commit()

    return {
        "id": str(item.id),
        "produto_id": prod["id"],
        "code": prod["code"],
        "name": prod["name"],
        "unit": prod["unit"],
        "ncm": prod["ncm"],
        "quantity": qtd,
        "unit_price": preco,
        "total": float(item.total or 0),
    }
