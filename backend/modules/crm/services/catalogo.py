"""Catálogo UNIFICADO para orçamento: preço praticado + identidade fiscal.

O catálogo do Jordan mora em duas tabelas, e isso não é acidente — cada uma sabe uma coisa
que a outra não sabe:

  `crm_products`  115 itens · SEMEADOS do histórico de 33 propostas dele.
                  Têm PREÇO PRATICADO, com a proposta e a data de origem carimbadas.
                  Não têm NCM, CEST nem código do Bling.

  `products`      854 itens · IMPORTADOS do Bling em 27/08/2026.
                  Têm IDENTIDADE FISCAL (código, NCM, CEST, origem, GTIN, unidade).
                  NÃO têm preço — decisão do Jordan: "desconsidere os preços, são antigos".

Fundir fisicamente as duas seria destruir informação: ou o preço praticado perderia o
lastro, ou a identidade fiscal ganharia um preço velho que ninguém validou. Então a união
acontece na LEITURA, com a origem de cada linha declarada — quem monta o orçamento vê de
onde veio cada número, e um item sem preço aparece como sem preço em vez de zero.

Regra de desempate: quando o mesmo NOME existe nas duas, vence a linha COM PREÇO
(`crm_products`), porque a pergunta do orçamento é "quanto custa". O código fiscal do
irmão viaja junto no campo `ncm`, então nada se perde.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

#: ⚠️ Sem `::` neste SQL: dentro de `text()` o SQLAlchemy lê `NULL::varchar` como o bind
#: param `:varchar` e estoura "A value is required for bind parameter". Use cast(x AS t).
#: Uma linha do catálogo, venha de onde vier. `preco` é None quando ninguém validou um
#: valor — nunca 0, que seria um preço afirmado.
_SQL = """
WITH praticado AS (
    SELECT sku,
           name                              AS nome,
           coalesce(unit, 'un')              AS unidade,
           unit_price                        AS preco,
           category                          AS categoria,
           cast(NULL AS varchar)             AS ncm,
           description                       AS lastro,
           'preço praticado'                 AS origem,
           1                                 AS prioridade
    FROM crm_products
    WHERE coalesce(is_active, true)
),
bling AS (
    SELECT p.code                            AS sku,
           p.name                            AS nome,
           coalesce(p.unit_of_measure, 'UN') AS unidade,
           cast(NULL AS numeric)             AS preco,
           p.brand                           AS categoria,
           p.ncm                             AS ncm,
           p.notes                           AS lastro,
           'Bling (sem preço)'               AS origem,
           2                                 AS prioridade
    FROM products p
    WHERE coalesce(p.ativo, true)
      -- O mesmo nome nas duas: a de preço vence. Ver o docstring.
      AND NOT EXISTS (SELECT 1 FROM crm_products c
                      WHERE lower(btrim(c.name)) = lower(btrim(p.name))
                        AND coalesce(c.is_active, true))
),
tudo AS (SELECT * FROM praticado UNION ALL SELECT * FROM bling)
SELECT sku, nome, unidade, preco, categoria, ncm, lastro, origem
FROM tudo
-- Os casts são obrigatórios: um bind nu comparado a NULL não deixa o asyncpg inferir
-- o tipo e ele levanta AmbiguousParameterError antes de chegar ao banco.
-- E NÃO escreva dois-pontos seguidos de nome aqui dentro: o SQLAlchemy lê bind param
-- ATÉ DENTRO de comentário -- , e foi assim que este arquivo pediu um "param" fantasma.
WHERE (cast(:busca AS text) IS NULL
       OR unaccent(nome) ILIKE cast(:busca AS text)
       OR unaccent(coalesce(sku, '')) ILIKE cast(:busca AS text))
  AND (cast(:categoria AS text) IS NULL
       OR unaccent(coalesce(categoria, '')) ILIKE cast(:categoria AS text))
  AND (cast(:so_com_preco AS boolean) = false OR preco IS NOT NULL)
