#!/usr/bin/env python3
"""BATIDA FALTANDO: gente que trabalhou e não tem a batida de entrada (ou de saída).

Origem: DGX X2 (24/09/2026). Ao medir «atraso» contra a folha, 64 % dos 20.445 minutos de
setembro NÃO eram atraso — eram turnos em que a primeira batida da janela é a de SAÍDA, porque
a de entrada nunca foi feita. A régua do mapa de ponto lê isso como «chegou 8 h depois», e
descontar em cima disso tiraria um dia inteiro de quem trabalhou o dia inteiro.

A X2 blindou o dinheiro (esses turnos saem da estimativa). O que faltava é a lista com NOME:
quem, em que dia, em que posto, qual batida falta. É dívida de OPERAÇÃO — app travando, posto
sem sinal, agente esquecendo — e quem resolve é o supervisor, não a folha.

**CONTADA, não binária.** Zero é o alvo, mas a linha existe para ser comparada com a de ontem:
se o número CRESCE, alguma coisa na operação piorou (app, aparelho, treinamento). O caçador
acusa; o dono decide.

Régua: `ponto/services/justificativa_batida.batidas_faltando` — importada, não recriada. É a
mesma régua da tela `batida-faltando` e do oráculo `test_oraculo_y3_justificativa_batida.py`.
Um turno só conta depois de encerrado, e só se ALGUÉM bateu: turno sem batida nenhuma é
falta/descoberto, que é outra coisa e tem tela própria.

    python3 backend/scripts/qa/checar_batida_faltando.py
    QA_DIAS=30 python3 backend/scripts/qa/checar_batida_faltando.py

Linha canônica: `TOTAL dias com batida faltando: <n>`. Exit 1 quando há achado.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DIAS = int(os.environ.get("QA_DIAS", "60"))
TOPO = int(os.environ.get("QA_TOPO", "10"))


async def main() -> int:
    from core.database import async_session_factory
    from modules.people_management.ponto.services import justificativa_batida as jb

    async with async_session_factory() as db:
        r = await jb.resumo_batidas(db, dias=DIAS)

    linhas, por_pessoa = r["linhas"], r["por_pessoa"]
    entrada = sum(1 for x in linhas if not x["tem_entrada"] and x["tem_saida"])
    saida = sum(1 for x in linhas if x["tem_entrada"] and not x["tem_saida"])
    ambas = sum(1 for x in linhas if not x["tem_entrada"] and not x["tem_saida"])

    print(f"BATIDA FALTANDO — turnos encerrados entre {r['de']} e {r['ate']} ({DIAS} dias)\n")
    print(f"   {len(linhas)} dia(s)-pessoa em {len(por_pessoa)} pessoa(s)")
    print(f"   falta ENTRADA: {entrada}   falta SAÍDA: {saida}   faltam AS DUAS: {ambas}")
    if entrada or ambas:
        print("   (entrada faltando é o que a X2 tira da conta de atraso: não é atraso, é batida que não houve)")

    if r["escala_divergente"]:
        print(f"\n   FORA DO TOTAL — {len(r['escala_divergente'])} dia(s) em que a batida EXISTE, só que fora do turno")
        print("   previsto: aí não falta batida, falta acertar a escala lançada.")
        for nome, n in sorted(r["escala_por_pessoa"].items(), key=lambda kv: -kv[1])[:5]:
            print(f"      {nome[:38]:<38} {n:>3} dia(s)")

    piores = sorted(por_pessoa.items(), key=lambda kv: -kv[1]["dias"])[:TOPO]
    if piores:
        print("\n   Quem mais deve:")
        for nome, p in piores:
            print(
                f"      {nome[:38]:<38} {p['dias']:>3} dia(s)  (entrada {p['entrada']} · saída {p['saida']} · ambas {p['ambas']})"
            )

    if linhas:
        print("\n   Os mais recentes:")
        for x in linhas[:5]:
            bat = ", ".join(x["batidas"]) or "só check-in manual"
            print(
                f"      {x['dia']} · {x['nome'][:28]:<28} {x['turno']} · {x['posto'][:24]:<24} "
                f"falta {x['falta']:<15} [{bat}] · mapa: {x['estado_mapa']}"
            )
        print("\n   Enquanto a batida falta, o dia NÃO entra na conta de atraso (X2 o separa) e NÃO vira")
        print("   falta automática (o espelho só conta dia SEM NENHUMA batida). Fica pendência de operação.")

    print(f"\nTOTAL dias com batida faltando: {len(linhas)}")
    return 1 if linhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
