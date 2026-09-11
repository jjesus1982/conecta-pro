"""A régua ÚNICA de "a escala promete a hora certa?" — detecção e correção leem daqui.

11/09/2026: eu escrevi a detecção duas vezes, num script de correção e num oráculo, e as duas
versões discordaram na primeira execução — o oráculo achou o FRANCISCO RAMON (escala promete
07:00, ele bate 06:00 há 14 dias) e o corretor não, porque olhava o histórico pela hora
PLANEJADA no passado e o oráculo olha pela hora prometida no FUTURO. A segunda é a certa: a
pergunta é "o que vamos cobrar dessa pessoa amanhã bate com o que ela faz todo dia?", e a
resposta não pode depender do que estava escrito num plano que já se sabe errado.

Duas cópias da mesma régua divergem; a que diverge cala. Então há uma só, e é esta.
"""
from __future__ import annotations

DIAS = 28
MIN_DIAS = 6
#: Desvio de UMA HORA LIMPA — a assinatura do defeito, e o único que dá para afirmar sem
#: conhecer a combinação de trabalho de cada um. Torto é relatado, nunca corrigido por script.
LIMPO_MIN, LIMPO_MAX = 45, 75

#: Para cada (pessoa, posto, hora PROMETIDA nos turnos futuros): a mediana de quanto ela se
#: afasta, nos últimos `:dias`, da primeira batida do dia dentro de ±4h daquela hora.
SQL_DESVIO = """
WITH fut AS (
  SELECT DISTINCT employee_id, post_id, planned_start_time AS plan
    FROM shifts
   WHERE shift_date >= current_date AND is_active AND NOT is_off_day),
obs AS (
  SELECT f.employee_id, f.post_id, f.plan, d.dia,
         (SELECT min(x.punch_timestamp) FROM gp_clock_punches x
           WHERE x.employee_id = f.employee_id
             AND x.punch_timestamp BETWEEN (d.dia + f.plan - interval '4 hours')
                                       AND (d.dia + f.plan + interval '4 hours')
             AND coalesce(x.status,'') <> 'facial_reprovado') AS entrada
    FROM fut f
    CROSS JOIN generate_series(current_date - make_interval(days => :dias),
                               current_date - 1, interval '1 day') AS d(dia))
SELECT o.employee_id::text AS employee_id, o.post_id::text AS post_id,
       e.nome, p.name AS posto, to_char(o.plan,'HH24:MI') AS promete,
       count(o.entrada) AS dias,
       round(percentile_cont(0.5) WITHIN GROUP (
         ORDER BY extract(epoch from (o.entrada - (o.dia + o.plan)))/60)::numeric) AS desvio
  FROM obs o JOIN employees e ON e.id = o.employee_id JOIN posts p ON p.id = o.post_id
 WHERE o.entrada IS NOT NULL
 GROUP BY 1,2,3,4,5 HAVING count(o.entrada) >= :min_dias
"""


def separar(linhas) -> tuple[list, list]:
    """(uma hora limpa, tortos). Limpo é corrigível por script; torto precisa de gente."""
    limpos, tortos = [], []
    for r in linhas:
        d = abs(int(r["desvio"]))
        if LIMPO_MIN <= d <= LIMPO_MAX:
            limpos.append(r)
        elif d > LIMPO_MAX:
            tortos.append(r)
    return limpos, tortos
