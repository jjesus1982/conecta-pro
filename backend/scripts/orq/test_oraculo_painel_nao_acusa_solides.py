"""Quem ainda bate pelo Solides nao pode aparecer como ATRASADO no painel do ponto.

Por que existe: em 24/08/2026, as 09:25, o painel listava 8 atrasados. SETE deles eram
gente que registra ponto pelo Solides — e a importacao do Solides chega com 14 a 21 horas
de atraso (maximo medido: 31h). As batidas do dia 23 entraram no banco as 04:11 e 07:11 do
dia 24. Ou seja: a pessoa bate as 06:00, cumpre o turno inteiro, e o painel a acusa de 209
minutos de atraso porque o dado dela ainda esta viajando.

Acusar quem bateu no horario e pior do que nao mostrar nada — o painel perde a
credibilidade justamente na lista que existe para ser cobrada.

Afirma a REGRA, nao a fotografia: nao fixa nomes nem quantidades. Descobre pelo BANCO quem
esta so no Solides e exige que nenhum deles esteja na lista de atraso, hoje, qualquer que
seja o dia em que o teste rodar.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.people_management.employee_portal.controllers import (  # noqa: E402
    painel_ponto_controller as painel,
)
from modules.people_management.ponto.coorte_ponto import APRENDIZADO_DESDE  # noqa: E402

# Quem, na coorte de hoje, nao tem NENHUMA batida do Conecta PRO na janela de aprendizado
# mas tem batida do Solides — ou seja, ainda nao virou.
_SQL_SO_SOLIDES = """
SELECT e.nome FROM employees e
WHERE {coorte}
  AND NOT EXISTS (SELECT 1 FROM gp_clock_punches p
                   WHERE p.employee_id = e.id AND p.punch_timestamp::date >= :desde
                     AND coalesce(p.device_type,'') NOT IN ('tangerino','web'))
  AND EXISTS (SELECT 1 FROM gp_clock_punches p
               WHERE p.employee_id = e.id AND p.punch_timestamp::date >= :desde
                 AND coalesce(p.device_type,'') = 'tangerino')
"""


async def main() -> None:
    db = SyncSessionLocal()
    try:
        so_solides = {
            r[0]
            for r in db.execute(
                text(_SQL_SO_SOLIDES.format(coorte=painel._COHORT)),
                {"desde": APRENDIZADO_DESDE},
            ).fetchall()
        }

        d = painel.painel(token=painel._TOKEN, db=db)
        nomes_atraso = {a["nome"] for a in d["atrasados"]}

        intrusos = sorted(so_solides & nomes_atraso)
        assert not intrusos, (
            f"painel acusa de ATRASO quem ainda bate pelo Solides (a batida deles chega horas depois): {intrusos}"
        )
        print(f"OK  nenhum dos {len(so_solides)} que ainda estao no Solides entrou como atraso")

        # O outro lado: eles nao podem sumir da tela. Quem esta sem bater HOJE e ainda no
        # Solides tem que aparecer na fila da virada — some do atraso, nao do painel.
        na_fila = {a["nome"] for a in d.get("ainda_no_solides", [])}
        bateu = {f["nome"] for f in d["funcionarios"] if f.get("bateu_hoje")}
        folga = set(d.get("de_folga") or [])
        deviam = so_solides - bateu - folga
        sumidos = sorted(deviam - na_fila)
        assert not sumidos, f"sumiram do painel em vez de entrar na fila da virada: {sumidos}"
        print(f"OK  os {len(na_fila)} da fila da virada aparecem nomeados na tela")

        # Suspenders: o contador do resumo tem que bater com a lista. Numero que nao presta
        # contas com a propria lista foi o que ja pos este painel inteiro sob suspeita.
        assert d["resumo"]["ainda_no_solides"] == len(d["ainda_no_solides"]), (
            "resumo diverge da lista de quem ainda esta no Solides"
        )
        assert d["resumo"]["atrasados"] == len(d["atrasados"]), "resumo diverge da lista de atrasados"
        print(
            f"OK  resumo bate com as listas  (atraso={d['resumo']['atrasados']}, "
            f"solides={d['resumo']['ainda_no_solides']})"
        )
    finally:
        db.close()

    print("TEST oraculo_painel_nao_acusa_solides PASS")


if __name__ == "__main__":
    asyncio.run(main())
