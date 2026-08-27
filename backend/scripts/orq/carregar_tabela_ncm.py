#!/usr/bin/env python3
"""Carrega a tabela OFICIAL de NCM no `ncms` — que existia com esquema rico e ZERO linha.

Contexto (27/08/2026): o Jordan importou 854 produtos do Bling e 736 estão SEM NCM. Ele
perguntou se dava para puxar da SEFAZ. Dá — em parte, e é importante ser exato sobre qual
parte:

  - A SEFAZ NÃO classifica produto. Não existe serviço que receba "PARAFUSO AA CABEÇA
    PANELA" e devolva o NCM. Classificar é responsabilidade do contribuinte, e NCM errado
    é multa e glosa de crédito.
  - As NOTAS DE ENTRADA dos fornecedores dele trazem NCM por item, e isso é documento
    fiscal, não palpite. Medido: 51 XMLs legíveis → 209 itens, todos com NCM. Mas só ~14
    casam com o catálogo do Bling (ele compra bota e hipoclorito; o Bling é eletrônica),
    e 1 em 6 do que casou estava ERRADO ("cabo de rede" ~ "testador de cabo de rede").
  - O que existe de oficial e completo é a TABELA da nomenclatura. É ela que este script
    carrega, e é ela que transforma "classificar" de adivinhação em BUSCA.

⭐ A DESCRIÇÃO OFICIAL É HIERÁRQUICA e sozinha não serve. O código 8525.60.20 traz apenas
"De televisão, de frequência superior a 7 GHz"; milhares de itens são literalmente
"- Outros". Sem remontar a cadeia capítulo → posição → subposição → item, uma busca por
"câmera" não acha nada. Por isso `descricao_resumida` guarda o CAMINHO COMPLETO — é ele
que a busca lê.

Fonte: Portal Único Siscomex, endpoint público da nomenclatura (segue redirect 307).
O JSON traz o ato e a vigência; ambos vão para o relatório, porque tabela fiscal sem data
de vigência é número sem procedência.

    curl -sSL -o /tmp/ncm.json \\
      'https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json'
    docker cp /tmp/ncm.json conecta-pro-backend:/tmp/ncm.json
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/carregar_tabela_ncm.py /tmp/ncm.json --gravar
"""
from __future__ import annotations

import asyncio
import json
import sys
import re
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, "/app")


#: A publicação oficial traz HTML no meio da descrição ("<i>Gallus domesticus</i>").
_TAG = re.compile(r"<[^>]+>")


def _texto(s: str | None) -> str:
    return _TAG.sub("", str(s or "")).strip().lstrip("- ").strip()


def _so_digitos(c: str) -> str:
    return "".join(ch for ch in str(c or "") if ch.isdigit())


def _data(s: str | None) -> date | None:
    """'31/12/9999' → None (sem fim). Data inválida → None, nunca hoje."""
    t = str(s or "").strip()
    if not t or t.startswith("31/12/9999"):
        return None
    try:
        return datetime.strptime(t, "%d/%m/%Y").date()
    except ValueError:
        return None


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gravar = "--gravar" in sys.argv
    if not args:
        print("  uso: carregar_tabela_ncm.py <ncm.json> [--gravar]")
        return 2
    caminho = Path(args[0])
    if not caminho.exists():
        print(f"  arquivo não encontrado: {caminho}")
        return 2

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    vigencia = bruto.get("Data_Ultima_Atualizacao_NCM") or "(sem data no arquivo)"
    ato = bruto.get("Ato") or "(sem ato no arquivo)"
    linhas = bruto.get("Nomenclaturas") or []
    if not linhas:
        print("  RECUSADO: arquivo sem `Nomenclaturas` — não é a tabela do Siscomex.")
        return 1

    # Índice por código sem pontos, para remontar a cadeia por PREFIXO. A nomenclatura é
    # posicional: 8525 é pai de 852560, que é pai de 85256020.
    por_codigo = {_so_digitos(x.get("Codigo")): _texto(x.get("Descricao"))
                  for x in linhas}

    def cadeia(cod: str) -> str:
        partes = [por_codigo[p] for p in (cod[:2], cod[:4], cod[:6], cod)
                  if p in por_codigo and por_codigo[p]]
        limpo = list(partes)   # já vêm sem travessão e sem HTML de `_texto`
        vistos, saida = set(), []
        for p in limpo:
            if p.lower() not in vistos:
                vistos.add(p.lower())
                saida.append(p)
        return " › ".join(saida)

    itens, hoje = [], date.today()
    encerrados = 0
    for x in linhas:
        cod = _so_digitos(x.get("Codigo"))
        if len(cod) != 8:          # só o nível de item vira produto
            continue
        fim = _data(x.get("Data_Fim"))
        if fim and fim < hoje:     # NCM já encerrado não entra: classificar por ele erra
            encerrados += 1
            continue
        itens.append({
            "codigo": cod,
            # A CADEIA vai em `descricao` (text, sem limite) porque é ela que a busca
            # lê e ela passa de 200 chars em 7.255 dos 10.515 códigos — a coluna
            # `descricao_resumida` é varchar(200) e guarda o texto PRÓPRIO do item.
            "descricao": cadeia(cod),
            "resumida": _texto(x.get("Descricao"))[:200],
            "capitulo": cod[:2], "posicao": cod[:4], "subposicao": cod[:6],
            "ini": _data(x.get("Data_Inicio")), "fim": fim,
        })

    print(f"  fonte: {caminho.name} · {ato} · {vigencia}")
    print(f"  linhas no arquivo: {len(linhas)} · NCM de 8 dígitos VIGENTES: {len(itens)}"
          f" (encerrados, fora: {encerrados})")
    print("  ── cadeia remontada (amostra) ──")
    for i in itens[:3]:
        print(f"      {i['codigo']}  {i['descricao'][:96]}")
    alvo = [i for i in itens if i["posicao"] == "8525"][:2]
    for i in alvo:
        print(f"      {i['codigo']}  {i['descricao'][-96:]}")

    async with async_session_factory() as db:
        atual = (await db.execute(text("SELECT count(*) FROM ncms"))).scalar()
        print(f"\n  `ncms` hoje: {atual} linha(s)")
        if not gravar:
            print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
            return 0

        # Recarga completa: a tabela é um retrato do ato vigente, não um acumulado.
        # Substituir por inteiro é o que mantém o retrato coerente com a data publicada.
        await db.execute(text("DELETE FROM ncms"))
        for i in itens:
            await db.execute(text("""
                INSERT INTO ncms (id, codigo, descricao, descricao_resumida,
                                  capitulo, posicao, subposicao,
                                  valid_from, valid_until, active, created_at, updated_at)
                VALUES (gen_random_uuid(), :codigo, :descricao, :resumida,
                        :capitulo, :posicao, :subposicao,
                        :ini, :fim, true, now(), now())
            """), i)
        await db.commit()
        n = (await db.execute(text("SELECT count(*) FROM ncms"))).scalar()
        print(f"\n  GRAVADO: {n} NCM vigentes ({ato}, {vigencia})")
        print("  ⚠️ As colunas de tributação (IPI, PIS/COFINS, CEST, ZFM) continuam "
              "VAZIAS: a nomenclatura não as traz. Elas vêm da TIPI e das regras da Zona "
              "Franca, que são outra fonte — e chutar alíquota é pior que não ter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
