"""Oráculo — item do orçamento escolhido do CATÁLOGO, com preço do dia digitado (frente AA2).

Por que existe
--------------
O dono pediu duas coisas que se contradizem se alguém for descuidado:

  «na hora de fazer o orçamento, fazemos pelo crm, já estará lá com toda a descrição,
   só seleciona o item e as quantidades» (24/09/2026)

  «nos produtos cadastrados, deixem sem valor, quando eu for fazer os orçamentos eu edito o
   preço, por que os preços variam muito, tem muitas constantes, então quando eu orçar pego o
   preço do dia e edito na hora» (24/09/2026)

Ou seja: **descrição, código, unidade e NCM vêm do catálogo; o preço NÃO vem.** O jeito natural
de escrever "item vindo do catálogo" é copiar o produto inteiro para o item — e é exatamente aí
que o preço de venda entra sozinho. Este oráculo é a trava contra esse reflexo.

O que afirma
------------
  1. O elo existe: `proposal_items.produto_id` (uuid → `products.id`), com índice.
  2. **Preço nunca vem do catálogo** — provado em duas frentes:
     a. por AST: nenhuma constante de string do serviço nem do builder da frente cita coluna de
        preço de `products` (`reference_price`, `last_purchase_price`, `average_price`,
        `min_price`, `max_price`, `price_history`) nem `crm_products.unit_price`;
     b. por AST: o campo de preço do formulário do catálogo (`preco_digitado`/`unit_price`/
        `preco`/`valor_unitario`) NÃO tem `value` — chega vazio na tela;
     c. por comportamento: `adicionar_item_do_catalogo` RECUSA (ValueError) quando o preço vem
        vazio, mesmo com o produto escolhido.
  3. Item ligado ao catálogo não redigita: `code`, `name` e `unit` do item são iguais aos do
     produto, e o NCM é alcançável pelo elo (o item não guarda NCM próprio de propósito —
     coluna duplicada é coluna que diverge).
  4. Item SEM catálogo continua válido: os 177 itens de hoje têm `produto_id` nulo, seguem
     ativos, com nome e total, e a tela `proposta-itens` os marca (a consulta da tela lê
     `produto_id` e a coluna "Catálogo" existe).
  5. A conta fecha ao centavo: `item.total == qtd × unitário × (1 − desconto/100)` e
     `proposals.subtotal == Σ itens ativos`.

Estado medido no nascimento (produção, 24/09/2026)
--------------------------------------------------
  * `proposal_items`: 177 linhas, **nenhuma coluna de elo**, `code` vazio em 177/177 — item é
    texto livre e a frente Z5, ao virar nota, casa por DESCRIÇÃO.
  * `products`: 867 linhas (193 com NCM), e as SEIS colunas de preço **zeradas nas 867** —
    é assim que o dono quer.
  * Item 1 VERMELHO (coluna não existe), 2 VERMELHO (serviço não existe), 3/4 VERMELHOS,
    5 já verde (0 divergências) — e tem de continuar verde depois do caminho novo.

Fixture (só no sandbox, `conecta_pro_staging`): proposta com `notes` = 'FIXTURE DGX AA2' e os
itens que ela ganhar. O oráculo apaga e recria a SUA fixture a cada corrida; não toca em mais nada.

Como roda
---------
    ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\\n' ' ')
    docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" -e PYTHONPATH=/app \\
      -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= \\
      -e SMTP_PASSWORD= $ENVS conecta-pro-backend:latest \\
      python3 /app/scripts/orq/test_oraculo_aa2_orcamento_catalogo.py

Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

MARCA = "FIXTURE DGX AA2"

#: Colunas de PREÇO que não podem aparecer no caminho novo. `products` tem seis; `crm_products`
#: tem `unit_price` preenchido em 107 de 115 — as duas fontes tentam a mesma coisa.
PRECO_PROIBIDO = (
    "reference_price",
    "last_purchase_price",
    "average_price",
    "min_price",
    "max_price",
    "price_history",
)

_RAIZ = Path(__file__).resolve().parents[1].parent  # /app
_FONTES = (
    _RAIZ / "modules/crm/services/item_do_catalogo.py",
    _RAIZ / "modules/operacional/controllers/redesign_builders/_dgx_aa2_orcamento_catalogo.py",
)

#: Recontado por SQL próprio — não pelo serviço.
SQL_DIVERGE_CATALOGO = """
SELECT i.id::text, coalesce(i.code,''), coalesce(p.code,''), i.name, p.name,
       i.unit, coalesce(p.unit_of_measure,'un'), coalesce(p.ncm,'')
  FROM proposal_items i JOIN products p ON p.id = i.produto_id
 WHERE i.produto_id IS NOT NULL
   AND (coalesce(i.code,'') <> coalesce(p.code,'')
     OR i.name <> p.name
     OR lower(i.unit) <> lower(coalesce(p.unit_of_measure,'un')))
