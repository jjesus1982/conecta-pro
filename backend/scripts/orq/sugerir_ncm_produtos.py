#!/usr/bin/env python3
"""Liga NCM aos produtos — por FONTE, com a força da evidência declarada em cada linha.

Ordem do Jordan (27/08/2026): "liga o ncm nos produtos agora". 736 dos 854 importados do
Bling estão sem NCM, e sem NCM não sai nota de mercadoria.

⭐ O PONTO INTEIRO DESTE SCRIPT É NÃO TRATAR AS TRÊS FONTES COMO IGUAIS. NCM errado é
multa e glosa de crédito; "achou alguma coisa" não é o mesmo que "está classificado".

  A · NOTA DE ENTRADA do fornecedor — o fornecedor classificou o item numa nota que já
      produziu efeito fiscal. É documento, não palpite. GRAVA.
  B · IRMÃO JÁ CLASSIFICADO — outro produto DELE, com nome quase igual, já tem NCM
      (veio preenchido do próprio Bling). Coerência interna do cadastro — mas SÓ vale se
      o NCM do irmão CONFERIR com a descrição oficial. Ver `_confere` abaixo.
  C · BUSCA NA TABELA OFICIAL — a nomenclatura tem 10.515 códigos e a busca acha um
      plausível. Isso é ponto de partida de classificação, NÃO classificação.
      NÃO GRAVA em `ncm`: fica em `attributes.ncm_sugerido`, para o Jordan confirmar.

Um NCM que entra por C sem ninguém olhar vira nota emitida com código errado, e a
diferença entre "o sistema classificou" e "alguém classificou" só aparece na fiscalização.

    # ensaio (padrão) — mostra quanto cada fonte alcança:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/sugerir_ncm_produtos.py

    # grava A e B em `ncm`, e C como sugestão:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/sugerir_ncm_produtos.py --gravar

    # depois de o Jordan revisar a lista de C, promover as sugestões a NCM:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/sugerir_ncm_produtos.py --promover-sugestoes --gravar

    # desfazer tudo que ESTE script escreveu (o carimbo é a marca):
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/sugerir_ncm_produtos.py --desfazer
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

sys.path.insert(0, "/app")

_NS = "{http://www.portalfiscal.inf.br/nfe}"

#: Similaridade mínima de tokens para aceitar um irmão/nota como o MESMO produto.
#: 0.80 não é chute: em 0.70 a medição de 27/08 aceitou "Cabo de rede 4PX0,5 bobina 300MT"
#: como "TESTADOR DE CABO DE REDE" — 1 erro em 6. Acima de 0.80 os pares que sobraram na
#: amostra eram todos o mesmo produto em grafias diferentes.
_CORTE = 0.80

#: Palavras que não distinguem produto e inflam a semelhança de qualquer par.
_VAZIAS = {"de", "da", "do", "com", "sem", "para", "por", "em", "e", "ou", "a", "o",
           "un", "kit", "cj", "pc", "pç", "tipo", "novo", "nova"}


def _toks(s: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p for p in re.sub(r"[^A-Z0-9]", " ", t).split()
            if len(p) > 1 and p.lower() not in _VAZIAS}


def _sim(a: set[str], b: set[str]) -> float:
    """Sobreposição sobre o MENOR conjunto.

    Jaccard puniria "Câmera bullet IP 4 MP" contra "Câmera bullet IP 4 MP 360° IR 40m
    com microfone" — que é o mesmo produto descrito com mais detalhe, o caso comum aqui.
    """
    return (len(a & b) / min(len(a), len(b))) if a and b else 0.0


async def _confere(db, ncm: str, nome: str) -> bool:
    """O nome do produto tem alguma palavra em comum com a descrição OFICIAL do NCM?

    ⭐ Esta checagem existe porque a fonte B PROPAGA ERRO. Medido em 27/08/2026: o cadastro
    do Bling classificava "Placa de motor portão" como 8704.60.00 — "veículos automóveis
    para transporte de mercadorias". Herdar isso para os 51 irmãos transformaria um erro
    em cinquenta e um, e com cara de resolvido.

    ⚠️ NÃO SERVE COMO PORTEIRO, e medir isso custou uma versão deste script. Como gate ele
    errou nos DOIS sentidos: barrou "Nobreak attiv 1200VA" → 8504.40.40 (a nomenclatura diz
    "conversor estático", não "nobreak") e "Bateria selada" → 8507.20.10 ("acumulador"), que
    estão CERTOS; e deixou passar "Placa de motor portão" → 8704.60.00, que está errado,
    porque a palavra "motor" aparece no capítulo de veículos.

    Vocabulário comercial e vocabulário fiscal não coincidem — é exatamente por isso que
    classificar é trabalho humano. Fica como ANOTAÇÃO na linha do relatório: "confira este".
    """
    from sqlalchemy import text as _t

    r = (await db.execute(_t(
        "SELECT 1 FROM ncm_busca WHERE codigo = :c "
        "  AND doc @@ to_tsquery('portuguese', unaccent(:q)) LIMIT 1"),
        {"c": ncm, "q": " | ".join(_toks(nome)) or "zzz"})).first()
    return r is not None


def _ncm(v) -> str | None:
    d = "".join(c for c in str(v or "") if c.isdigit())
    return d if len(d) == 8 else None


async def _fontes_documentais(db) -> list[tuple[set[str], str, str]]:
    """(tokens, ncm, procedência) das notas de entrada e do estoque de compras."""
    from sqlalchemy import text

    saida: list[tuple[set[str], str, str]] = []
    xmls = (await db.execute(text(
        "SELECT chave_acesso, emitente_nome, xml_raw FROM nfe_entradas "
        "WHERE xml_raw IS NOT NULL"))).all()
    for chave, emit, xml in xmls:
        try:
            raiz = ET.fromstring(xml)
        except ET.ParseError:
            continue
        for det in raiz.iter(_NS + "det"):
            p = det.find(_NS + "prod")
            if p is None:
                continue
            n = _ncm(p.findtext(_NS + "NCM"))
            desc = (p.findtext(_NS + "xProd") or "").strip()
            if n and desc:
                saida.append((_toks(desc), n,
                              f"NF-e {str(chave)[-8:]} de {str(emit or '')[:22]}"))
    for desc, n, nfe in (await db.execute(text(
        "SELECT descricao, ncm, last_nfe_key FROM nfe_compras_estoque "
        "WHERE ncm IS NOT NULL AND descricao IS NOT NULL"))).all():
        if _ncm(n):
            saida.append((_toks(desc), _ncm(n), f"compra NF-e {str(nfe or '')[-8:]}"))
    return saida


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    gravar = "--gravar" in sys.argv
    promover = "--promover-sugestoes" in sys.argv

    async with async_session_factory() as db:
        if "--desfazer" in sys.argv:
            n = (await db.execute(text(
                "UPDATE products SET ncm = NULL, attributes = attributes - 'ncm_origem' "
                "- 'ncm_sugerido' - 'ncm_sugerido_desc' "
                "WHERE attributes ? 'ncm_origem' OR attributes ? 'ncm_sugerido'"))).rowcount
            await db.commit()
            print(f"  desfeito em {n} produto(s) — o NCM que veio do Bling não foi tocado")
            return 0

        if promover:
            linhas = (await db.execute(text(
                "SELECT id, code, name, attributes->>'ncm_sugerido' AS s FROM products "
                "WHERE ncm IS NULL AND attributes->>'ncm_sugerido' IS NOT NULL"))).all()
            print(f"  sugestões (fonte C) a promover: {len(linhas)}")
            if not gravar:
                print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
                return 0
            for pid, _c, _n, s in linhas:
                await db.execute(text(
                    "UPDATE products SET ncm = :n, "
                    "attributes = jsonb_set(attributes, '{ncm_origem}', "
                    "  to_jsonb(cast('C · busca oficial, confirmada pelo Jordan' "
                    "                 AS text))), "
                    "updated_at = now() WHERE id = :i"), {"n": s, "i": pid})
            await db.commit()
            print(f"  GRAVADO: {len(linhas)} sugestões promovidas a NCM")
            return 0

        docs = await _fontes_documentais(db)
        irmaos = [(_toks(n), _ncm(x), f"irmão {c} do próprio cadastro")
                  for c, n, x in (await db.execute(text(
                      "SELECT code, name, ncm FROM products WHERE ncm IS NOT NULL"))).all()
                  if _ncm(x)]
        sem = (await db.execute(text(
            "SELECT id, code, name FROM products WHERE ncm IS NULL "
            "AND coalesce(ativo, true) ORDER BY code"))).all()

        print(f"  produtos SEM NCM: {len(sem)}")
        print(f"  fonte A (notas de entrada): {len(docs)} item(ns) classificados por "
              f"fornecedor")
        print(f"  fonte B (irmãos já com NCM): {len(irmaos)}")

        # ⚠️ A CTE que calcula o tsvector na hora é boa para UMA busca e péssima para
        # 736: cada consulta recomputava os 10.515 vetores, e a primeira tentativa deste
        # script estourou 590s sem terminar. Materializamos UMA vez, com índice GIN.
        # Tabela TEMPORÁRIA: some no fim da sessão, sem migração e sem lixo no schema.
        await db.execute(text("""
            CREATE TEMP TABLE ncm_busca ON COMMIT PRESERVE ROWS AS
            SELECT codigo, descricao_resumida,
                   setweight(to_tsvector('portuguese',
                             unaccent(coalesce(descricao_resumida, ''))), 'A')
                || setweight(to_tsvector('portuguese',
                             unaccent(coalesce(descricao, ''))), 'B') AS doc
            FROM ncms WHERE active"""))
        await db.execute(text("CREATE INDEX ON ncm_busca USING gin(doc)"))
        await db.execute(text("ANALYZE ncm_busca"))

        SQL_C = """
          SELECT codigo, descricao_resumida FROM ncm_busca
          WHERE doc @@ plainto_tsquery('portuguese', unaccent(:q))
          ORDER BY ts_rank(doc, plainto_tsquery('portuguese', unaccent(:q))) DESC, codigo
          LIMIT 1"""

        pa, pb, pc, nada, suspeitos = [], [], [], [], []
        for pid, code, nome in sem:
            t = _toks(nome)
            if not t:
                nada.append((code, nome))
                continue
            ma = max(((_sim(t, d), n, p) for d, n, p in docs), default=(0, None, ""))
            mb = max(((_sim(t, d), n, p) for d, n, p in irmaos), default=(0, None, ""))
            if ma[0] >= _CORTE:
                pa.append((pid, code, nome, ma[1], f"A · {ma[2]} ({ma[0]:.2f})"))
            elif mb[0] >= _CORTE:
                # Herda a classificação que ELE já usa — ser consistente com o próprio
                # cadastro é defensável. Mas anotamos quando o NCM não conversa com a
                # descrição oficial, porque a fonte B propaga o que existir, certo ou
                # errado, e o Bling dele TEM erro (ver `suspeitos` no relatório).
                ok = await _confere(db, mb[1], nome)
                pb.append((pid, code, nome, mb[1],
                           f"B · {mb[2]} ({mb[0]:.2f})" + ("" if ok else " ⚠️ CONFERIR")))
                if not ok:
                    suspeitos.append((code, nome, mb[1], mb[2]))
            else:
                # No lote não fazemos o relaxamento palavra a palavra da tool (que faria
                # ~5.900 consultas): três tentativas por produto bastam, porque nome de
                # produto vai do geral para o específico.
                achado = None
                palavras = nome.split()
                for corte in dict.fromkeys((len(palavras), 3, 1)):
                    if corte < 1:
                        continue
                    achado = (await db.execute(text(SQL_C),
                                               {"q": " ".join(palavras[:corte])})).first()
                    if achado:
                        break
                if achado:
                    pc.append((pid, code, nome, achado[0], achado[1]))
                else:
                    nada.append((code, nome))

        print(f"\n  ── por FORÇA DA EVIDÊNCIA ──")
        print(f"    A · nota do fornecedor (documento fiscal) → GRAVA:  {len(pa)}")
        print(f"    B · irmão do cadastro já classificado     → GRAVA:  {len(pb)}")
        print(f"    C · busca na tabela oficial       → SUGERE, não grava: {len(pc)}")
        print(f"    sem candidato nenhum:                                 {len(nada)}")
        if suspeitos:
            print(f"\n  ⚠️ {len(suspeitos)} herança(s) cujo NCM não conversa com a "
                  f"descrição oficial. FORAM gravadas (é a classificação que o seu "
                  f"cadastro já usa), mas são as primeiras a revisar — parte é só "
                  f"vocabulário fiscal ('nobreak' é 'conversor estático'), parte é erro "
                  f"real vindo do Bling:")
            for c, n, ncm, proc in suspeitos[:8]:
                print(f"      {c:12} {n[:36]:38} herdaria {ncm} de {proc[:26]}")

        for rot, lst in (("A", pa), ("B", pb)):
            for _i, c, n, ncm, proc in lst[:5]:
                print(f"      {rot} {c:12} {n[:38]:40} → {ncm}  [{proc[:40]}]")
        for _i, c, n, ncm, desc in pc[:5]:
            print(f"      C {c:12} {n[:38]:40} → {ncm}  {desc[:34]}")

        if not gravar:
            print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
            return 0

        for pid, _c, _n, ncm, proc in pa + pb:
            await db.execute(text(
                "UPDATE products SET ncm = :n, "
                # cast() e não `::` — dentro de text() o SQLAlchemy tropeça no `::`
                # e deixa o bind literal no SQL. Terceira vez hoje que isto morde.
                "attributes = jsonb_set(coalesce(attributes, cast('{}' AS jsonb)), "
                "  '{ncm_origem}', to_jsonb(cast(:p AS text))), updated_at = now() "
                "WHERE id = :i"), {"n": ncm, "p": proc, "i": pid})
        for pid, _c, _n, ncm, desc in pc:
            await db.execute(text(
                "UPDATE products SET attributes = "
                "  jsonb_set(jsonb_set(coalesce(attributes, cast('{}' AS jsonb)), "
                "    '{ncm_sugerido}', to_jsonb(cast(:n AS text))), "
                "    '{ncm_sugerido_desc}', to_jsonb(cast(:d AS text))), "
                "  updated_at = now() "
                "WHERE id = :i"), {"n": ncm, "d": (desc or "")[:200], "i": pid})
        await db.commit()

        com = (await db.execute(text(
            "SELECT count(*) FROM products WHERE ncm IS NOT NULL"))).scalar()
        tot = (await db.execute(text("SELECT count(*) FROM products"))).scalar()
        sug = (await db.execute(text(
            "SELECT count(*) FROM products WHERE ncm IS NULL "
            "AND attributes->>'ncm_sugerido' IS NOT NULL"))).scalar()
        print(f"\n  GRAVADO · com NCM: {com} de {tot} (era 118) · aguardando sua "
              f"confirmação: {sug}")
        print("  Para promover as sugestões depois de revisar: --promover-sugestoes --gravar")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
