"""Um turno agendado começa jornada nova — batida de outro dia não decide o tipo da de hoje.

🔴 MEDIDO EM 29/09/2026, e quem achou foi a ERIKA, escrevendo no WhatsApp:

    "A localização do celular está ligada, e mesmo assim não está querendo fazer o registro
     de intervalo, em ida e nem volta"

O GPS não tinha nada a ver. A única batida dela no dia — **07:01:03, a 5 m do posto, para um
turno 07:00–19:00** — saiu tipada como **`saida`**. Com a chegada registrada como saída, a
jornada lia-se fechada e ela não conseguia registrar mais nada.

## A causa

O tipo vem de `seq[feitas]`, e `feitas` conta as batidas desde o início da jornada, achado por
uma janela de **14 horas** para trás. A batida anterior dela era **28/09 às 17:09** — 13h51m
antes. Cabe na janela.

⭐ E a raiz é anterior: a ERIKA é **12x36 e trabalha em dias ÍMPARES**. Em 28/09 ela **não tinha
turno**, e mesmo assim havia um par de contingência lançado naquele dia. Foi essa batida órfã que
envenenou a janela.

⚠️ A janela de 14h **não estava errada** — é o corte que o espelho de ponto usa e é ela que
protege o noturno que cruza a meia-noite. Faltava um terceiro piso: **o começo de um turno
AGENDADO também é começo de jornada.**

## O que este oráculo trava

1. **O piso do turno existe** no cálculo de `feitas`. Se sair, batida de véspera volta a decidir
   o tipo da batida de hoje.
2. **A folga de 4h para quem chega adiantado continua lá**, com o `LEAST` que faz o piso RECUAR
   até incluir uma batida adiantada real. Medido em 90 dias: 519 batidas até 1h antes do turno,
   95 entre 1 e 2h, 16 entre 2 e 3h, 10 entre 3 e 4h e **5 além de 4h**. Sem o `LEAST`, essas
   cinco passariam a receber «entrada» duas vezes — eu consertaria uma pessoa e quebraria três.
3. **Comportamento contra o banco**: ninguém SAI duas vezes sem ter entrado. `saida` logo após
   `saida`, com um início de turno agendado entre as duas, é a assinatura exata deste defeito.

⭐ Afirma a REGRA, não a fotografia: nenhum nome, nenhum id. A janela é corrente.

## ⚠️ Três réguas erradas antes desta, e é a parte que mais ensina

1. **«mesmo tipo da anterior, em menos de 14h»** → **71 casos**. Mas quatro são duplo toque
   (menos de 2 min), 39 são repetição em menos de 1h e 27 entre 1 e 8h — coisas diferentes.
2. **«mesmo tipo, com início de turno entre as duas»** → **217 casos em 90 dias**. Todos
   `entrada` após `entrada` com 24 a 348 horas: gente que **nunca bateu a saída**. Aí o tipo
   está CERTO — o que falta é a saída. Problema real, mas OUTRO.
3. Só **`saida` após `saida` cruzando um turno** isola o defeito: **1 caso em 90 dias**.

⭐ E antes disso eu disse ao Jordan que a ERIKA era «o único caso em 30 dias». Cheguei a isso
olhando as 15 primeiras linhas ordenadas por data e generalizando — o mesmo erro de amostra que
eu tinha apontado numa sessão vizinha horas antes. **Contar é diferente de olhar o começo da
lista.**

⚠️ A janela de asserção é de **7 dias**, não 90: a varredura roda todo dia, então 7 dias pegam
qualquer caso novo no dia seguinte, e dívida antiga não deixa a trava vermelha para sempre.
Alarme que sempre toca para de ser lido. O número de 90 dias é IMPRESSO, para não sumir de vista.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

_CTRL = "/app/modules/people_management/employee_portal/controllers/self_service_controller.py"

#: Janela de ASSERÇÃO. A varredura roda diariamente; 7 dias pegam o caso novo no dia seguinte
#: sem arrastar dívida antiga para sempre.
DIAS_ASSERCAO = 7
#: Janela de RELATÓRIO — impressa, nunca asseverada.
DIAS_RELATORIO = 90


def main() -> int:
    with open(_CTRL, encoding="utf-8") as fh:
        src = fh.read()
    ast.parse(src)  # sintaxe quebrada aqui derruba a batida de todo mundo

    # 1 — o piso do turno existe
    assert "sh.planned_start_time" in src and "FROM shifts sh" in src, (
        "o piso do TURNO AGENDADO saiu do cálculo de `feitas`: batida de outro dia volta a "
        "decidir o tipo da batida de hoje, e a chegada de quem trabalha 12x36 vira «saída»"
    )
    # 2 — a folga de quem chega adiantado continua
    assert "LEAST(t.ini - interval '4 hours'" in src, (
        "a folga de 4h do piso do turno sumiu: quem chega mais de 4h adiantado passa a receber "
        "«entrada» duas vezes. Medido: 5 batidas em 90 dias chegam além de 4h"
    )
    assert "interval '8 hours'" in src, (
        "o recuo do piso (o `LEAST` com a batida mais antiga da janela de 8h) sumiu — é ele que "
        "impede que consertar um caso quebre quem chega muito cedo"
    )
    # a janela de 14h NÃO pode ter sido substituída: ela é quem protege o noturno
    assert "interval '14 hours'" in src, (
        "a janela de 14h desapareceu. Ela não estava errada: é o corte do espelho de ponto e é "
        "o que impede o noturno de receber «entrada» às 2 da manhã"
    )

    # 3 — comportamento: ninguém sai duas vezes sem entrar
    _SQL = """
