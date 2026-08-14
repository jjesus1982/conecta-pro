"""O espelho de ponto não pode marcar falta em dia que não aconteceu.

🔴 O DEFEITO, medido em 14/08/2026 e com aritmética que fecha exata. `absent_days` era
"todos os dias de escala DO MÊS INTEIRO menos os turnos trabalhados". Fechar agosto no dia
10 marcava os dias 11 a 31 como ausência:

    EDWARD          escala do mês 16 · turnos contados 5  → 16-5 = 11 faltas anunciadas
    ANTONIO DINIZ   escala do mês 15 · turnos contados 3  → 15-3 = 12
    MALAQUIAS       escala do mês 26 · turnos contados 10 → 26-10 = 16

Onze faltas contra SETE dias de escala decorridos é impossível. E isso não fica num painel:
a folha de ponto vai **assinada** no kit que sai para o cliente. Documento trabalhista
dizendo que a pessoa faltou num dia que ainda não chegou é prova contra a empresa E contra o
funcionário.

DEPOIS da correção, medido: agosto caiu de 12,2 faltas médias para 1,6; julho de 7,6 para
6,7 (mês passado não tem futuro a cortar — ali o ganho é `_trabalha_no_dia`).

ESTE ORÁCULO AFIRMA A REGRA, NÃO A FOTOGRAFIA: não fixa "1,6" nem nome de ninguém. A conta é
refeita do banco a cada rodada e continua valendo em setembro.

⚠️ A verdade daqui é escrita independente do serviço — conta os dias decorridos direto de
`shifts` e do calendário. Se importasse `espelho_service`, provaria só que sei chamá-lo.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Dias de escala já DECORRIDOS na competência do espelho — o teto aritmético da falta.
#: Para mês passado é o mês inteiro; para o corrente, até hoje em Manaus (a sessão do
#: Postgres roda em UTC e o dia dela vira às 20h daqui).
SQL = text(
    "WITH hoje AS (SELECT (now() AT TIME ZONE 'America/Manaus')::date AS d), "
    "esc AS ( "
    "  SELECT s.employee_id, "
    "         extract(month from s.shift_date)::int AS m, "
    "         extract(year  from s.shift_date)::int AS y, "
    "         count(*) AS dias_decorridos "
    "  FROM shifts s, hoje "
    "  WHERE NOT coalesce(s.is_off_day, false) "
    "    AND lower(coalesce(s.status::text,'')) <> 'cancelled' "
    "    AND s.shift_date <= hoje.d "
    "  GROUP BY 1,2,3) "
    "SELECT ts.employee_name AS nome, ts.reference_month AS mes, ts.reference_year AS ano, "
    "       ts.absent_days AS faltas, ts.work_days_worked AS dias, "
    "       coalesce(esc.dias_decorridos, 0) AS escala_decorrida "
    "FROM time_sheets ts "
    "LEFT JOIN esc ON CAST(esc.employee_id AS TEXT) = CAST(ts.employee_id AS TEXT) "
    "             AND esc.m = ts.reference_month AND esc.y = ts.reference_year "
    "WHERE coalesce(ts.is_deleted, false) = false "
    "  AND ts.reference_year = extract(year from (now() AT TIME ZONE 'America/Manaus'))::int"
)


async def main() -> None:
    async with async_session_factory() as db:
        linhas = (await db.execute(SQL)).mappings().all()
        assert linhas, "nenhum espelho no ano corrente — o oráculo não teria o que provar"

        # A regra: FALTA não pode passar dos dias de escala DECORRIDOS. Só isso.
        #
        # ⚠️ MINHA PRIMEIRA VERSÃO AFIRMAVA `faltas + dias <= escala` E ESTAVA ERRADA.
        # `work_days_worked` vem das BATIDAS, e gente trabalha em dia sem turno lançado —
        # medi 77 dias-pessoa assim em 7 dias, 30% do total. Somar os dois e cobrar o teto
        # da escala acusava quem trabalhou A MAIS. Falso positivo mata a confiança mais
        # rápido que achado nenhum; o invariante honesto é só o da falta.
        #
        # Sem escala publicada não há teto a afirmar: "fora da janela de cobertura da
        # fonte, ausência não é prova".
        impossiveis = [
            r for r in linhas
            if r["escala_decorrida"] > 0
            and int(r["faltas"] or 0) > int(r["escala_decorrida"])
        ]
        if impossiveis:
            det = "; ".join(
                f'{r["nome"][:22]} {r["mes"]:02d}/{r["ano"]}: '
                f'{r["faltas"]} faltas contra {r["escala_decorrida"]} '
                f'dias de escala decorridos ({r["dias"]} trabalhados)'
                for r in impossiveis[:4]
            )
            raise AssertionError(
                f"{len(impossiveis)} espelho(s) com MAIS FALTAS do que dias de escala "
                f"decorridos — falta em dia que não aconteceu: {det}"
            )
        com_escala = [r for r in linhas if r["escala_decorrida"] > 0]
        print(f"OK falta nunca passa da escala decorrida — {len(com_escala)} espelho(s) "
              f"com escala publicada, de {len(linhas)} no ano")

        # suspenders: o sintoma exato era falta ABSURDA no mês corrente. Ninguém pode ter
        # mais faltas do que dias decorridos no mês em que estamos.
        mes_corrente = [
            r for r in linhas
            if r["escala_decorrida"] > 0 and int(r["faltas"] or 0) > int(r["escala_decorrida"])
        ]
        assert not mes_corrente, (
            f"{len(mes_corrente)} espelho(s) com MAIS faltas do que dias de escala "
            f"decorridos — o cálculo voltou a contar o futuro"
        )
        print("OK nenhum espelho com mais faltas do que dias de escala decorridos")

    print("TEST oraculo_espelho_falta PASS")


if __name__ == "__main__":
    asyncio.run(main())
