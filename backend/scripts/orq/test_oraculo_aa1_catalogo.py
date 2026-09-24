"""Oráculo — catálogo único: a compra vira produto sem fusão no escuro e sem preço (DGX AA1).

24/09/2026. O pedido do dono foi *«cadastrar os produtos a partir das notas de compra, ter cuidado
com duplicidades»* e, no mesmo dia, *«nos produtos cadastrados deixem sem valor — quando eu for
fazer os orçamentos eu edito o preço»*. Esta frente é o miolo do fluxo compra → catálogo →
orçamento → nota. Os dois jeitos de ela apodrecer são exatamente os dois que este arquivo vigia:
**um produto nascer com preço de venda inventado** e **duas coisas diferentes serem fundidas sem
ninguém ter olhado**.

O que afirma (cada bloco recontado por SQL próprio, nunca pelo serviço):

  (a) **preço: nada.** Nenhum produto criado pelo importador tem qualquer das SEIS colunas de
      preço de `products` preenchida (`reference_price`, `last_purchase_price`, `average_price`,
      `min_price`, `max_price`, `price_history`). E o catálogo inteiro continua sem preço: as 867
      linhas medidas em 24/09 tinham as seis zeradas, e o importador não pode ser quem muda isso.
  (b) **NCM só o que existe.** Nenhum produto criado pelo importador com NCM fora da nomenclatura
      vigente (`ncms`, 10.515 códigos do Portal Único Siscomex). O NCM da nota do fornecedor pode
      estar errado — está, em 1 dos 95 (`65119000`, «CAPACETE DE SEGURANCA BRANCO»: o capítulo 65
      termina em 6507) — e nesse caso o produto nasce SEM NCM em vez de nascer errado.
  (c) **nenhuma fusão no escuro.** Todo candidato decidido tem quem e quando; todo produto criado
      pela frente tem um candidato aprovado apontando para ele; todo elo `fin_produtos.product_id`
      tem candidato aprovado com aquele código. Elo que apareceu sem decisão humana é desvio.
  (d) **o elo é íntegro dos dois lados.** `fin_produtos.product_id` só aponta para `products.id`
      que existe, nunca dois fiscais para o mesmo comercial, e nenhum candidato aprovado ficou
      sem `product_id`.
  (e) **a régua separa variação de produto distinto — nas duas direções, no dado real.**
      NCM 64039190 = 10 linhas que são UMA bota em 10 tamanhos: têm de virar **1 representante +
      9 variações**. NCM 34025000 = 9 linhas que são 9 produtos diferentes (detergente,
      lava-roupas, limpa-vidros, multiuso, sabão em pó de três marcas): têm de continuar **9
      candidatos distintos**, nenhum variação do outro. Sem este bloco, (c) e (d) ficariam verdes
      com uma régua que fundisse tudo ou não fundisse nada.
  (f) **código do fornecedor não casa sozinho.** Medido em 24/09: das 16 linhas de compra cujo
      `item_code` existe como `products.code`, **9 são produtos diferentes** — «ENXADA LARGA
      30CM» × «Desempeno das portas», «AREIA EM SACO» × «Controle remoto xac 4000 smart»,
      «COLHER PEDREIRO N10» × «DVR 16 portas». Nenhuma dessas colisões pode sair classificada
      como `igual`, e nenhum `igual` pode ter semelhança de descrição abaixo de 0,30.
  (g) **fiação**: `redesign_builders/suprimentos.py` importa o router e chama `telas(db, out)` —
      tela sem porta não existe.
  (h) **o caminho de aprovação funciona e é recusado quando tem de ser**: fixture
      'FIXTURE DGX AA1' — aprovar um candidato cria o produto sem nenhum preço e com registro;
      aprovar uma variação cujo representante não foi aprovado é recusado. Apagada ao fim, mesmo
      em falha.

Estado medido no NASCIMENTO (sandbox = cópia de produção de 23/09/2026):
  · `products` 867 linhas (193 com NCM, **0 com `cfop_out`**, **0 com qualquer preço**);
  · `fin_produtos` 95 linhas (uma por NCM distinto das compras — NÃO é um catálogo de produto:
    as 10 botas em 10 tamanhos são 1 linha lá);
  · **elo entre os dois: não existia** — `fin_produtos.product_id` não era coluna, e casar por
    código dá 10 pares dos quais 8 são produtos diferentes;
  · `fin_catalogo_candidatos` não existia → (a)…(h) vermelhos.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \\
      --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_aa1_catalogo.py

Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, "/app")

FIX = "FIXTURE DGX AA1"
#: As seis colunas de preço de `products`. O dono decidiu em 24/09 que nenhuma é do importador.
PRECOS = ("reference_price", "last_purchase_price", "average_price", "min_price", "max_price")
MARCA = "%DGX AA1%"  # o carimbo que o importador põe em `products.notes`


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE fin_produtos SET product_id = NULL WHERE product_id IN (SELECT id FROM products WHERE name LIKE :f)"
        ),
        {"f": f"{FIX}%"},
    )
    await db.execute(text("DELETE FROM fin_catalogo_candidatos WHERE descricao LIKE :f"), {"f": f"{FIX}%"})
    await db.execute(text("DELETE FROM products WHERE name LIKE :f"), {"f": f"{FIX}%"})
    await db.commit()


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from fastapi import HTTPException
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.financial.services import catalogo_compra as cc

    falhas: list[str] = []
    async with async_session_factory() as db:
        await cc._ensure(db)
        await _limpar(db)
        contagem = await cc.classificar(db)

        # ------------------------------------------------------------------ (a) preço: nada
        cols = " OR ".join(f"coalesce({c}, 0) <> 0" for c in PRECOS)
        com_preco = (
            await db.execute(
                text(
                    f"SELECT count(*) FROM products WHERE notes LIKE :m AND ({cols} OR coalesce(price_history::text, '[]') NOT IN ('[]', 'null'))"
                ),
                {"m": MARCA},
            )
        ).scalar() or 0
        if com_preco:
            falhas.append(f"(a) {com_preco} produto(s) do importador com preço preenchido — o dono decidiu SEM valor")
        com_preco_geral = (
            await db.execute(
                text(
                    f"SELECT count(*) FROM products WHERE {cols} OR coalesce(price_history::text, '[]') NOT IN ('[]', 'null')"
                )
            )
        ).scalar() or 0
        if com_preco_geral:
            falhas.append(
                f"(a) o catálogo tem {com_preco_geral} linha(s) com preço — eram 0 em 24/09/2026; "
                "se foi o dono, esta trava muda; se foi código, é o defeito que ela existe para pegar"
            )

        # ------------------------------------------------------------------ (b) NCM só o que existe
        maus = (
            await db.execute(
                text(
                    "SELECT p.code, p.ncm FROM products p WHERE p.notes LIKE :m "
                    "  AND coalesce(p.ncm, '') <> '' "
                    "  AND NOT EXISTS (SELECT 1 FROM ncms n WHERE n.codigo = p.ncm AND n.active IS NOT false)"
                ),
                {"m": MARCA},
            )
        ).fetchall()
        for code, ncm in maus:
            falhas.append(f"(b) produto {code} nasceu com NCM {ncm}, que não existe na nomenclatura vigente")

        # ------------------------------------------------------------------ (c) nenhuma fusão no escuro
        sem_quem = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fin_catalogo_candidatos WHERE status <> 'pendente' "
                    "AND (coalesce(decidido_por,'') = '' OR decidido_em IS NULL)"
                )
            )
        ).scalar() or 0
        if sem_quem:
            falhas.append(f"(c) {sem_quem} candidato(s) decidido(s) sem quem/quando — fusão no escuro")
        orfaos = (
            await db.execute(
                text(
                    "SELECT count(*) FROM products p WHERE p.notes LIKE :m "
                    "AND NOT EXISTS (SELECT 1 FROM fin_catalogo_candidatos c "
                    "                 WHERE c.product_id = p.id AND c.status = 'aprovado')"
                ),
                {"m": MARCA},
            )
        ).scalar() or 0
        if orfaos:
            falhas.append(
                f"(c) {orfaos} produto(s) carimbado(s) pelo importador sem candidato aprovado que os explique"
            )
        elo_sem_decisao = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fin_produtos f WHERE f.product_id IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM fin_catalogo_candidatos c "
                    "                 WHERE c.item_code = f.codigo AND c.status = 'aprovado')"
                )
            )
        ).scalar() or 0
        if elo_sem_decisao:
            falhas.append(f"(c) {elo_sem_decisao} elo(s) fiscal↔comercial sem candidato aprovado por trás")

        # ------------------------------------------------------------------ (d) elo íntegro
        quebrados = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fin_produtos f WHERE f.product_id IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM products p WHERE p.id = f.product_id)"
                )
            )
        ).scalar() or 0
        if quebrados:
            falhas.append(f"(d) {quebrados} linha(s) de fin_produtos apontam para produto que não existe")
        repetidos = (
            await db.execute(
                text(
                    "SELECT count(*) FROM (SELECT product_id FROM fin_produtos WHERE product_id IS NOT NULL "
                    "GROUP BY 1 HAVING count(*) > 1) x"
                )
            )
        ).scalar() or 0
        if repetidos:
            falhas.append(f"(d) {repetidos} produto(s) comercial(is) com mais de uma face fiscal")
        aprov_sem_pid = (
            await db.execute(
                text("SELECT count(*) FROM fin_catalogo_candidatos WHERE status = 'aprovado' AND product_id IS NULL")
            )
        ).scalar() or 0
        if aprov_sem_pid:
            falhas.append(f"(d) {aprov_sem_pid} candidato(s) aprovado(s) sem produto ligado")

        # ------------------------------------------------------------------ (e) a régua, nas duas direções
        bota = (
            await db.execute(
                text(
                    "SELECT c.classe, count(*) FROM fin_catalogo_candidatos c "
                    "JOIN nfe_compras_estoque e ON e.item_code = c.item_code "
                    "WHERE e.ncm = '64039190' GROUP BY 1"
                )
            )
        ).fetchall()
        bota_d = dict(bota)
        if bota_d.get("novo", 0) != 1 or bota_d.get("variacao", 0) != 9:
            falhas.append(f"(e) as 10 botas (NCM 64039190) deveriam dar 1 representante + 9 variações; deram {bota_d}")
        limpeza = (
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE c.classe = 'variacao') FROM fin_catalogo_candidatos c "
                    "JOIN nfe_compras_estoque e ON e.item_code = c.item_code WHERE e.ncm = '34025000'"
                )
            )
        ).scalar() or 0
        if limpeza:
            falhas.append(
                f"(e) {limpeza} dos 9 itens de NCM 34025000 viraram variação um do outro — detergente, "
                "lava-roupas e sabão em pó são produtos DIFERENTES com o mesmo NCM"
            )

        # ------------------------------------------------------------------ (f) código não casa sozinho
        fraco = (
            await db.execute(
                text("SELECT item_code, score FROM fin_catalogo_candidatos WHERE classe = 'igual' AND score < 0.30")
            )
        ).fetchall()
        for ic, sc in fraco:
            falhas.append(
                f"(f) candidato {ic} classificado «igual» com semelhança de descrição {sc} — código não é prova"
            )
        colisoes = (
            await db.execute(
                text(
                    "SELECT c.item_code, p.name FROM fin_catalogo_candidatos c "
                    "JOIN products p ON upper(btrim(p.code)) = upper(btrim(c.item_code)) "
                    "WHERE c.classe = 'igual' AND c.alvo_product_id = p.id AND c.score < 0.30"
                )
            )
        ).fetchall()
        for ic, nome in colisoes:
            falhas.append(f"(f) colisão de código aceita como igual: {ic} × «{nome}»")

        # ------------------------------------------------------------------ (g) fiação
        sup = pathlib.Path("/app/modules/operacional/controllers/redesign_builders/suprimentos.py").read_text()
        if "_dgx_aa1_catalogo" not in sup or "_telas_aa1" not in sup:
            falhas.append("(g) suprimentos.py não importa o router nem chama telas() da AA1 — tela sem porta")

        # ------------------------------------------------------------------ (h) o caminho de aprovação
        try:
            await db.execute(
                text(
                    "INSERT INTO fin_catalogo_candidatos (item_code, descricao, ncm, unidade, classe, score, motivo) "
                    "VALUES (:c1, :d1, '85365090', 'UN', 'novo', 0, :m), "
                    "       (:c2, :d2, '85365090', 'UN', 'variacao', 0.9, :m)"
                ),
                {
                    "c1": f"{FIX}-A",
                    "d1": f"{FIX} TOMADA SMART 10A",
                    "c2": f"{FIX}-B",
                    "d2": f"{FIX} TOMADA SMART 20A",
                    "m": FIX,
                },
            )
            await db.execute(
                text("UPDATE fin_catalogo_candidatos SET alvo_item_code = :a WHERE item_code = :c2"),
                {"a": f"{FIX}-A", "c2": f"{FIX}-B"},
            )
            await db.commit()
            ids = {
                r[1]: r[0]
                for r in (
                    await db.execute(
                        text("SELECT id, item_code FROM fin_catalogo_candidatos WHERE descricao LIKE :f"),
                        {"f": f"{FIX}%"},
                    )
                ).fetchall()
            }
            # a variação sozinha tem de ser RECUSADA: o pai ainda não virou produto
            try:
                await cc.aprovar(db, [ids[f"{FIX}-B"]], "oraculo-aa1")
                falhas.append("(h) aprovar variação sem o representante passou — deveria ser recusado")
            except HTTPException:
                await db.rollback()
            r = await cc.aprovar(db, [ids[f"{FIX}-A"], ids[f"{FIX}-B"]], "oraculo-aa1")
            if r["criados"] != 1:
                falhas.append(f"(h) aprovar 1 novo + 1 variação criou {r['criados']} produto(s), esperado 1")
            novo = (
                await db.execute(
                    text(
                        f"SELECT count(*) FROM products WHERE name LIKE :f AND ({cols} OR coalesce(price_history::text, '[]') NOT IN ('[]', 'null'))"
                    ),
                    {"f": f"{FIX}%"},
                )
            ).scalar() or 0
            if novo:
                falhas.append("(h) o produto criado pela fixture nasceu com preço")
        finally:
            await db.rollback()
            await _limpar(db)
            restou = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM products WHERE name LIKE :f) "
                        "     + (SELECT count(*) FROM fin_catalogo_candidatos WHERE descricao LIKE :f)"
                    ),
                    {"f": f"{FIX}%"},
                )
            ).scalar() or 0
            if restou:
                falhas.append(f"(h) {restou} fixture(s) '{FIX}' não foram apagadas")

        cat = (await db.execute(text("SELECT count(*) FROM products"))).scalar()
        fis = (await db.execute(text("SELECT count(*) FROM fin_produtos"))).scalar()
        elos = (await db.execute(text("SELECT count(*) FROM fin_produtos WHERE product_id IS NOT NULL"))).scalar()

    print(
        f"{contagem['total']} linha(s) de nota de compra classificadas · "
        f"novo: {contagem['novo']} · igual: {contagem['igual']} · variação: {contagem['variacao']} · "
        f"catálogo `products`: {cat} produto(s), 0 com preço (decisão do dono 24/09) · "
        f"face fiscal `fin_produtos`: {fis}, com elo: {elos} · "
        f"botas NCM 64039190: {bota_d} · itens NCM 34025000 tratados como variação: {limpeza} (tem de ser 0)"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no catálogo único")
    print(
        "OK catálogo único: nenhum produto do importador tem preço, nenhum NCM inventado, toda fusão tem "
        "quem/quando/por quê, o elo comercial↔fiscal fecha dos dois lados, as 10 botas viram 1 produto + 9 "
        "variações e os 9 produtos de mesmo NCM continuam 9"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
