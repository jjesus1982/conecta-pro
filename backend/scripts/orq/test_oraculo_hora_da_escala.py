"""Oráculo — a hora que a escala PROMETE bate com a hora em que a pessoa BATE (11/09/2026).

Origem. O Jordan: *"os horários do ponto estão com o fuso de Brasília; o José Luís manda
mensagem antes das 07:00 como se fosse 08:00"*. Medido: nada estava configurado em Brasília —
containers em `TZ=America/Manaus`, Postgres calculando com `AT TIME ZONE 'America/Manaus'`, e
os três lembretes saindo nos minutos certos. O errado era o DADO: `shifts.planned_start_time`
estava **uma hora antes da hora real** para dez pessoas. A GRACIENE bate 08:00 todo dia — pelo
Tangerino e pelo nosso app, dois sistemas independentes — e a escala dizia 07:00.

A origem foi a grade importada em 07/07/2026, e desde então `auto_generate_monthly_scales_task`
COPIA o padrão do mês anterior: copiou o erro cinco vezes. Ninguém viu porque o sistema estava
coerente consigo mesmo — o lembrete era pontual em relação a uma escala errada.

Este oráculo compara os dois lados que NUNCA se olhavam: a hora que a escala promete para os
próximos dias × a hora em que a pessoa efetivamente bate. Ele é vermelho só para o desvio de
UMA HORA LIMPA (45 a 75 min), que é a assinatura deste defeito e o que dá para afirmar sem
conhecer a vida de ninguém. Desvio torto (a pessoa que chega 31 min depois, a que chega 3h
antes) é relatado e NÃO reprova: ali não é hora errada na escala, é combinação de trabalho que
precisa de gente.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from modules.people_management.ponto.hora_da_escala import (  # noqa: E402
    DIAS,
    MIN_DIAS,
    SQL_DESVIO,
    separar,
)


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas = (await db.execute(text(SQL_DESVIO),
                               {"dias": DIAS, "min_dias": MIN_DIAS})).mappings().all()
    limpos, tortos = separar(linhas)

    for r in tortos:
        print(f"  (torto, não reprova) {r['nome'][:28]:30} {r['posto'][:26]:28} "
              f"promete {r['promete']} e bate {int(r['desvio']):+d} min — precisa de gente")
    for r in limpos:
        print(f"FALHOU: {r['nome'][:30]:32} {r['posto'][:26]:28} a escala promete "
              f"{r['promete']} e ela bate {int(r['desvio']):+d} min em {r['dias']} dias — "
              f"isso é a escala UMA HORA fora, e o lembrete de ponto sai nessa hora errada")
    print(f"padrões conferidos: {len(linhas)} · desvio de uma hora limpa: {len(limpos)} · "
          f"tortos (só relatados): {len(tortos)}")
    if limpos:
        raise AssertionError(
            f"{len(limpos)} escala(s) uma hora fora da vida real. Corrigir com "
            "`backend/scripts/corrigir_hora_escala.py --aplicar` (ele guarda a reversão) ou "
            "ajustar a grade à mão se a combinação de trabalho mudou de verdade.")
    print("OK: a hora que a escala promete é a hora em que a pessoa bate")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