ORDER BY prioridade, nome
LIMIT :limite
"""

#: Busca de UM item por SKU, nas duas tabelas. Usada quando o orçamento resolve `sku`.
_SQL_SKU = """
SELECT sku, nome, unidade, preco, categoria, ncm, lastro, origem, empresa_id FROM (
    SELECT sku, name AS nome, coalesce(unit,'un') AS unidade, unit_price AS preco,
           category AS categoria, cast(NULL AS varchar) AS ncm, description AS lastro,
           'preço praticado' AS origem, empresa_id, 1 AS prioridade
    FROM crm_products WHERE coalesce(is_active, true) AND upper(sku) = ANY(:skus)
    UNION ALL
    -- Bling não tem empresa: item de lá herda a do orçamento, ou é recusado.
    SELECT code, name, coalesce(unit_of_measure,'UN'), cast(NULL AS numeric),
           brand, ncm, notes, 'Bling (sem preço)', cast(NULL AS uuid), 2
    FROM products WHERE coalesce(ativo, true) AND upper(code) = ANY(:skus)
) t ORDER BY prioridade
"""


async def buscar(db, *, busca=None, categoria=None, so_com_preco=False,
                 limite=40) -> list[dict[str, Any]]:
    """Procura no catálogo unificado. `busca` casa nome OU SKU, ignorando acento."""
    linhas = (await db.execute(text(_SQL), {
        "busca": f"%{busca.strip()}%" if str(busca or "").strip() else None,
        "categoria": f"%{categoria.strip()}%" if str(categoria or "").strip() else None,
        "so_com_preco": bool(so_com_preco),
        "limite": max(1, min(int(limite), 200)),
    })).mappings().all()
    return [dict(x) for x in linhas]


async def por_sku(db, skus: list[str]) -> dict[str, dict[str, Any]]:
    """SKU → linha. Quando o mesmo SKU existe nas duas, a de PREÇO vence (ORDER BY)."""
    alvo = [str(s).strip().upper() for s in skus if str(s or "").strip()]
    if not alvo:
        return {}
    linhas = (await db.execute(text(_SQL_SKU), {"skus": alvo})).mappings().all()
    saida: dict[str, dict[str, Any]] = {}
    for x in linhas:
        saida.setdefault((x["sku"] or "").upper(), dict(x))
    return saida


# ── RESOLUÇÃO DE ITENS: a única regra sobre de onde um preço pode vir ──────────────────
# Dois consumidores usam isto: `gerar_orcamento_itens_doc` (PDF) e `criar_orcamento`
# (grava proposta). A regra mora aqui e não em cada um porque duas cópias divergem, e a
# cópia que divergir vai ser justamente a que deixa um preço inventado chegar ao cliente.

#: Categoria do catálogo → natureza no PDF/proposta. Fora do mapa é material.
NATUREZA = {
    "Mão de obra": "servico", "Serviço técnico": "servico",
    "Locação": "servico", "Software / plataforma": "servico",
}


async def resolver_itens(db, itens: list) -> tuple[list[dict], list[str], str | None]:
    """(linhas, lastro, recusa). `recusa` preenchida = nada de linhas, e o motivo é o texto.

    As DUAS únicas fontes legítimas de preço são o catálogo (preço praticado, com a
    proposta de origem) e um `valor_unit` que a PESSOA informou. Não existe terceira.
    """
    if not isinstance(itens, list) or not itens:
        return [], [], ("informe os itens do orçamento (sku do catálogo ou descrição + "
                        "valor); não vou montar orçamento sem linha.")

    skus = [str(i.get("sku")).strip().upper() for i in itens
            if isinstance(i, dict) and i.get("sku")]
    cat = await por_sku(db, skus) if skus else {}

    linhas: list[dict] = []
    lastro: list[str] = []
    for n, it in enumerate(itens, 1):
        if not isinstance(it, dict):
            return [], [], f"item {n} veio malformado; esperava objeto com sku ou descrição."
        sku = str(it.get("sku") or "").strip().upper()
        try:
            # `it.get("qtd") or 1` estaria ERRADO: 0 é falsy e viraria 1 em silêncio —
            # um item com quantidade zero sairia cobrado como 1 no orçamento do cliente.
            bruto = it.get("qtd")
            qtd = float(1 if bruto is None or bruto == "" else bruto)
        except (TypeError, ValueError):
            return [], [], f"item {n}: quantidade inválida ({it.get('qtd')!r})."
        if qtd <= 0:
            return [], [], f"item {n}: quantidade tem de ser maior que zero."
        informado = it.get("valor_unit")
        informado = float(informado) if informado not in (None, "") else None

        if sku:
            p = cat.get(sku)
            if p is None:
                # Fail-closed: SKU fantasma NÃO vira descrição livre a preço zero.
                return [], [], (f"item {n}: SKU {sku} não existe no catálogo ativo. "
                                f"Confira em consultar_crm consulta=catalogo.")
            desc = p["nome"]
            unidade = it.get("unidade") or p["unidade"] or "un"
            valor = informado if informado is not None else (
                float(p["preco"]) if p["preco"] is not None else None)
            tipo = it.get("tipo") or NATUREZA.get(p["categoria"] or "", "material")
            if valor is None:
                return [], [], (f"item {n} ({sku} — {desc[:40]}) veio do {p['origem']} e "
                                f"não tem preço validado. Me diga o `valor_unit` dele.")
            if informado is None:
                lastro.append(f"{sku}: {(p['lastro'] or '').split('.')[0]}")
            codigo = p["sku"]
        else:
            desc = str(it.get("descricao") or "").strip()
            if not desc:
                return [], [], f"item {n}: sem sku e sem descrição."
            if informado is None:
                return [], [], (f"item {n} ('{desc[:40]}') não tem SKU nem valor informado. "
                                f"Ou escolha um item do catálogo, ou me diga o valor — eu "
                                f"não estimo preço.")
            unidade, valor = it.get("unidade") or "un", informado
            tipo, codigo = it.get("tipo") or "material", None

        # ⭐ 28/08/2026 — `empresa_id` viaja COM a linha desde o catálogo. Sem isto o item
        # chega ao INSERT sem carimbo e bate no NOT NULL que subiu hoje — e batia na
        # APROVAÇÃO, o pior lugar: o Jordan clica e estoura. Item fora do catálogo vem
        # None e herda a empresa do orçamento; se nem essa houver, é recusa, nunca NULL.
        linhas.append({"descricao": desc, "qtd": qtd, "unidade": unidade,
                       "valor_unit": valor, "tipo": tipo, "codigo": codigo,
                       # str(): o payload do rascunho é JSONB e o driver devolve UUID,
                       # que não serializa. Erro só aparece na hora de GRAVAR o rascunho.
                       "empresa_id": (str(p["empresa_id"]) if sku and sku in cat
                                      and p.get("empresa_id") else None)})
    return linhas, lastro, None
