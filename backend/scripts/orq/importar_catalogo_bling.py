#!/usr/bin/env python3
"""Importa o catálogo de produtos/serviços do BLING para `crm_products`.

O Bling é a fonte da verdade do catálogo do Jordan. O que já está em `crm_products` veio
do histórico de propostas dele (115 produtos, ver `semear_catalogo_de_propostas.py`) —
lastro real, mas incompleto e sem o código dele. Quando o arquivo do Bling chega, ele
manda: código, preço e unidade passam a ser os do Bling.

⭐ NÃO ADIVINHA COLUNA. O cabeçalho é casado por nome normalizado (sem acento, minúsculo)
contra uma lista de sinônimos. Coluna que não bate é IGNORADA e NOMEADA no relatório — a
alternativa (adivinhar pela posição) erra silencioso, e erro silencioso em preço vai para
o cliente.

Sempre ENSAIO por padrão. `--gravar` escreve. `--desfazer` remove só o que veio do Bling.

    docker cp ~/produtos_bling.xlsx conecta-pro-backend:/tmp/bling.xlsx
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/importar_catalogo_bling.py /tmp/bling.xlsx
    # conferir o relatório, e então:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/importar_catalogo_bling.py /tmp/bling.xlsx --gravar
"""
from __future__ import annotations

import asyncio
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, "/app")

_CARIMBO = "[importado do Bling]"
_CARIMBO_HISTORICO = "[catálogo semeado do histórico de propostas]"

