-- FORWARD — Posto 3/9 MIRANTE grade final + emenda Euler (Jordan, 2026-07-08)
-- Noturno: Ailton (ímpares) × Eduardo (pares). Diurno: Gama+Ediwilson (ímpares) × Chagas+Alexandre (pares).
-- Euler: diurno-ímpares no Mirante até 21/07 (vaga do Ediwilson em férias); 22/07+ cobre férias do
-- Francisco Ramon no Laranjeiras (diurno-pares). Férias do Francisco: registrar no DP quando Jordan der as datas.
BEGIN;

-- a) Eduardo: noturno passa a DIAS PARES (par do Ailton)
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Realocado p/ noturno-pares (grade Jordan 08/07).', updated_at=now()
FROM employees e WHERE s.employee_id=e.id AND e.nome='EDUARDO OLIVEIRA DE SOUZA'
  AND s.shift_date>=CURRENT_DATE AND s.shift_date<='2026-07-31' AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND month=7 AND year=2026),
  e.id, '593e86e5-7b3c-406c-a314-1ca80b03ec9f', d::date, '18:00', '06:00', 60,
  'scheduled', false, true, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Noturno/dias pares (grade Jordan 08/07).', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='EDUARDO OLIVEIRA DE SOUZA' AND EXTRACT(DAY FROM d)::int % 2 = 0;

-- b) Gama: diurno passa a DIAS ÍMPARES (dupla com Ediwilson na volta); mantém início 09:00 real dele
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Realocado p/ diurno-ímpares (grade Jordan 08/07).', updated_at=now()
FROM employees e WHERE s.employee_id=e.id AND e.nome='ANTONIO CARLOS CASTRO GAMA'
  AND s.shift_date>=CURRENT_DATE AND s.shift_date<='2026-07-31' AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND month=7 AND year=2026),
  e.id, '593e86e5-7b3c-406c-a314-1ca80b03ec9f', d::date, '09:00', '21:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Diurno/dias ímpares (grade Jordan 08/07).', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='ANTONIO CARLOS CASTRO GAMA' AND EXTRACT(DAY FROM d)::int % 2 = 1;

-- c) Euler: até 21/07 assume o slot do Ediwilson (diurno-ímpares) no Mirante
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Cobertura correta = diurno (vaga Ediwilson) — grade Jordan 08/07.', updated_at=now()
FROM employees e WHERE s.employee_id=e.id AND e.nome='EULER FELIPE FERNANDES DA COSTA'
  AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND month=7 AND year=2026),
  e.id, '593e86e5-7b3c-406c-a314-1ca80b03ec9f', d::date, '07:00', '19:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'TEMP: cobre férias do Ediwilson (diurno-ímpares) até 21/07.', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-21'::date, '1 day') AS d
WHERE e.nome='EULER FELIPE FERNANDES DA COSTA' AND EXTRACT(DAY FROM d)::int % 2 = 1;

-- d) Francisco Ramon: FÉRIAS a partir de 22/07 (datas finais a registrar no DP) → turnos 22-31 cancelados
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | FÉRIAS a partir de 22/07 (Jordan 08/07; registrar datas no DP).', updated_at=now()
FROM employees e WHERE s.employee_id=e.id AND e.nome='FRANCISCO RAMON FARIAS DE SOUZA'
  AND s.shift_date>='2026-07-22' AND s.status='scheduled';

-- e) Euler: nova cobertura TEMP no Laranjeiras a partir de 22/07 (vaga do Francisco, diurno-pares)
INSERT INTO allocations (id, post_id, employee_id, status, start_date, is_primary, is_temporary,
                         role, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), 'a853d52a-594e-40e8-a168-f63d93d88e56', e.id, 'active', '2026-07-22', false, true,
       e.cargo, 'TEMP: cobre férias do Francisco Ramon no Laranjeiras a partir de 22/07 (Jordan 2026-07-08).', true, now(), now()
FROM employees e WHERE e.nome='EULER FELIPE FERNANDES DA COSTA'
  AND NOT EXISTS (SELECT 1 FROM allocations a WHERE a.employee_id=e.id AND a.post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND a.is_active);
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND month=7 AND year=2026),
  e.id, 'a853d52a-594e-40e8-a168-f63d93d88e56', d::date, '07:00', '19:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'TEMP: cobre férias do Francisco Ramon (diurno-pares) — Jordan 2026-07-08.', true, now(), now()
FROM employees e, generate_series('2026-07-22'::date, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='EULER FELIPE FERNANDES DA COSTA' AND EXTRACT(DAY FROM d)::int % 2 = 0;

-- f) Vaga do Alexandre = diurno/dias pares (nota no posto)
UPDATE posts SET notes=COALESCE(notes,'')||' | Vaga Alexandre Silva (definitivo, lugar do Marcelino): DIURNO/dias pares.', updated_at=now()
WHERE id='593e86e5-7b3c-406c-a314-1ca80b03ec9f';

-- g) Métricas
UPDATE scales s SET total_shifts=COALESCE(q.n,0), filled_shifts=COALESCE(q.n,0), total_hours=COALESCE(q.horas,0), updated_at=now()
FROM (SELECT sc.id AS sid,
        (SELECT count(*) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS n,
        (SELECT COALESCE(sum(sh.planned_hours),0) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS horas
      FROM scales sc WHERE sc.month=7 AND sc.year=2026) q
WHERE s.id=q.sid;
COMMIT;
SELECT 'grade Mirante 12x36', e.nome, CASE WHEN s.is_night_shift THEN 'noturno' ELSE 'diurno' END,
 CASE WHEN EXTRACT(DAY FROM min(s.shift_date))::int % 2 = 1 THEN 'impares' ELSE 'pares' END, min(s.shift_date), max(s.shift_date)
FROM shifts s JOIN employees e ON e.id=s.employee_id
WHERE s.post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND s.status='scheduled' AND s.planned_hours=12 AND s.shift_date>=CURRENT_DATE
GROUP BY e.nome, s.is_night_shift ORDER BY 3,4;
SELECT 'duplo-turno', count(*) FROM (SELECT employee_id, shift_date FROM shifts s JOIN scales sc ON sc.id=s.scale_id WHERE sc.month=7 AND sc.year=2026 AND s.status='scheduled' GROUP BY 1,2 HAVING count(*)>1) x;