WITH seq AS (
  SELECT cp.employee_id AS eid, e.nome, cp.punch_timestamp AS ts, cp.punch_type,
         lag(cp.punch_timestamp) OVER w AS ant, lag(cp.punch_type) OVER w AS ant_tipo
    FROM gp_clock_punches cp JOIN employees e ON e.id = cp.employee_id
   WHERE cp.punch_timestamp >= current_date - :dias
  WINDOW w AS (PARTITION BY cp.employee_id ORDER BY cp.punch_timestamp))
SELECT count(*) AS n, coalesce(string_agg(DISTINCT left(nome, 22), ', '), '') AS quem
  FROM seq s
 WHERE s.ant_tipo = 'saida' AND s.punch_type = 'saida'
   AND EXISTS (SELECT 1 FROM shifts sh
                WHERE sh.employee_id = s.eid AND NOT sh.is_off_day
                  AND (sh.shift_date + sh.planned_start_time) > s.ant
                  AND (sh.shift_date + sh.planned_start_time) <= s.ts)
"""
    with get_sync_db() as db:
        recente = db.execute(text(_SQL), {"dias": DIAS_ASSERCAO}).mappings().first()
        historico = db.execute(text(_SQL), {"dias": DIAS_RELATORIO}).mappings().first()
        # Contexto: sem saber quantas batidas a régua olhou, «0 impossíveis» e «consulta cega»
        # leem igual.
        total = db.execute(
            text("SELECT count(*) FROM gp_clock_punches "
                 "WHERE punch_timestamp >= current_date - :d"),
            {"d": DIAS_ASSERCAO},
        ).scalar() or 0

    assert total > 0, (
        f"a régua não encontrou batida nenhuma em {DIAS_ASSERCAO} dias — isso não é «tudo certo», "
        "é consulta cega. Verde aqui não provaria nada"
    )
    assert recente["n"] == 0, (
        f"{recente['n']} caso(s) de SAÍDA logo após SAÍDA cruzando um início de turno "
        f"({recente['quem']}): ninguém sai duas vezes sem entrar. É a assinatura do tipo decidido "
        "por batida de outra jornada — foi assim que a chegada da ERIKA virou «saída» e a deixou "
        "sem conseguir registrar nada o dia inteiro"
    )

    print("OK o piso do TURNO AGENDADO está no cálculo de `feitas`")
    print("OK a folga de 4h e o recuo de 8h continuam — quem chega adiantado não quebra")
    print("OK a janela de 14h continua — o noturno segue protegido")
    print(f"OK {total} batida(s) em {DIAS_ASSERCAO} dias, {recente['n']} saída-após-saída")
    print(f"OK histórico de {DIAS_RELATORIO} dias: {historico['n']} caso(s) "
          f"({historico['quem'] or 'nenhum'}) — impresso, não asseverado")
    print("TEST oraculo_turno_agendado_abre_jornada PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
