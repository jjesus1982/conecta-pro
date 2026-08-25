#!/usr/bin/env python3
"""Trava: o motor responde 200 e NÃO PRODUZ FRASE — sucesso vazio.

Mesma forma do `checar_beats` (rotina que roda e não produz), um nível acima: aqui é o motor
do chat que devolve HTTP 200, `ok=True` na telemetria, e um texto vazio para quem perguntou.

Medido em 24/08/2026, antes do conserto:

    agente.orquestrador   59 chamadas · 11 bateram o teto · 18,6%
    whatsapp.agente        6 chamadas ·  0
    llm_provider        7397 chamadas ·  0

Quase uma em cada cinco perguntas ao chat morria em "(sem resposta)". ⭐ E as 11 estavam
**verdes** em `llm_usage` — `ok=True`, sem erro nenhum. Não são falha: são sucesso sem frase, o
que é bem mais difícil de achar do que um 500.

Por que existe uma trava e não só o conserto: eu achei esse defeito de MANHÃ, tratei o sintoma
(reduzi o payload de uma tool) e ele voltou seis horas depois, na primeira capacidade nova que
construí. Achado tratado sem trava volta — a diferença entre as duas vezes é que agora existe
número.

PISO = 5%. Escolhido assim: o conserto (repetição em `finish_reason=length` + teto de 2500)
deve levar isto a perto de zero; 5% dá folga para variação de dia sem esconder regressão. Se
subir de novo, ou o modelo mudou de comportamento ou alguém desligou a repetição — e nos dois
casos alguém precisa olhar. Piso frouxo demais vira sino que não toca; apertado demais vira
sino que toca sempre, e essa casa já matou 3 agentes por 3 dias assim.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/qa/checar_sucesso_vazio.py
"""
from __future__ import annotations

import asyncio
import sys

#: Acima disto, reprova. Ver o raciocínio no docstring — o número tem data e motivo.
PISO_PCT = 5.0

#: Origens que passam pelo motor do chat. `llm_provider` é a camada de baixo (chamada crua) e
#: não tem laço de tools; não é ela que produz frase para humano.
ORIGENS = ("agente.orquestrador", "consultor_executar", "consultor_escopado", "whatsapp.agente")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    SQL = """
        SELECT origem,
               count(*) AS total,
               count(*) FILTER (WHERE tokens_saida >= :teto) AS no_teto
        FROM llm_usage
        WHERE criado_em > now() - interval '24 hours'
          AND ok = true
          AND origem = ANY(:origens)
        GROUP BY 1 ORDER BY 2 DESC
    """
    async with async_session_factory() as db:
        # `tokens_saida` batendo exatamente o teto é a assinatura do corte: o modelo gastou
        # tudo e parou. Não é prova perfeita (uma resposta pode terminar no limite por acaso),
        # mas é a única que a telemetria guarda hoje — e ela move junto com o defeito.
        linhas = (await db.execute(text(SQL),
                                   {"teto": 1200, "origens": list(ORIGENS)})).all()

    if not linhas:
        # Ausência não é resultado: sem chamada nenhuma em 24h não dá para afirmar saúde.
        print("  NÃO VERIFICADO: nenhuma chamada ao motor nas últimas 24h")
        return 1

    ruins: list[str] = []
    for origem, total, no_teto in linhas:
        pct = 100.0 * int(no_teto) / int(total)
        marca = "x " if pct > PISO_PCT else "  "
        print(f"  {marca}{origem:24} {total:5} chamadas · {no_teto:4} no teto · {pct:5.1f}%")
        if pct > PISO_PCT:
            ruins.append(f"{origem}: {pct:.1f}% (piso {PISO_PCT}%)")

    if ruins:
        print(f"\n{len(ruins)} origem(ns) acima do piso — o motor está devolvendo 200 sem "
              f"produzir frase:\n  - " + "\n  - ".join(ruins) +
              "\n\nA repetição em `finish_reason=length` foi desligada, o teto voltou a ser "
              "pequeno, ou o modelo mudou de comportamento. Nos três casos alguém precisa "
              "olhar — e a telemetria diz ok=True em todas elas.")
        return 1
    print(f"\n  confere: nenhuma origem acima de {PISO_PCT}% de sucesso vazio")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
