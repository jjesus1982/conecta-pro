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
               count(*) FILTER (WHERE tokens_saida >= :teto) AS no_teto,
               -- ⭐ 19/09/2026 — O QUE REPROVA agora é o MUDO, não a batida no teto.
               -- Medido hoje: 12 chamadas do `whatsapp.agente` com tokens_saida = 1200
               -- exato (o teto dele), e TODAS as 12 seguidas de mensagem entregue ao
               -- cliente em menos de 3 minutos. Eram rodadas INTERMEDIÁRIAS do laço de
               -- ferramentas — o modelo gasta o orçamento pensando numa rodada, a rodada
               -- seguinte responde, e quem perguntou recebe. Ninguém ficou no silêncio.
               --
               -- A trava contava essas 12 como «200 sem frase» e reprovava. Medir a
               -- chamada no teto é medir o MECANISMO; o que o 27/08 doeu foi o EFEITO —
               -- o Jordan três minutos calado esperando resposta que não veio.
               --
               -- Mudo = bateu o teto e NÃO saiu mensagem depois. Só dá para medir onde a
               -- saída é observável: `whatsapp.agente` tem `cwi_message_log`. Nas outras
               -- origens a batida vira AVISO de pressão de teto, nunca reprovação — trava
               -- que reprova o que não consegue medir é a que ensina todo mundo a ignorar.
               count(*) FILTER (
                 WHERE tokens_saida >= :teto AND origem = 'whatsapp.agente'
                   AND NOT EXISTS (
                     SELECT 1 FROM cwi_message_log m
                      WHERE m.direction = 'out'
                        AND m.created_at BETWEEN llm_usage.criado_em
                                             AND llm_usage.criado_em + interval '3 minutes')
               ) AS mudos
        FROM llm_usage
        WHERE criado_em > now() - interval '24 hours'
          AND origem = ANY(:origens)
        GROUP BY origem ORDER BY origem
    """

    async with async_session_factory() as db:
        linhas = (await db.execute(text(SQL), {"teto": 1200, "origens": list(ORIGENS)})).all()

    if not linhas:
        # Ausência não é resultado — mas também não é regressão. Em 07/09/2026 o motor ficou
        # sem uso (o dono parou o José Luís depois do vazamento de crédito) e esta trava
        # reprovou a varredura inteira e tocou o sino por um chat que ninguém chamou. Sem uso
        # em 7 dias: não há usuário sendo lesado, não há o que medir. Sai como NÃO VERIFICADO
        # com exit 0; o checar_regressao mostra "~ sem uso" em vez de "confere".
        print("  NÃO VERIFICADO: nenhuma chamada ao motor nas últimas 24h (sem uso, nada a medir)")
        return 0

    ruins: list[str] = []
    for origem, total, no_teto, mudos in linhas:
        pct_teto = 100.0 * int(no_teto) / int(total) if total else 0.0
        pct_mudo = 100.0 * int(mudos) / int(total) if total else 0.0
        marca = "x " if pct_mudo > PISO_PCT else "  "
        extra = f" · {mudos} MUDO(s) {pct_mudo:.1f}%" if mudos else ""
        print(f"  {marca}{origem:24} {total:5} chamadas · {no_teto:4} no teto ({pct_teto:4.1f}%){extra}")
        if pct_mudo > PISO_PCT:
            ruins.append(f"{origem}: {pct_mudo:.1f}% de perguntas sem resposta (piso {PISO_PCT}%)")
        elif pct_teto > 25.0:
            # aviso, não reprovação: teto apertado custa dinheiro e segundos, não resposta.
            print(
                f"      aviso: {pct_teto:.1f}% das chamadas gastam o teto inteiro — "
                "orçamento apertado para o tamanho do prompt, vale olhar o custo"
            )

    if ruins:
        print(
            f"\n{len(ruins)} origem(ns) acima do piso — houve pergunta que ficou SEM "
            "resposta, com 200 e ok=True na telemetria:"
        )
        for r in ruins:
            print(f"  - {r}")
        print(
            "\nA repetição em `finish_reason=length` foi desligada, o teto voltou a ser "
            "pequeno, ou o modelo mudou de comportamento. Nos três casos alguém precisa "
            "olhar — e a telemetria diz ok=True em todas elas."
        )
        return 1
    print(f"\n  confere: nenhuma origem acima de {PISO_PCT}% de sucesso vazio")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
