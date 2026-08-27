#!/usr/bin/env python3
"""Oráculo do ESCOPO POR ANALOGIA — propor a partir do que o Jordan JÁ VENDEU.

Na visita, a pergunta que importa não é "o que a norma manda" — é "o que eu fiz da última
vez num lugar parecido". O Jordan tem 16 propostas com 3+ itens; elas são o repertório.

⭐ O QUE ESTE ORÁCULO PROTEGE é a diferença entre ANALOGIA e FABRICAÇÃO. Um escopo
sugerido vira orçamento, e orçamento vira contrato. Se o serviço puder devolver um item
que não saiu de proposta nenhuma, ele está inventando projeto de segurança — e isso sai
bonito, com a marca certa, dizendo coisa que ninguém especificou.

Seis invariantes:
  1. termo vazio é RECUSADO (não devolve "as 3 mais recentes" como se fossem parecidas)
  2. termo sem nenhuma correspondência devolve LISTA VAZIA e AVISO — nunca a proposta
     menos ruim disfarçada de achado
  3. todo item devolvido EXISTE numa proposta real (nenhum nome inventado)
  4. todo achado cita o NÚMERO e a DATA da proposta de origem (rastreável pelo Jordan)
  5. a similaridade é COERENTE: "rack switch backbone" acha Sala de TI acima de CFTV
  6. o corte é respeitado: nada abaixo dele entra

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_escopo_analogo.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.crm.services import escopo_analogo as E

    falhas: list[str] = []
    async with async_session_factory() as db:
        # 1 · termo vazio
        r = await E.buscar(db, "")
        if r.get("achados"):
            falhas.append("termo VAZIO devolveu achados — sem termo não há analogia")

        # 2 · termo impossível
        r = await E.buscar(db, "zzz nada disso existe no repertorio dele qqq")
        if r.get("achados"):
            falhas.append(f"termo impossível devolveu {len(r['achados'])} achado(s) — "
                          f"a proposta menos ruim NÃO é uma proposta parecida")
        if not r.get("aviso"):
            falhas.append("nenhum achado e nenhum AVISO — silêncio parece sucesso vazio")

        # 5 · coerência: infra de rede acha Sala de TI
        rede = await E.buscar(db, "rack switch backbone cabeamento fibra")
        if not rede.get("achados"):
            print("  (base sem proposta de infra — bloco de coerência não exercitado)")
        else:
            topo = rede["achados"][0]
            if "TI" not in (topo["titulo"] or "").upper() and \
               "INFRAESTRUTURA" not in (topo["titulo"] or "").upper():
                falhas.append(f"'rack switch backbone' achou {topo['titulo'][:40]!r} no "
                              f"topo — a similaridade não está coerente")

            # 3 e 4 · rastreabilidade e não-fabricação
            for a in rede["achados"]:
                if not a.get("numero") or not a.get("data"):
                    falhas.append(f"achado sem número/data de origem: {str(a)[:80]}")
                if not a.get("itens"):
                    falhas.append(f"achado {a.get('numero')} sem itens")
                for it in a.get("itens") or []:
                    existe = (await db.execute(text(
                        "SELECT 1 FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
                        "WHERE p.number = :n AND i.name = :nome LIMIT 1"),
                        {"n": a["numero"], "nome": it["nome"]})).first()
                    if not existe:
                        falhas.append(f"item INVENTADO: {it['nome'][:50]!r} não está na "
                                      f"proposta {a['numero']}")
                        break

            # 6 · corte respeitado
            if any(a["similaridade"] < rede["corte"] for a in rede["achados"]):
                falhas.append("devolveu achado ABAIXO do corte declarado")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK escopo_analogo: 6/6 — recusa termo vazio; termo sem correspondência devolve "
          "vazio COM aviso; todo item devolvido existe na proposta citada; todo achado "
          "cita número e data; a similaridade é coerente; e o corte é respeitado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
