"""Cadastro de horário errado não vira acusação de atraso — e se virar, aparece aqui sozinho.

🔴 MEDIDO EM 29/09/2026. A CELIANE escreveu no WhatsApp *"já falei várias vezes"*, *"eu entro
9:0h da manhã"*, *"eu nunca bater pode atrasado"*. O cadastro dela dizia 08:00. Consequência: 60
minutos de atraso todo dia, batida RECUSADA sem justificativa, e o número descendo para
`atraso_falta_conferencia` como `minutos_alem` — que é o que sustenta DESCONTO em folha.

E ela não era a única. Medido em setembro/2026 com a régua deste oráculo: **9 pessoas, 72 turnos,
4.372 minutos fantasma, 3.292 além da tolerância** — 54,9 horas de acusação que ninguém cometeu.
Oito delas tinham o MESMO valor errado (07:00), corrigido na origem em 11/09; **sete nunca
reclamaram** e ninguém soube que havia resíduo em folha.

## ⭐ Como se separa «atraso» de «cadastro errado» — sem opinião

Pela **VARIAÇÃO**. Quem se atrasa, atrasa diferente todo dia: trânsito, ônibus, filho doente.
Quem tem o cadastro errado bate sempre na mesma hora, e a diferença é constante:

    GEILSON   8 dias · média 60 min · variação 0   · batida 08:00–08:00
    OSCAR     7 dias · média 62 min · variação 1
    CELIANE  14 dias · média 59 min · variação 2   · batida 08:51–09:02

Ninguém se atrasa exatamente 60 minutos, com margem de um minuto, oito dias seguidos.

## ⚠️ As duas armadilhas que erraram a minha primeira medição

Este oráculo existe na forma que tem porque a versão anterior da régua deu duas respostas erradas:

1. **Agrupar por PESSOA mistura regimes.** O cadastro da Celiane mudou de 07:00 para 08:00 no meio
   do mês; a variância estourou e o filtro «variação baixa» a descartou — justamente ela. O
   regime é o par **(pessoa, horário cadastrado)**, porque é ele que define o que se compara.
2. **Parear batida por DATA DE CALENDÁRIO faz o noturno inventar atraso.** O MAURICIO apareceu com
   **3.518 minutos em 5 dias** (703 por dia): ele entra 18:58 e o cadastro daquela linha dizia
   07:00. *Data da batida ≠ data da escala.* Aqui a batida é pareada ao **instante previsto ±3h**,
   e ele desaparece da lista — corretamente.

⚠️ O que denunciou o defeito nº 2 não foi trava nenhuma: foi o valor ser absurdo. 703 minutos por
dia não é atraso de ninguém.

## O que este oráculo afirma

**Nenhum regime com assinatura de cadastro errado fica sem correção registrada.** Regime suspeito
é: ≥5 dias medidos, diferença média > 25 min, variação < 10 min. Se aparecer um, ele reprova com
nome, cadastro e minutos — e a saída é uma das duas, ambas humanas: corrigir o horário em `shifts`
ou registrar linha em `ponto_horario_vigencia`.

⭐ Afirma a REGRA, não a fotografia: nenhum nome, nenhum id, nenhuma contagem esperada. A janela é
corrente, então o mês vira sozinho. Hoje devolve ZERO — e devolveria NOVE na janela de setembro,
que é como se sabe que ela tem dentes sem precisar que alguém reclame.

⚠️ A diferença é medida JÁ COM a vigência aplicada. Quem foi corrigido sai da lista por mérito do
conserto, não por complacência da régua.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

#: Dias de janela. 21 cobre três semanas de escala sem arrastar mês fechado.
JANELA_DIAS = 21
#: Mínimo de dias medidos no regime. Menos que isso, média e variação não dizem nada.
MIN_DIAS = 5
#: Acima disto a diferença deixa de ser «chegou em cima da hora».
MIN_MEDIA_MIN = 25
#: Abaixo disto a diferença é CONSTANTE — assinatura de cadastro, não de atraso.
MAX_VARIACAO_MIN = 10

_SQL = f"""
WITH t AS (
  SELECT e.id AS eid, e.nome, s.shift_date, s.planned_start_time AS cad,
         (s.shift_date + coalesce(
            (SELECT hv.entrada FROM ponto_horario_vigencia hv
              WHERE hv.employee_id = e.id AND hv.vigencia_inicio <= s.shift_date
                AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= s.shift_date)
              ORDER BY hv.vigencia_inicio DESC LIMIT 1),
            s.planned_start_time)) AS marco
    FROM shifts s
    JOIN employees e ON e.id = s.employee_id
   WHERE s.shift_date >= current_date - {JANELA_DIAS}
     AND s.shift_date <= current_date
     AND NOT s.is_off_day
),
-- ⚠️ pareamento pelo INSTANTE, jamais por data de calendário: o noturno cruza a meia-noite e
-- comparar com o dia do cadastro inventa ~700 minutos de atraso por turno.
ent AS (
  SELECT t.eid, t.nome, t.cad,
         EXTRACT(EPOCH FROM (b.pt - t.marco)) / 60 AS dif
    FROM t
    JOIN LATERAL (
      SELECT min(cp.punch_timestamp) AS pt
        FROM gp_clock_punches cp
       WHERE cp.employee_id = t.eid
         AND cp.punch_type = 'entrada'
         AND cp.punch_timestamp BETWEEN t.marco - interval '3 hours'
                                    AND t.marco + interval '3 hours'
    ) b ON b.pt IS NOT NULL
)
SELECT nome, to_char(cad, 'HH24:MI') AS cadastro, count(*) AS dias,
       round(avg(dif))::int AS media,
       round(coalesce(stddev_pop(dif), 0))::int AS variacao,
       sum(greatest(round(dif) - 15, 0))::int AS alem_tolerancia
  FROM ent
 GROUP BY nome, eid, cad
