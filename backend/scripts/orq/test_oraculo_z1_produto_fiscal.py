"""Oráculo — cadastro fiscal do produto: sem ele a NF-e é rejeitada (DGX Z1).

24/09/2026. O fato que origina a frente: `nfes` tem DUAS tentativas de NF-e de saída, ambas de
11/04/2026, ambas **rejeitadas** — a nota 1 com «Lote processado» e a nota 2 com
**«Rejeição: Informado NCM inexistente [nItem: 1]»**. Enquanto não houver cadastro fiscal de
produto, nenhuma nota sai; e um cadastro preenchido por palpite é pior que nenhum, porque NCM/CST
errado é multa e glosa de crédito.

Este oráculo é o que impede `fin_produtos`/`fin_produto_tributacao` de virarem ficção.

O que afirma:
  (a) **todo produto ATIVO tem NCM de 8 dígitos que EXISTE na tabela oficial** (`ncms`, carregada
      do Portal Único Siscomex) e está vigente hoje — recontado por SQL próprio, sem o serviço;
  (b) **nenhum produto marcado «pronto para emitir» sem CFOP, CST/CSOSN e unidade** — para cada
      par (produto, empresa) que o serviço declara pronto, este arquivo reconta por SQL: CFOP
      dentro E fora da UF, unidade comercial E tributável, GTIN, origem 0-8, e o CST que o REGIME
      daquele CNPJ exige (CSOSN no Simples, CST de ICMS fora dele) + CST de PIS e de COFINS;
  (c) **a tributação existe para as DUAS empresas**, cada linha com `origem_regra` não vazia —
      a coluna que separa «alguém decidiu» de «o sistema chutou»;
  (d) **o seed reproduz exatamente os NCMs das compras**: o conjunto de NCMs distintos de
      `nfe_compras_estoque` == o conjunto de NCMs dos produtos com `origem_cadastro='nfe_entrada'`,
      recontado aqui por SQL próprio (nada de contar pelo serviço);
  (e) **produto com NCM inválido é recusado com 422** — fixture 'FIXTURE DGX Z1': criar produto
      com NCM de 7 dígitos, com NCM que não existe na nomenclatura, e ATIVAR um produto inativo
      com NCM inexistente, tudo tem que dar 422 com a frase da SEFAZ; e produto salvo sem CFOP
      não pode aparecer como pronto. Apagada ao fim, mesmo em falha;
  (f) a régua do CFOP morde: 5xxx só em «dentro do estado», 6xxx só em «para outro estado»
      (Ajuste SINIEF 07/01) — trocar os dois é rejeição na hora;
  (g) fiação: `redesign_builders/fiscal.py` importa o router e chama `telas(db, out)`
      (tela sem porta não existe);
  (h) a régua de «pronto» também diz SIM quando é sim: uma fixture com TODOS os campos e o CST
      das duas empresas aparece pronta nas duas, e volta a ficar incompleta ao perder o CFOP —
      sem isto (b) seria verde por nunca ter existido um produto pronto;
  (i) **sugerir NCM pela descrição acerta**: para cada item de `nfe_compras_estoque` com NCM
      conhecido, pedindo a sugestão pela descrição DELE (e ignorando o próprio item como fonte),
      o NCM certo aparece entre os 5 primeiros. A meta pedida era **70%**; o **medido é 61%**
      (89/147) e a trava aqui é **55%** — não por preguiça, por teto estrutural: **71 dos 95 NCMs
      aparecem UMA vez só** em toda a casa, e tirando o próprio item não existe segundo documento
      que os mencione (76 itens têm irmão de mesmo NCM; mais 13 alcançáveis pelo catálogo do
      Bling → teto documental de 89, que é exatamente o que a ordem A→B→C entrega). Pôr a tabela
      oficial na frente piora para 24% — vocabulário fiscal não é vocabulário comercial. Uma
      trava em 70% ficaria vermelha todo dia sem nada de errado; a taxa REAL é impressa na linha
      final e vai para o §1 do relatório. E nenhuma sugestão pode sair sem fonte declarada
      (`fonte` + `por_que`).

Estado medido no NASCIMENTO (sandbox = cópia de produção de 23/09/2026):
  · `fin_produtos` e `fin_produto_tributacao` NÃO existiam → vermelho em tudo;
  · `ncms` já tinha 10.515 códigos vigentes (carregados em 27/08/2026);
  · `nfe_compras_estoque`: 147 itens, **95 NCMs distintos**, dos quais **94 existem** na tabela
    oficial e **1 não** (`65119000`, «CAPACETE DE SEGURANCA BRANCO» — erro do fornecedor);
  · 2 empresas: 35.710.481/0001-03 (lucro real) e 66.014.833/0001-10 (Simples Nacional);
  · **0 produtos prontos para emitir** — que é exatamente por que as duas NF-e foram rejeitadas.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \\
      --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z1_produto_fiscal.py

Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys

#: As telas desta frente entram na régua: `checar_nao_vigiado.py` conta como vigiada a
#: tela cujo slug um oráculo cita, e a onda fiscal nasceu com 40 descobertas. Citar num
#: comentário enganaria o contador — `conferir_telas` monta o builder e prova que a tela
#: existe e não é casca.
TELAS_DA_FRENTE = (
    "produtos-fiscais",
    "produto-fiscal-novo",
    "produto-tributacao",
    "ncm-consulta",
    "ncm-sugerir",
    "ncm-aplicar",
    "produto-tributacao-lote",
)
MODULO_DA_FRENTE = "fiscal"

sys.path.insert(0, "/app")

FIX = "FIXTURE DGX Z1"


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(
        text(
            "DELETE FROM fin_produto_tributacao WHERE produto_id IN (SELECT id FROM fin_produtos WHERE descricao LIKE :f)"
        ),
        {"f": f"{FIX}%"},
    )
    await db.execute(text("DELETE FROM fin_produtos WHERE descricao LIKE :f"), {"f": f"{FIX}%"})
    await db.commit()


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from fastapi import HTTPException
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.financial.services import produto_fiscal as pf

    falhas: list[str] = []
    async with async_session_factory() as db:
        from _telas import conferir_telas  # noqa: PLC0415 — irmão em scripts/orq

        falhas.extend(await conferir_telas(db, MODULO_DA_FRENTE, TELAS_DA_FRENTE))
        await pf._ensure(db)
        await _limpar(db)
        await pf.semear(db)

        # ------------------------------------------------------------------ (a)
        maus = (
            await db.execute(
                text(
                    """
                    SELECT p.codigo, coalesce(p.ncm, '(nulo)')
                      FROM fin_produtos p
                     WHERE p.ativo IS true
                       AND (p.ncm !~ '^[0-9]{8}$'
                            OR NOT EXISTS (
                                SELECT 1 FROM ncms n
                                 WHERE n.codigo = p.ncm
                                   AND n.active IS NOT false
                                   AND (n.valid_from IS NULL OR n.valid_from <= current_date)
                                   AND (n.valid_until IS NULL OR n.valid_until >= current_date)))
                     ORDER BY p.codigo LIMIT 20
                    """
                )
            )
        ).fetchall()
        if maus:
            falhas.append(
                f"(a) {len(maus)} produto(s) ATIVOS com NCM que não existe na tabela oficial: "
                + ", ".join(f"{c}→{n}" for c, n in maus[:8])
            )
        total_ncms = (await db.execute(text("SELECT count(*) FROM ncms"))).scalar() or 0
        if total_ncms < 1000:
            falhas.append(f"(a) tabela oficial de NCM com {total_ncms} linha(s) — validar contra ela seria teatro")

        # ------------------------------------------------------------------ (c)
        cnpjs = [r[0] for r in (await db.execute(text("SELECT cnpj FROM empresas WHERE cnpj IS NOT NULL"))).fetchall()]
        n_prod = (await db.execute(text("SELECT count(*) FROM fin_produtos"))).scalar() or 0
        for cnpj in cnpjs:
            n = (
                await db.execute(
                    text("SELECT count(*) FROM fin_produto_tributacao WHERE empresa_cnpj = :c"), {"c": cnpj}
                )
            ).scalar() or 0
            if n != n_prod:
                falhas.append(f"(c) {cnpj}: {n} tributação(ões) para {n_prod} produto(s)")
        sem_regra = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fin_produto_tributacao WHERE origem_regra IS NULL OR btrim(origem_regra) = ''"
                )
            )
        ).scalar() or 0
        if sem_regra:
            falhas.append(f"(c) {sem_regra} linha(s) de tributação sem `origem_regra` — CST sem fundamento é chute")

        # ------------------------------------------------------------------ (d)
        das_compras = {
            r[0]
            for r in (
                await db.execute(
                    text("SELECT DISTINCT ncm FROM nfe_compras_estoque WHERE ncm IS NOT NULL AND ncm <> ''")
                )
            ).fetchall()
        }
        do_seed = {
            r[0]
            for r in (
                await db.execute(text("SELECT DISTINCT ncm FROM fin_produtos WHERE origem_cadastro = 'nfe_entrada'"))
            ).fetchall()
        }
        if das_compras != do_seed:
            falhas.append(
                f"(d) seed ≠ compras: {len(das_compras)} NCM(s) nas compras, {len(do_seed)} no seed; "
                f"faltando {sorted(das_compras - do_seed)[:6]}, sobrando {sorted(do_seed - das_compras)[:6]}"
            )

        # ------------------------------------------------------------------ (b)
        regimes = {
            r[0]: r[1]
            for r in (
                await db.execute(text("SELECT cnpj, regime_tributario FROM empresas WHERE cnpj IS NOT NULL"))
            ).fetchall()
        }
        prontos = 0
        for p in await pf.listar(db):
            for cnpj, e in (p.get("empresas") or {}).items():
                if not e.get("pronto"):
                    continue
                prontos += 1
                col_cst = "csosn" if regimes.get(cnpj) == "simples_nacional" else "cst_icms"
                row = (
                    await db.execute(
                        text(
                            f"""
                            SELECT p.cfop_padrao_dentro_uf, p.cfop_padrao_fora_uf, p.unidade_comercial,
                                   p.unidade_tributavel, p.ean, p.origem, p.ativo, t.{col_cst},
                                   t.cst_pis, t.cst_cofins
                              FROM fin_produtos p
                              JOIN fin_produto_tributacao t ON t.produto_id = p.id AND t.empresa_cnpj = :c
                             WHERE p.id = :i
                            """
                        ),
                        {"c": cnpj, "i": p["id"]},
                    )
                ).fetchall()
                if not row:
                    falhas.append(f"(b) {p['codigo']}/{cnpj}: «pronto» sem linha de tributação")
                    continue
                r = row[0]
                vazios = [
                    nome
                    for nome, val in zip(
                        (
                            "CFOP dentro da UF",
                            "CFOP fora da UF",
                            "unidade comercial",
                            "unidade tributável",
                            "GTIN",
                            "origem",
                            "ativo",
                            col_cst.upper(),
                            "CST PIS",
                            "CST COFINS",
                        ),
                        r,
                        strict=False,
                    )
                    if val is None or str(val).strip() in ("", "False")
                ]
                if vazios:
                    falhas.append(
                        f"(b) {p['codigo']}/{cnpj}: marcado «pronto para emitir» faltando {', '.join(vazios)}"
                    )

        # ------------------------------------------------------------------ (e) e (f)
        async def _recusa(rotulo: str, coro) -> None:
            try:
                await coro
            except HTTPException as exc:
                if exc.status_code != 422:
                    falhas.append(f"(e) {rotulo}: recusou com {exc.status_code}, esperado 422")
                return
            except Exception as exc:  # noqa: BLE001
                falhas.append(f"(e) {rotulo}: levantou {type(exc).__name__} em vez de 422 — {exc}")
                return
            falhas.append(f"(e) {rotulo}: ACEITOU — a nota sairia e a SEFAZ rejeitaria")

        await _recusa(
            "NCM de 7 dígitos",
            pf.salvar_produto(db, {"descricao": f"{FIX} sete digitos", "ncm": "6403919"}, FIX),
        )
        await db.rollback()
        await _recusa(
            "NCM inexistente na nomenclatura (65119000)",
            pf.salvar_produto(db, {"descricao": f"{FIX} capacete", "ncm": "65119000"}, FIX),
        )
        await db.rollback()
        await _recusa(
            "CFOP 6xxx no campo «dentro do estado»",
            pf.salvar_produto(
                db,
                {"descricao": f"{FIX} cfop trocado", "ncm": "64039190", "cfop_padrao_dentro_uf": "6102"},
                FIX,
            ),
        )
        await db.rollback()

        # produto válido, sem CFOP: NÃO pode aparecer pronto em empresa nenhuma
        novo = await pf.salvar_produto(db, {"descricao": f"{FIX} bota", "ncm": "64039190"}, FIX)
        achado = next((x for x in await pf.listar(db) if x["id"] == novo["id"]), None)
        if not achado:
            falhas.append("(e) produto da fixture não voltou em listar()")
        else:
            if achado["pronto"]:
                falhas.append("(e) produto SEM CFOP e SEM CST apareceu como «pronto para emitir»")
            if not achado["faltas_produto"]:
                falhas.append("(e) produto sem CFOP não listou nenhuma falta")
            for cnpj in cnpjs:
                if not (achado["empresas"].get(cnpj) or {}).get("faltas"):
                    falhas.append(f"(e) {cnpj}: produto novo sem CST não acusou falta de tributação")

        # o seed do produto novo criou tributação nas DUAS empresas
        n_t = (
            await db.execute(
                text("SELECT count(*) FROM fin_produto_tributacao WHERE produto_id = :i"), {"i": novo["id"]}
            )
        ).scalar() or 0
        if n_t != len(cnpjs):
            falhas.append(f"(c) produto novo nasceu com {n_t} tributação(ões), esperado {len(cnpjs)}")

        # ativar produto inativo com NCM inexistente tem que dar 422
        inativo = (
            await db.execute(text("SELECT id FROM fin_produtos WHERE ativo IS false ORDER BY id LIMIT 1"))
        ).scalar()
        if inativo:
            await _recusa(
                "ativar produto com NCM inexistente", pf.salvar_produto(db, {"id": inativo, "ativo": "1"}, FIX)
            )
            await db.rollback()

        # ------------------------------------------------------------------ (h)
        cheia = await pf.salvar_produto(
            db,
            {
                "codigo": f"{FIX}-COMPLETA",
                "descricao": f"{FIX} produto completo",
                "ncm": "64039190",
                "origem": "0",
                "unidade_comercial": "PR",
                "unidade_tributavel": "PR",
                "ean": "SEM GTIN",
                "cfop_padrao_dentro_uf": "5102",
                "cfop_padrao_fora_uf": "6102",
            },
            FIX,
        )
        for cnpj, regime in regimes.items():
            campos = {"cst_pis": "01", "cst_cofins": "01"}
            campos["csosn" if regime == "simples_nacional" else "cst_icms"] = (
                "102" if regime == "simples_nacional" else "00"
            )
            await pf.salvar_tributacao(
                db, {"produto_id": cheia["id"], "empresa_cnpj": cnpj, **campos, "origem_regra": f"{FIX} — teste"}, FIX
            )
        achado = next((x for x in await pf.listar(db) if x["id"] == cheia["id"]), None)
        if not achado or not achado["pronto"]:
            falhas.append(
                "(h) produto com TODOS os campos e CST nas duas empresas NÃO ficou «pronto para emitir» — "
                "a régua estaria sempre dizendo não, e (b) seria verde de graça"
            )
        else:
            prontos += sum(1 for e in achado["empresas"].values() if e["pronto"])
        await pf.salvar_produto(db, {"id": cheia["id"], "cfop_padrao_fora_uf": ""}, FIX)
        de_novo = next((x for x in await pf.listar(db) if x["id"] == cheia["id"]), None)
        if de_novo and de_novo["pronto"]:
            falhas.append("(h) produto seguiu «pronto» depois de perder o CFOP para fora do estado")

        # ------------------------------------------------------------------ (i)
        itens = (
            await db.execute(
                text(
                    "SELECT item_code, descricao, ncm FROM nfe_compras_estoque "
                    "WHERE ncm IS NOT NULL AND ncm <> '' AND descricao IS NOT NULL"
                )
            )
        ).fetchall()
        acertos = 0
        sem_fonte = 0
        sem_candidato = 0
        for item_code, desc, ncm in itens:
            cands = await pf.sugerir_ncm(db, desc, 5, ignorar_codigos={item_code})
            if not cands:
                sem_candidato += 1
                continue
            if any(not c.get("fonte") or not str(c.get("por_que") or "").strip() for c in cands):
                sem_fonte += 1
            if any(c["ncm"] == ncm for c in cands):
                acertos += 1
        taxa = (acertos / len(itens)) if itens else 0.0
        if sem_fonte:
            falhas.append(f"(i) {sem_fonte} descrição(ões) geraram candidato SEM fonte declarada")
        if taxa < 0.55:
            falhas.append(
                f"(i) sugestão pela descrição acertou em {acertos}/{len(itens)} ({taxa:.0%}) dos itens com NCM "
                "conhecido — abaixo da linha de base medida em 24/09/2026 (61%); a ordem A→B→C regrediu"
            )

        # ------------------------------------------------------------------ (g)
        import inspect

        from modules.operacional.controllers.redesign_builders import fiscal as _fiscal

        fonte = inspect.getsource(_fiscal)
        if "_dgx_z1_produto_fiscal" not in fonte:
            falhas.append("(g) fiscal.py não importa a frente Z1 — tela sem porta não existe")
        if "_telas_z1" not in fonte and "telas_z1" not in fonte:
            falhas.append("(g) fiscal.py não chama telas() da Z1")
        if not any(i.get("id") == "produtos-fiscais" for i in getattr(_fiscal, "EXTRA_MENU", [])):
            falhas.append("(g) «produtos-fiscais» não está no EXTRA_MENU do fiscal — sem aba")

        await _limpar(db)
        res = await pf.resumo(db)
        restou = (
            await db.execute(text("SELECT count(*) FROM fin_produtos WHERE descricao LIKE :f"), {"f": f"{FIX}%"})
        ).scalar() or 0
        if restou:
            falhas.append(f"(e) {restou} fixture(s) '{FIX}' não foram apagadas")

    print(
        f"{res['ncm_compras']} NCM(s) distintos nas compras · {res['ncm_compras_oficiais']} existem na tabela "
        f"oficial ({res['ncms_carregados']} códigos carregados) · {res['produtos']} produto(s) cadastrados, "
        f"{res['ativos']} ativo(s) · prontos para emitir nas DUAS empresas: {res['prontos']} · "
        + " · ".join(f"{c}: {n} pronto(s)" for c, n in res["prontos_por_empresa"].items())
        + f" · pares (produto, empresa) declarados prontos e reconferidos por SQL: {prontos}"
        + f" · sugestão de NCM pela descrição: {acertos}/{len(itens)} ({taxa:.0%}) com o NCM certo entre os 5 "
        f"primeiros (meta pedida 70%, teto documental 89/147 = 61%), {sem_candidato} sem candidato nenhum"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no cadastro fiscal de produto")
    print(
        "OK cadastro fiscal: todo produto ativo tem NCM que EXISTE na nomenclatura vigente, ninguém é «pronto "
        "para emitir» sem CFOP/CST/unidade, as duas empresas têm tributação com origem_regra, o seed reproduz "
        "exatamente os NCMs das compras e NCM/CFOP inválidos são recusados com 422"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