#: cabeçalho normalizado → campo interno. Vários sinônimos porque o Bling mudou o nome
#: das colunas entre versões de exportação, e o arquivo do usuário pode vir de qualquer uma.
_COLUNAS: dict[str, tuple[str, ...]] = {
    "sku": ("codigo", "cod", "código", "sku", "codigo do produto", "codigo (sku)",
            "referencia", "referência"),
    "nome": ("descricao", "descrição", "nome", "produto", "descricao do produto",
             "nome do produto"),
    "preco": ("preco", "preço", "valor", "preco de venda", "preço de venda",
              "vlr venda", "preco venda"),
    "custo": ("preco de custo", "preço de custo", "custo", "preco custo"),
    "unidade": ("unidade", "un", "und", "unid"),
    "categoria": ("categoria", "grupo", "familia", "família", "categoria do produto"),
    "situacao": ("situacao", "situação", "status", "ativo"),
    "detalhe": ("descricao complementar", "descrição complementar", "observacoes",
                "observações", "detalhes"),
    "gtin": ("gtin", "ean", "gtin/ean", "codigo de barras", "código de barras"),
    "tipo": ("tipo", "tipo do produto", "tipo de produto"),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _num(v) -> float | None:
    """'1.234,56' | '1234.56' | 1234.56 → float. Vazio/lixo → None (nunca 0)."""
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    # Formato BR: separador de milhar '.' e decimal ','. Só troca quando a vírgula
    # aparece DEPOIS do último ponto — senão '1.234' viraria 1234,0 por acidente.
    if "," in t and (t.rfind(",") > t.rfind(".")):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _ler(caminho: Path) -> tuple[list[dict], list[str], list[str]]:
    """Devolve (linhas mapeadas, colunas reconhecidas, colunas ignoradas)."""
    import pandas as pd

    if caminho.suffix.lower() in (".xlsx", ".xlsm"):
        df = pd.read_excel(caminho, dtype=str)
    else:
        # sep=None + engine python deixa o pandas farejar ';' (padrão BR) vs ','.
        df = pd.read_csv(caminho, dtype=str, sep=None, engine="python",
                         encoding_errors="replace")

    mapa: dict[str, str] = {}
    for col in df.columns:
        n = _norm(col)
        for campo, nomes in _COLUNAS.items():
            if campo not in mapa and n in {_norm(x) for x in nomes}:
                mapa[campo] = col
                break

    ignoradas = [str(c) for c in df.columns if c not in mapa.values()]
    linhas = []
    for _, r in df.iterrows():
        linhas.append({k: (None if r[v] is None or str(r[v]) == "nan" else str(r[v]).strip())
                       for k, v in mapa.items()})
    return linhas, sorted(mapa), ignoradas


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gravar = "--gravar" in sys.argv
    desfazer = "--desfazer" in sys.argv

    async with async_session_factory() as db:
        if desfazer:
            n = (await db.execute(text(
                "DELETE FROM crm_products WHERE description LIKE :c"),
                {"c": f"%{_CARIMBO}%"})).rowcount
            await db.commit()
            print(f"  desfeito: {n} produto(s) do Bling removido(s); o que veio do "
                  f"histórico de propostas e o cadastrado à mão continuam lá")
            return 0

        if not args:
            print("  uso: importar_catalogo_bling.py <arquivo.xlsx|.csv> [--gravar]")
            return 2
        caminho = Path(args[0])
        if not caminho.exists():
            print(f"  arquivo não encontrado: {caminho}")
            return 2

        linhas, reconhecidas, ignoradas = _ler(caminho)
        if "nome" not in reconhecidas:
            print("  RECUSADO: não achei a coluna de DESCRIÇÃO/NOME do produto no "
                  f"cabeçalho. Colunas do arquivo: {ignoradas[:12]}\n"
                  "  Sem nome não dá para importar — e adivinhar pela posição erraria "
                  "em silêncio.")
            return 1

        print(f"  arquivo: {caminho.name} · {len(linhas)} linha(s)")
        print(f"  colunas reconhecidas: {', '.join(reconhecidas)}")
        if ignoradas:
            print(f"  colunas IGNORADAS ({len(ignoradas)}): {', '.join(ignoradas[:10])}"
                  f"{' …' if len(ignoradas) > 10 else ''}")

        atuais = {r["nome"].strip().lower(): r for r in (await db.execute(text(
            "SELECT name AS nome, sku, unit_price, description FROM crm_products"
        ))).mappings().all()}
        por_sku = {(r["sku"] or "").strip().upper(): r for r in atuais.values()}

        novos, atualiza, sem_preco, sem_nome, inativos = [], [], [], 0, 0
        for ln in linhas:
            nome = (ln.get("nome") or "").strip()
            if not nome:
                sem_nome += 1
                continue
            sit = _norm(ln.get("situacao") or "")
            if sit in ("inativo", "i", "0", "nao", "false", "excluido"):
                inativos += 1
                continue
            preco = _num(ln.get("preco"))
            if preco is None:
                sem_preco.append(nome)
            sku = (ln.get("sku") or "").strip().upper()
            achado = atuais.get(nome.lower()) or (por_sku.get(sku) if sku else None)
            (atualiza if achado else novos).append((ln, nome, sku, preco, achado))

        print(f"\n  a INSERIR:   {len(novos)}")
        print(f"  a ATUALIZAR: {len(atualiza)}  (já existiam — o Bling manda em código, "
              f"preço e unidade)")
        if inativos:
            print(f"  pulados por situação INATIVA: {inativos}")
        if sem_nome:
            print(f"  pulados sem nome: {sem_nome}")
        if sem_preco:
            print(f"  ⚠️  {len(sem_preco)} sem preço no arquivo — entram com preço VAZIO, "
                  f"não com zero: {', '.join(x[:26] for x in sem_preco[:4])}"
                  f"{' …' if len(sem_preco) > 4 else ''}")

        for ln, nome, sku, preco, _a in novos[:6]:
            print(f"      + {sku or '(sem código)':14} "
                  f"R$ {preco if preco is not None else float('nan'):>10,.2f}  {nome[:46]}")
        for ln, nome, sku, preco, a in atualiza[:6]:
            de = float(a["unit_price"] or 0)
            marca = " ←preço MUDA" if preco is not None and abs(de - preco) > 0.01 else ""
            print(f"      ~ {sku or a['sku']:14} R$ {de:>10,.2f} → "
                  f"{preco if preco is not None else de:>10,.2f}  {nome[:40]}{marca}")

        if not gravar:
            print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
            return 0

        from datetime import date
        hoje = f"{date.today():%d/%m/%Y}"
        for ln, nome, sku, preco, achado in novos:
            await db.execute(text("""
                INSERT INTO crm_products (id, sku, name, description, category, unit,
                                          unit_price, is_recurring, service_type,
                                          is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :sku, :name, :desc, :cat, :unit, :preco,
                        false, NULL, true, now(), now())
            """), {"sku": sku or None, "name": nome, "cat": ln.get("categoria"),
                   "unit": ln.get("unidade") or "un", "preco": preco,
                   "desc": f"{ln.get('detalhe') or ''} {_CARIMBO} em {hoje}.".strip()})

        for ln, nome, sku, preco, achado in atualiza:
            # A description ACUMULA os carimbos: o de origem no histórico não se perde
            # quando o Bling assume. Rastro que some é rastro que não serviu para nada.
            desc = (achado["description"] or "")
            if _CARIMBO not in desc:
                desc = f"{desc} {_CARIMBO} em {hoje}.".strip()
            await db.execute(text("""
                UPDATE crm_products
                   SET sku = coalesce(:sku, sku),
                       unit = coalesce(:unit, unit),
                       unit_price = coalesce(:preco, unit_price),
                       category = coalesce(:cat, category),
                       description = :desc,
                       updated_at = now()
                 WHERE lower(name) = lower(:name)
            """), {"sku": sku or None, "unit": ln.get("unidade"), "preco": preco,
                   "cat": ln.get("categoria"), "desc": desc, "name": nome})

        await db.commit()
        tot = (await db.execute(text("SELECT count(*) FROM crm_products"))).scalar()
        do_bling = (await db.execute(text(
            "SELECT count(*) FROM crm_products WHERE description LIKE :c"),
            {"c": f"%{_CARIMBO}%"})).scalar()
        so_historico = (await db.execute(text(
            "SELECT count(*) FROM crm_products WHERE description LIKE :h "
            "AND description NOT LIKE :c"),
            {"h": f"%{_CARIMBO_HISTORICO}%", "c": f"%{_CARIMBO}%"})).scalar()
        print(f"\n  GRAVADO · catálogo: {tot} produtos "
              f"({do_bling} tocados pelo Bling · {so_historico} só do histórico de "
              f"propostas, que o Bling não cobriu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
