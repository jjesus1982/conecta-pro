BEGIN;
-- Turnos para ELEN XAVIER NUNES e ALEXANDRE SOUZA DA SILVA, autorizados pelo Jordan em 25/09.
--
-- POR QUE EXISTEM: os dois batem ponto há semanas e NUNCA estiveram em escala nenhuma —
-- 0 turnos, `max(shift_date)` NULO. A hora deles não era conferida contra nada e o espelho os
-- mostrava batendo sem estar previstos.
--
-- ⚠️ O ciclo e o horário são DERIVADOS das batidas de ENTRADA, não inventados:
--   ÉLEN      19:00, 7 entradas em 14 dias, TODAS em dia PAR   → noturno 19:00→07:00, ciclo PAR
--   ALEXANDRE 07:00, 6 entradas em 14 dias, TODAS em dia ÍMPAR → diurno 07:00→19:00, ciclo ÍMPAR
-- Paridade limpa (uma só) nos dois — por isso são estes dois e não os outros três, que são
-- comerciais ou têm uma batida só.
--
-- `scale_id` vem da escala do MÊS e do POSTO, porque os 14 dias atravessam setembro e outubro.
INSERT INTO shifts (id, scale_id, post_id, employee_id, shift_date,
                    planned_start_time, planned_end_time, status, is_active, is_off_day, created_at)
SELECT gen_random_uuid(), s.id, p.post_id, p.eid, d.dia, p.hora_ini, p.hora_fim,
       'scheduled', true, false, now()
FROM (VALUES ('ELEN XAVIER NUNES','PAR','19:00'::time,'07:00'::time),
             ('ALEXANDRE SOUZA DA SILVA','IMPAR','07:00'::time,'19:00'::time)) AS a(nome,ciclo,hora_ini,hora_fim)
JOIN employees e ON unaccent(upper(e.nome)) = a.nome
JOIN allocations al ON al.employee_id = e.id AND coalesce(al.is_active,true)
CROSS JOIN LATERAL (SELECT e.id AS eid, al.post_id, a.ciclo, a.hora_ini, a.hora_fim) p
CROSS JOIN generate_series(current_date, current_date+13, '1 day') AS d(dia)
JOIN scales s ON s.post_id = p.post_id
   AND to_char(d.dia,'MM/YYYY') = substring(coalesce(s.name,'') from 8 for 7)
WHERE ((p.ciclo='PAR'   AND extract(day from d.dia)::int % 2 = 0)
    OR (p.ciclo='IMPAR' AND extract(day from d.dia)::int % 2 = 1))
  -- idempotente: rodar duas vezes não duplica
  AND NOT EXISTS (SELECT 1 FROM shifts x WHERE x.employee_id = p.eid AND x.shift_date = d.dia::date);
COMMIT;
