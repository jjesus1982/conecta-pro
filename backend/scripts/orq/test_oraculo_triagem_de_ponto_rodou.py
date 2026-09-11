"""Oráculo — a triagem de ponto do Hermes OLHOU o dia, ou o silêncio está mentindo (11/09/2026).

A triagem roda às 08:30 (Manaus) e avisa o Jordan só quando há gente a checar — silêncio
honesto no dia tranquilo. Isso cria a ambiguidade que esta casa já pagou caro uma vez com os
oráculos: **"não recebi nada" passa a significar duas coisas** — "está tudo bem" e "ninguém
olhou". O `celery-beat` já rodou 46 dias em loop de crash sem ninguém ver, e foi exatamente
por isso que nasceu o `orq.checar_varredura_ausente`. Mesma doença, outro assunto.

A prova é o registro no SINO: a tarefa grava lá todo dia, inclusive quando o Hermes não
responde (nesse caso grava dizendo que não olhou). Sem registro nas últimas 30 horas, a
tarefa não rodou — e isso não é dia tranquilo.

30h e não 24: a folga cobre o dia em que o worker reinicia perto do horário, sem deixar passar
um dia inteiro. Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

HORAS = 30


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    row = (await db.execute(text(
        "SELECT max(created_at), count(*) FROM communication_notifications "
        " WHERE extra_data->>'origem' = 'triagem_ponto_hermes'"))).first()
    ultimo, total = (row[0], int(row[1] or 0)) if row else (None, 0)

    if total == 0:
        print("nenhuma triagem de ponto registrada no sino — a tarefa nunca rodou")
        raise AssertionError("triagem de ponto: nenhum registro")

    idade = (await db.execute(text(
        "SELECT round(extract(epoch FROM (now() - max(created_at)))/3600.0, 1) "
        "  FROM communication_notifications WHERE extra_data->>'origem' = 'triagem_ponto_hermes'"))).scalar()
    print(f"última triagem de ponto: {ultimo} ({idade}h atrás) · {total} registros no sino")
    # ⚠️ `idade or 999` seria um defeito: 0.0 é FALSY, então a triagem que acabou de rodar
    # viraria "999 horas atrás" e o oráculo acusaria exatamente no dia em que está tudo certo.
    # Aconteceu comigo na primeira execução deste arquivo.
    horas = 999.0 if idade is None else float(idade)
    if horas > HORAS:
        raise AssertionError(
            f"a triagem de ponto não roda há {horas}h (teto {HORAS}h). Ninguém olhou o ponto — "
            "silêncio aqui NÃO é 'dia tranquilo'. Ver o beat `ponto-triagem-hermes` e se o "
            "Hermes responde em http://conecta-pro-hermes:8642/v1/models")
    print("OK: a triagem de ponto olhou o dia")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
