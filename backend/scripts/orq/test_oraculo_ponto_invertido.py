"""Ninguém sai para almoçar 8 horas depois de entrar.

🔴 O DEFEITO, medido em 23/08/2026. A LÍVIA, dia 17/08: entrou às 06:00 pelo app e voltou
às 18:01 para registrar a SAÍDA. O sistema mandou ela bater SAÍDA PARA O ALMOÇO, às seis da
tarde. Ela não errou — o app pediu. Nas palavras do Jordan: "pra uns o ponto está
invertido". Medido: 18 batidas de saída-de-almoço às 16h ou depois, 10 pessoas.

A causa não é óbvia e eu errei o diagnóstico na primeira tentativa. Supus que o Sólides
inflava a contagem do dia; era o CONTRÁRIO. As batidas do Sólides chegam ao banco 6 a 15
HORAS DEPOIS (as do dia 17 entraram em 18/08, às 04:09 e 13:39). Às 18:01 o banco tinha UMA
batida dela — a entrada das 06:00. `seq[count(*)]` = `seq[1]` = "saida_almoco".

Este oráculo reproduz o caso REAL: entrada de manhã, app aberto no fim do turno. É o que a
minha primeira correção não fazia, e por isso ela passava no código defeituoso.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.people_management.employee_portal.controllers.self_service_controller import (  # noqa: E402
    _proxima_batida_info,
)

# ZZ FIXO, nunca gerado por execução: prefixo que varia não casa com o órfão de ontem, que é
# exatamente o lixo que ninguém remove. E `ZZ` ordena no fim de qualquer listagem — o que
# escapar aparece agrupado no rodapé, não escondido no meio do dado real.
_PREFIXO = "ZZORQ-INVERT-"
#: O prefixo ANTERIOR fica aqui até a limpeza de entrada tê-lo varrido de vez. Trocar de
#: prefixo sem varrer o antigo é criar órfão novo com as próprias mãos.
_PREFIXOS_ANTIGOS = ("ORQ-INVERT-",)

#: (descrição, horas atrás em que a ENTRADA foi batida, próximo tipo esperado)
#:
#: O NOTURNO está aqui de propósito. Ele entra às 18:00 e sai às 06:00 — à meia-noite a
#: DATA vira, e a versão anterior contava por `punch_timestamp::date = hoje`: a contagem
#: zerava e o app oferecia "entrada" a quem trabalhava havia seis horas. Medido em
#: 23/08/2026: 33 batidas de entrada entre 00h e 06h, de 9 pessoas que já tinham entrado
#: nas 12h anteriores. O ADAILSON bateu entrada às 02:00 e "retorno do almoço" às 03:00.
#: Por isso a janela é o TURNO (corte de 14h), não o dia do calendário.
CASOS = [
    ("entrou agora — almoço ainda faz sentido", 1, "saida_almoco"),
    ("entrou há 4h — ainda é hora de almoçar", 4, "saida_almoco"),
    ("entrou há 9h — está encerrando", 9, "saida"),
    ("LÍVIA: entrou 06:00, voltou 18:01", 12, "saida"),
    # NOTURNO cruzando a meia-noite: 5h depois de entrar ainda é hora de almoçar, e a
    # virada da data não pode zerar a jornada.
    ("NOTURNO: entrou 18:00, agora são 23:00", 5, "saida_almoco"),
    ("NOTURNO: entrou 18:00, agora são 02:00", 8, "saida"),
]


#: (descrição, [(horas atrás, tipo)], esperado) — o espelho do defeito: a pessoa saiu para
#: o almoço e NUNCA bateu a volta. Medido no print de 23/08/2026, 18:04: a Lívia tinha
#: entrada 05:59 e saída de almoço 12:38, e o app oferecia "BATER VOLTA DO ALMOÇO" cinco
#: horas e meia depois, quando ela queria registrar a saída.
CASOS_ALMOCO = [
    ("voltou logo — 1h de almoço", [(6, "entrada"), (1, "saida_almoco")], "retorno_almoco"),
    ("LÍVIA: almoçou 12:38, agora são 18:04", [(12, "entrada"), (5, "saida_almoco")], "saida"),
]


async def main() -> None:
    async with async_session_factory() as db:
        emp = (
            await db.execute(
                text(
                    "SELECT e.id::text FROM employees e "
                    " WHERE lower(coalesce(e.status,'')) = 'ativo' "
                    "   AND NOT coalesce(e.recebe_intrajornada, false) "
                    "   AND NOT EXISTS (SELECT 1 FROM gp_clock_punches p "
                    "        WHERE p.employee_id = e.id "
                    "          AND p.punch_timestamp::date = (now() AT TIME ZONE 'America/Manaus')::date) "
                    " LIMIT 1"
                )
            )
        ).scalar()
        assert emp, "sem funcionário de 4 batidas livre de batidas hoje — pré-condição"

        falhas: list[str] = []
        try:
            for desc, horas, esperado in CASOS:
                await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"), {"p": f"{_PREFIXO}%"})
                await db.execute(
                    text(
                        "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, "
                        "  punch_timestamp, status, device_type) "
                        "VALUES (:pid, CAST(:e AS uuid), 'entrada', "
                        "  (now() AT TIME ZONE 'America/Manaus') - make_interval(hours => :h), "
                        "  'approved', 'mobile')"
                    ),
                    {"pid": f"{_PREFIXO}0", "e": emp, "h": horas},
                )
                await db.flush()
                got = (await _proxima_batida_info(db, emp))["tipo"]
                if got != esperado:
                    falhas.append(f"{desc}: esperado {esperado}, veio {got}")
        finally:
            # Limpa SEMPRE — batida sintética que sobra em gp_clock_punches vira falta ou
            # hora extra no espelho de alguém.
            await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"), {"p": f"{_PREFIXO}%"})
            await db.commit()

        # Segundo bloco: a volta do almoço que nunca veio.
        try:
            for desc, batidas, esperado in CASOS_ALMOCO:
                await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"), {"p": f"{_PREFIXO}%"})
                for i, (h, t) in enumerate(batidas):
                    await db.execute(
                        text(
                            "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, "
                            "  punch_timestamp, status, device_type) "
                            "VALUES (:pid, CAST(:e AS uuid), :t, "
                            "  (now() AT TIME ZONE 'America/Manaus') - make_interval(hours => :h), "
                            "  'approved', 'mobile')"
                        ),
                        {"pid": f"{_PREFIXO}A{i}", "e": emp, "t": t, "h": h},
                    )
                await db.flush()
                got = (await _proxima_batida_info(db, emp))["tipo"]
                if got != esperado:
                    falhas.append(f"{desc}: esperado {esperado}, veio {got}")
        finally:
            await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"), {"p": f"{_PREFIXO}%"})
            await db.commit()

        assert not falhas, f"{len(falhas)} cenário(s) errado(s) — " + " ; ".join(falhas)

        sobrou = (
            await db.execute(
                text("SELECT count(*) FROM gp_clock_punches WHERE punch_id LIKE :p"),
                {"p": f"{_PREFIXO}%"},
            )
        ).scalar()
        assert not sobrou, f"{sobrou} batida(s) sintética(s) ficaram no banco"

    print(f"OK {len(CASOS)} cenários — o app não pede almoço a quem entrou há 8h ou mais")
    print(f"OK {len(CASOS_ALMOCO)} cenários — nem a volta do almoço a quem saiu há 3h ou mais")
    print("OK nenhuma batida sintética sobrou no banco")
    print("TEST oraculo_ponto_invertido PASS")


if __name__ == "__main__":
    asyncio.run(main())