HAVING count(*) >= {MIN_DIAS}
   AND avg(dif) > {MIN_MEDIA_MIN}
   AND coalesce(stddev_pop(dif), 0) < {MAX_VARIACAO_MIN}
 ORDER BY media DESC
"""


def main() -> int:
    with get_sync_db() as db:
        suspeitos = db.execute(text(_SQL)).mappings().all()
        # Contexto: quantos regimes a régua examinou. Sem isto, «0 suspeitos» pode ser «não há
        # ninguém» ou «a consulta não achou turno nenhum» — e as duas leem igual.
        examinados = db.execute(
            text(
                "SELECT count(DISTINCT (s.employee_id, s.planned_start_time)) "
                f"  FROM shifts s WHERE s.shift_date >= current_date - {JANELA_DIAS} "  # noqa: S608
                "   AND s.shift_date <= current_date AND NOT s.is_off_day"
            )
        ).scalar() or 0

    assert examinados > 0, (
        "a régua não encontrou NENHUM regime de turno na janela — isso não é «ninguém suspeito», é "
        "consulta cega. Verde aqui não provaria nada"
    )

    if suspeitos:
        print(f"🔴 {len(suspeitos)} regime(s) com assinatura de CADASTRO ERRADO, não de atraso:")
        for s in suspeitos:
            print(f"   {s['nome'][:28]:28} cadastro {s['cadastro']} · {s['dias']} dias · "
                  f"média {s['media']} min · variação {s['variacao']} · "
                  f"{s['alem_tolerancia']} min além da tolerância")
        total = sum(s["alem_tolerancia"] for s in suspeitos)
        raise AssertionError(
            f"{len(suspeitos)} pessoa(s) acusada(s) de atraso com diferença CONSTANTE "
            f"(variação < {MAX_VARIACAO_MIN} min): {total} minutos além da tolerância que descem "
            "para `minutos_alem` e sustentam desconto. Ninguém se atrasa sempre o mesmo tanto — "
            "corrija o horário em `shifts` ou registre linha em `ponto_horario_vigencia`"
        )

    print(f"OK {examinados} regime(s) (pessoa × horário cadastrado) examinados nos últimos "
          f"{JANELA_DIAS} dias")
    print(f"OK nenhum com diferença média > {MIN_MEDIA_MIN} min e variação < {MAX_VARIACAO_MIN} min "
          "— ninguém está sendo acusado de um atraso que é erro de cadastro")
    print("TEST oraculo_cadastro_de_horario_suspeito PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
