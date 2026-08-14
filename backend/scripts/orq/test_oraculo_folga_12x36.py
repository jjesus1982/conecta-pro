"""O painel não pode chamar de ATRASADO quem está de FOLGA — nem inverter o revezamento.

DOIS DEFEITOS REAIS, medidos em 14/08/2026 às 09:26 contra o painel de produção:

1. FOLGA VIRANDO ATRASO. Dos 15 "atrasados", ONZE eram 12x36 que tinham trabalhado no dia
   anterior — gente de folga, cobrada por um alerta que o Jordan pediu para monitorar a
   adesão ao ponto novo. Um alerta que grita com quem está de folga é um alerta que ninguém
   lê na semana seguinte.

2. REVEZAMENTO INVERTIDO. `horario_entrada` ganhou o parâmetro `iso_week` para decidir o
   revezamento de fim de semana do Michelangelo, e o painel continuou chamando com 5
   argumentos. Com `iso_week=0`, `(0 - 33) % 2 = 1` → "trocou" → no sábado o painel cobraria
   o artífice de folga e daria o escalado como ausente. Os dois errados, ao mesmo tempo.

O QUE ESTE ORÁCULO AFIRMA É A REGRA, NÃO A FOTOGRAFIA. Não fixa "11 pessoas" nem nomes: a
verdade é recalculada do banco a cada rodada, então ele continua valendo quando o quadro
mudar, quando alguém entrar de férias ou quando o Michelangelo trocar de artífice.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.people_management.employee_portal.controllers.painel_ponto_controller import (  # noqa: E402
    _TOKEN,
    painel,
)
from modules.people_management.ponto.coorte_ponto import (  # noqa: E402
    HORAS_ENTRE_TURNOS,
    REVEZAMENTO_FDS,
    horario_entrada,
)

# A VERDADE, escrita de forma independente do builder. Se isto fosse copy-paste da query do
# painel, o oráculo só provaria que eu sei copiar: quem começou turno ONTEM e não bateu hoje.
SQL_DE_FOLGA = text(
    "WITH inicio AS ("
    "  SELECT employee_id, d FROM ("
    "    SELECT employee_id, punch_timestamp::date AS d,"
    "           punch_timestamp - lag(punch_timestamp)"
    "             OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS gap"
    "    FROM gp_clock_punches"
    "    WHERE punch_timestamp >= (now() AT TIME ZONE 'America/Manaus')::date - 30"
    "      AND punch_timestamp <  (now() AT TIME ZONE 'America/Manaus')::date"
    "  ) x WHERE gap IS NULL OR gap > make_interval(hours => :h)),"
    "ult AS (SELECT employee_id, max(d) AS ultimo FROM inicio GROUP BY employee_id) "
    "SELECT e.nome FROM employees e JOIN ult ON ult.employee_id = e.id "
    "WHERE lower(coalesce(e.status,'')) = 'ativo' "
    "  AND lower(coalesce(e.escala_padrao,'')) = '12x36' "
    "  AND ult.ultimo = (now() AT TIME ZONE 'America/Manaus')::date - 1 "
    "  AND NOT EXISTS (SELECT 1 FROM gp_clock_punches p WHERE p.employee_id = e.id "
    "        AND p.punch_timestamp::date = (now() AT TIME ZONE 'America/Manaus')::date "
    "        AND coalesce(p.device_type,'') NOT IN ('tangerino','web'))"
)


def main() -> None:
    with SyncSessionLocal() as db:
        d = painel(token=_TOKEN, db=db)
        atrasados = {a["nome"] for a in d["atrasados"]}
        de_folga = set(db.execute(SQL_DE_FOLGA, {"h": HORAS_ENTRE_TURNOS}).scalars().all())

        # 1 — ninguém de folga pode estar na lista de atraso
        invasores = sorted(de_folga & atrasados)
        assert not invasores, f"de folga e cobrado como atrasado: {invasores}"
        print(f"OK folga não vira atraso: {len(de_folga)} de folga hoje, "
              f"{len(atrasados)} atrasados, interseção 0")

        # suspenders: o defeito exato foi o painel NÃO conhecer folga. Se `de_folga` tem
        # gente e o painel não devolve nenhuma, o cálculo sumiu de novo.
        if de_folga:
            assert d["resumo"].get("de_folga"), "painel voltou a ignorar a folga do 12x36"

        # 2 — revezamento: em cada fim de semana, EXATAMENTE UM dos dois trabalha, e os dois
        # trocam de lugar na semana seguinte. Isto pega o `iso_week` esquecido: sem ele o
        # horário não depende da semana e as duas semanas dariam a mesma resposta.
        for posto, cfg in REVEZAMENTO_FDS.items():
            dupla = [cfg["sabado"], cfg["domingo"]]
            wk = cfg["semana_ref"]
            for dow, nome_dia in ((6, "sábado"), (0, "domingo")):
                for semana in (wk, wk + 1):
                    trabalham = [n for n in dupla
                                 if horario_entrada(n, posto, "ARTÍFICE", "", dow, semana)]
                    assert len(trabalham) == 1, (
                        f"{posto} {nome_dia} semana {semana}: {len(trabalham)} trabalhando, "
                        f"esperado exatamente 1 ({trabalham})")
                # e tem de TROCAR de uma semana para a outra
                a = [n for n in dupla if horario_entrada(n, posto, "ARTÍFICE", "", dow, wk)][0]
                b = [n for n in dupla if horario_entrada(n, posto, "ARTÍFICE", "", dow, wk + 1)][0]
                assert a != b, f"{posto} {nome_dia}: não revezou entre as semanas {wk} e {wk+1}"
            print(f"OK revezamento {posto}: 1 por dia, e troca a cada semana")

    print("TEST oraculo_folga_12x36 PASS")


if __name__ == "__main__":
    main()