"""

SQL_TOTAL_ITEM = """
SELECT count(*) FROM proposal_items i
 WHERE coalesce(i.is_active,true)
   AND abs(round(i.total::numeric,2)
         - round((i.quantity * i.unit_price * (1 - coalesce(i.discount_percent,0)/100))::numeric,2)) > 0.01
"""

SQL_SUBTOTAL = """
SELECT count(*) FROM (
  SELECT p.id, round(p.subtotal::numeric,2) s, round(sum(i.total)::numeric,2) si
    FROM proposals p JOIN proposal_items i ON i.proposal_id = p.id AND coalesce(i.is_active,true)
   WHERE coalesce(p.is_active,true) GROUP BY p.id, p.subtotal) x
 WHERE abs(s - si) > 0.01
"""


def _strings_do_modulo(caminho: Path) -> list[str]:
    """Só constantes de string do AST: comentário que EXPLICA a proibição não conta como violação."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


#: Como o campo de PREÇO pode se chamar no formulário. Qualquer um deles com `value` é
#: preenchimento automático — o que o dono cancelou.
CHAVES_DE_PRECO = ("preco_digitado", "unit_price", "preco", "valor_unitario")


def _campo_preco_sem_valor(caminho: Path) -> str | None:
    """No AST do builder: o campo de preço do formulário do catálogo não pode trazer default."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achou = False
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Dict):
            continue
        chaves = {k.value for k in no.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "key" not in chaves:
            continue
        alvo = next(
            (v for k, v in zip(no.keys, no.values, strict=False) if isinstance(k, ast.Constant) and k.value == "key"),
            None,
        )
        if not (isinstance(alvo, ast.Constant) and alvo.value in CHAVES_DE_PRECO):
            continue
        achou = True
        if "value" in chaves:
            return f"o campo `{alvo.value}` do formulário do catálogo tem `value` — o preço tem de chegar VAZIO"
    if not achou:
        return f"não achei campo de preço {CHAVES_DE_PRECO} no formulário do catálogo (AST)"
    return None


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # ── 1) o elo ────────────────────────────────────────────────────────────────────────
    try:
        from modules.crm.services import item_do_catalogo as ic
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: serviço crm/services/item_do_catalogo.py não importa: {e}")
        return 1

    # ── 2a/2b) o preço não vem do catálogo — prova por AST ───────────────────────────────
    for fonte in _FONTES:
        if not fonte.exists():
            falhas.append(f"fonte da frente não existe: {fonte}")
            continue
        for s in _strings_do_modulo(fonte):
            baixo = s.lower()
            for col in PRECO_PROIBIDO:
                if col in baixo:
                    falhas.append(f"{fonte.name}: string cita `{col}` — coluna de preço do catálogo")
            if "crm_products" in baixo and "unit_price" in baixo:
                falhas.append(f"{fonte.name}: string lê `crm_products.unit_price` — preço de catálogo")
    tela = _FONTES[1]
    if tela.exists():
        desvio = _campo_preco_sem_valor(tela)
        if desvio:
            falhas.append(desvio)

    async with async_session_factory() as db:
        await ic.garantir_coluna(db)
        col = (
            await db.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    " WHERE table_name='proposal_items' AND column_name='produto_id'"
                )
            )
        ).scalar()
        if col != "uuid":
            falhas.append(f"proposal_items.produto_id ausente ou não-uuid (achei {col!r})")
        idx = (
            await db.execute(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE tablename='proposal_items' AND indexdef ILIKE '%produto_id%'"
                )
            )
        ).scalar()
        if not idx:
            falhas.append("proposal_items.produto_id sem índice")

        # ── fixture: proposta própria, recriada a cada corrida ──────────────────────────
        await db.execute(
            text("DELETE FROM proposal_items WHERE proposal_id IN (SELECT id FROM proposals WHERE notes = :m)"),
            {"m": MARCA},
        )
        await db.execute(text("DELETE FROM proposals WHERE notes = :m"), {"m": MARCA})
        await db.commit()
        emp = (await db.execute(text("SELECT id::text FROM empresas ORDER BY razao_social LIMIT 1"))).scalar()
        prod = (
            await db.execute(
                text(
                    "SELECT id::text, code, name, coalesce(unit_of_measure,'un'), coalesce(ncm,'') "
                    "  FROM products WHERE coalesce(ncm,'') <> '' ORDER BY code LIMIT 1"
                )
            )
        ).fetchone()
        if not prod or not emp:
            print("FALHOU: sandbox sem produto com NCM ou sem empresa — não dá para provar a regra")
            return 1
        pid = (
            await db.execute(
                text(
                    "INSERT INTO proposals (id, number, version, client_name, title, proposal_type, "
                    "  subtotal, discount_value, taxes, total, installments, issue_date, status, notes, "
                    "  is_active, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :n, 1, 'Cliente de fixture', 'Orçamento de fixture AA2', "
                    "  'product', 0, 0, 0, 0, 1, current_date, 'draft', :m, true, now(), now()) "
                    "RETURNING id::text"
                ),
                {"n": f"AA2-{MARCA}", "m": MARCA},
            )
        ).scalar()
        await db.commit()

        # ── 2c) preço vazio tem de ser RECUSADO ─────────────────────────────────────────
        for vazio in (None, "", "   "):
            try:
                await ic.adicionar_item_do_catalogo(
                    db, proposal_id=pid, produto_id=prod[0], empresa_id=emp, quantidade="2", preco_digitado=vazio
                )
                falhas.append(f"preço {vazio!r} foi aceito — o catálogo não pode preencher preço por omissão")
            except ValueError:
                pass
            except Exception as e:  # noqa: BLE001
                falhas.append(f"preço {vazio!r}: erro inesperado {type(e).__name__}: {e}")
            await db.rollback()

        # ── 3) com preço digitado: nasce ligado e sem redigitar ─────────────────────────
        try:
            item = await ic.adicionar_item_do_catalogo(
                db, proposal_id=pid, produto_id=prod[0], empresa_id=emp, quantidade="2", preco_digitado="1.250,50"
            )
        except Exception as e:  # noqa: BLE001
            falhas.append(f"item do catálogo com preço digitado falhou: {type(e).__name__}: {e}")
            item = None
        if item:
            if item.get("unit_price") != 1250.50:
                falhas.append(f"preço digitado 1.250,50 virou {item.get('unit_price')!r}")
            if item.get("ncm") != prod[4]:
                falhas.append(f"NCM do item {item.get('ncm')!r} ≠ NCM do produto {prod[4]!r}")

        diverg = (await db.execute(text(SQL_DIVERGE_CATALOGO))).fetchall()
        for d in diverg:
            falhas.append(
                f"item {d[0]} diverge do catálogo: code {d[1]!r}≠{d[2]!r} · nome {d[3]!r}≠{d[4]!r} · un {d[5]!r}≠{d[6]!r}"
            )
        ligados = (await db.execute(text("SELECT count(*) FROM proposal_items WHERE produto_id IS NOT NULL"))).scalar()
        if not ligados:
            falhas.append("nenhum item ligado ao catálogo — o elo não está sendo escrito")
        sem_ncm = (
            await db.execute(
                text(
                    "SELECT count(*) FROM proposal_items i JOIN products p ON p.id=i.produto_id "
                    " WHERE i.produto_id IS NOT NULL AND coalesce(p.ncm,'') = ''"
                )
            )
        ).scalar()

        # ── 4) item sem catálogo continua de pé, e a tela o marca ───────────────────────
        soltos = (
            await db.execute(
                text(
                    "SELECT count(*) FROM proposal_items "
                    " WHERE produto_id IS NULL AND coalesce(is_active,true) AND coalesce(name,'') <> ''"
                )
            )
        ).scalar()
        if soltos < 1:
            falhas.append("nenhum item digitado à mão sobrou — os 177 orçamentos reais não podem sumir")
        quebrados = (
            await db.execute(
                text("SELECT count(*) FROM proposal_items WHERE produto_id IS NULL AND coalesce(name,'') = ''")
            )
        ).scalar()
        if quebrados:
            falhas.append(f"{quebrados} item(ns) sem catálogo e sem nome — o caminho antigo quebrou")

        crm_py = _RAIZ / "modules/operacional/controllers/redesign_builders/crm.py"
        fonte_crm = crm_py.read_text(encoding="utf-8") if crm_py.exists() else ""
        if "i.produto_id" not in fonte_crm:
            falhas.append("a tela `proposta-itens` não lê produto_id — o item sem catálogo não é marcado")
        if '"Catálogo"' not in fonte_crm:
            falhas.append('a tela `proposta-itens` não tem a coluna "Catálogo"')
        if "_telas_aa2" not in fonte_crm:
            falhas.append("crm.py não chama telas() da frente AA2 — tela sem porta não existe")

        # ── 5) a conta fecha ao centavo ─────────────────────────────────────────────────
        n_item = (await db.execute(text(SQL_TOTAL_ITEM))).scalar()
        if n_item:
            falhas.append(f"{n_item} item(ns) com total ≠ qtd × unitário × (1 − desconto)")
        n_sub = (await db.execute(text(SQL_SUBTOTAL))).scalar()
        if n_sub:
            falhas.append(f"{n_sub} proposta(s) com subtotal ≠ Σ dos itens")

        total_itens = (await db.execute(text("SELECT count(*) FROM proposal_items"))).scalar()
        total_prod = (await db.execute(text("SELECT count(*) FROM products WHERE coalesce(ativo,true)"))).scalar()

    print(
        f"itens de orçamento: {total_itens} · ligados ao catálogo: {ligados} "
        f"(sem NCM no produto: {sem_ncm}) · digitados à mão: {soltos} · catálogo: {total_prod} produtos"
    )
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no item do orçamento vindo do catálogo")
    print("OK orçamento×catálogo: elo gravado, descrição/unidade/NCM do catálogo, preço só do humano, conta fecha")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
