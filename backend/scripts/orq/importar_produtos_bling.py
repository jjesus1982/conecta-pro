#!/usr/bin/env python3
"""Importa o cadastro de PRODUTOS do Bling para `products` — identidade fiscal, sem preço.

Decisão do Jordan (27/08/2026): "desconsidere os preços, são antigos; considere apenas os
produtos e as informações necessárias para uma futura emissão de nota fiscal; com relação
à grafia, padronize".

POR QUE `products` E NÃO `crm_products`:
  `products` já tem, nativos, TODOS os campos de NF-e — ncm, cest, origin, barcode,
  cfop_in/out, unit_of_measure, brand, code — e estava vazia. `crm_products` não tem
  nenhum deles. Importar lá exigiria migração para replicar uma tabela que já existe.
  Divisão que fica: `products` = IDENTIDADE FISCAL (Bling manda) ·
  `crm_products` = PREÇO PRATICADO (histórico das propostas dele).

O QUE ESTE SCRIPT NÃO FAZ:
  - não traz preço nenhum (`reference_price` fica NULL, não zero)
  - não inventa NCM, CEST, GTIN nem unidade: campo vazio no Bling entra VAZIO e é CONTADO
    no relatório. Emissão de NF-e com NCM chutado é multa, não conveniência.
  - não funde com `crm_products`: apenas RELATA quantos nomes casam.

Ensaio por padrão. `--gravar` escreve. `--desfazer` remove só o que veio do Bling.

    docker cp uploads/produtos_*.csv conecta-pro-backend:/tmp/bling.csv
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/importar_produtos_bling.py /tmp/bling.csv
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

_CARIMBO = "[Bling]"

#: Unidades do Bling vêm em 4 grafias para a mesma coisa (UN/Un/UNI, PÇ/Pç, MT/Mt).
#: Padroniza para a sigla curta em caixa alta. Vazio continua VAZIO — chutar "UN" num
#: produto vendido por metro erra a nota.
_UNIDADES = {
    "un": "UN", "uni": "UN", "und": "UN", "unid": "UN", "unidade": "UN",
    "pç": "PÇ", "pc": "PÇ", "peca": "PÇ", "peça": "PÇ",
    "mt": "MT", "m": "MT", "metro": "MT", "ml": "MT",
    "cx": "CX", "caixa": "CX", "kg": "KG", "l": "L", "lt": "L",
    "rl": "RL", "rolo": "RL", "par": "PAR", "kit": "KIT", "cj": "CJ", "jg": "JG",
}

#: "Tipo do item" do Bling → `products.product_type`. Vazio (736 de 857 no arquivo real)
#: fica como o default da coluna: material.
_TIPOS = {"mercadoria para revenda": "material", "serviços": "servico",
          "serviço": "servico", "matéria prima": "material", "produto": "material"}

#: Nome que denuncia produto de TESTE no cadastro real. Casa o nome INTEIRO ou o CÓDIGO —
#: nunca substring, senão "TERMINAL … SIMPLES" e "PLACA ADVERTENCIA FACE SIMPLES" caem
#: junto, e são produtos legítimos que ele vende.
_TESTE_NOME = frozenset({"produto simples", "produto teste", "produto teste 2",
                         "produto teste api", "teste", "item qa"})
_TESTE_CODIGO = ("TESTE", "PROD-SIMPLE", "PROD-TESTE", "ZZ")


def _lim(v) -> str:
    """Bling exporta com TAB grudado no código ('873\\t'). Tira tudo que é branco."""
    return str(v or "").strip().strip("\t\r\n ").strip()


def _e_teste(codigo: str, nome: str) -> bool:
    return nome.strip().lower() in _TESTE_NOME or codigo.upper().startswith(_TESTE_CODIGO)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.crm.services.nome_produto import normalizar_nome_produto

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gravar = "--gravar" in sys.argv

    async with async_session_factory() as db:
        if "--desfazer" in sys.argv:
            n = (await db.execute(text(
                "DELETE FROM products WHERE notes LIKE :c"),
                {"c": f"%{_CARIMBO}%"})).rowcount
            await db.commit()
            print(f"  desfeito: {n} produto(s) do Bling removido(s)")
            return 0

        if not args:
            print("  uso: importar_produtos_bling.py <arquivo.csv> [--gravar|--desfazer]")
            return 2
        caminho = Path(args[0])
        if not caminho.exists():
            print(f"  arquivo não encontrado: {caminho}")
            return 2

        raw = caminho.read_text(encoding="utf-8-sig", errors="replace")
        delim = csv.Sniffer().sniff(raw[:4000], delimiters=";,\t").delimiter
        linhas = list(csv.DictReader(io.StringIO(raw), delimiter=delim))

        need = {"Código", "Descrição"}
        if not need.issubset(set(linhas[0] if linhas else {})):
            print(f"  RECUSADO: faltam colunas {need - set(linhas[0] if linhas else {})}. "
                  f"Sem código e descrição não há produto — e adivinhar por posição "
                  f"erraria em silêncio.")
            return 1

        tenant = (await db.execute(text(
            "SELECT condominio_id::text FROM users WHERE email = :e"),
            {"e": "jjesus@conectamais.pro"})).scalar()
        if not tenant:
            print("  RECUSADO: não achei o condominio_id do dono — `products` exige.")
            return 1

        ja = {c.upper() for c in (await db.execute(text(
            "SELECT code FROM products WHERE code IS NOT NULL"))).scalars().all()}

        entram, testes, dup = [], [], 0
        vazios = {"NCM": 0, "CEST": 0, "GTIN/EAN": 0, "Unidade": 0, "Marca": 0,
                  "Tipo do item": 0}
        vistos: set[str] = set()

        for ln in linhas:
            cod, nome_bruto = _lim(ln.get("Código")), _lim(ln.get("Descrição"))
            if not cod or not nome_bruto:
                continue
            if _e_teste(cod, nome_bruto):
                testes.append((cod, nome_bruto))
                continue
            if cod.upper() in ja or cod.upper() in vistos:
                dup += 1
                continue
            vistos.add(cod.upper())

            for c in vazios:
                if not _lim(ln.get(c)):
                    vazios[c] += 1

            un = _lim(ln.get("Unidade"))
            entram.append({
                "code": cod,
                "name": normalizar_nome_produto(nome_bruto),
                "unit": _UNIDADES.get(un.lower(), un.upper() or None),
                "ncm": _lim(ln.get("NCM")).replace(".", "") or None,
                "cest": _lim(ln.get("CEST")) or None,
                "origin": _lim(ln.get("Origem")) or None,
                "barcode": _lim(ln.get("GTIN/EAN")) or None,
                "brand": normalizar_nome_produto(_lim(ln.get("Marca"))) or None,
                "ptype": _TIPOS.get(_lim(ln.get("Tipo do item")).lower(), "material"),
                "notes": " ".join(x for x in (_lim(ln.get("Descrição Complementar")),
                                              f"{_CARIMBO} cód. {cod}.") if x),
                "extra": json.dumps({
                    "bling_id": _lim(ln.get("ID")) or None,
                    "codigo_lista_servicos": _lim(ln.get("Código na Lista de Serviços")) or None,
                    "fornecedor": _lim(ln.get("Fornecedor")) or None,
                    "nome_original_bling": nome_bruto,
                }, ensure_ascii=False),
            })

        tot = len(entram)
        print(f"  arquivo: {caminho.name} · delimitador {delim!r} · {len(linhas)} linha(s)")
        print(f"  a IMPORTAR: {tot}   (duplicados/já existentes pulados: {dup})")
        if testes:
            print(f"\n  ⚠️  {len(testes)} produto(s) de TESTE no cadastro do Bling — não "
                  f"entram; apague lá também:")
            for c, n in testes:
                print(f"      {c:18} {n[:52]}")

        print(f"\n  ⛔ CAMPOS DE NF-e QUE O BLING NÃO TEM (entram VAZIOS, nunca chutados):")
        for c, q in sorted(vazios.items(), key=lambda x: -x[1]):
            falta = 100.0 * q / max(tot, 1)
            print(f"      {c:14} vazio em {q:4} de {tot}  ({falta:5.1f}%)")

        print("\n  ── como fica a grafia (amostra) ──")
        for p in entram[:6]:
            print(f"      {p['code']:8} {p['name'][:48]:50} un={p['unit'] or '—':4} "
                  f"ncm={p['ncm'] or '—'}")

        casam = (await db.execute(text(
            "SELECT count(*) FROM crm_products c WHERE lower(c.name) = ANY(:n)"),
            {"n": [p["name"].lower() for p in entram]})).scalar()
        print(f"\n  cruzamento: {casam} do catálogo de PREÇO PRATICADO (crm_products, "
              f"115) têm nome igual a um produto do Bling")

        if not gravar:
            print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
            return 0

        for p in entram:
            await db.execute(text("""
                INSERT INTO products (id, condominio_id, code, name, unit_of_measure,
                                      ncm, cest, origin, barcode, brand, product_type,
                                      status, notes, attributes, ativo,
                                      created_at, updated_at)
                VALUES (gen_random_uuid(), :tenant, :code, :name, :unit,
                        :ncm, :cest, :origin, :barcode, :brand, :ptype,
                        'ativo', :notes, cast(:extra as jsonb), true, now(), now())
            """), {**p, "tenant": tenant})
        await db.commit()

        n = (await db.execute(text("SELECT count(*) FROM products"))).scalar()
        com_ncm = (await db.execute(text(
            "SELECT count(*) FROM products WHERE ncm IS NOT NULL"))).scalar()
        print(f"\n  GRAVADO: {tot} produtos · tabela `products` agora com {n} "
              f"({com_ncm} com NCM — o resto precisa de NCM antes de virar NF-e)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
