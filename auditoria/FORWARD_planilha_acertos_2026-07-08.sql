-- FORWARD — Acertos da planilha oficial (Jordan, 2026-07-08)
BEGIN;
-- 1) Adeilson: NOTURNO no Ideal (P1 à noite) — batidas confirmam (saída ~05h)
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Corrigido p/ noturno (planilha+Jordan 08/07).', updated_at=now()
FROM employees e WHERE s.employee_id=e.id AND e.nome='ADEILSON DINIZ DEODATO' AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='0baad2d9-5380-448d-85d9-691bd7f59681' AND month=7 AND year=2026),
  e.id, '0baad2d9-5380-448d-85d9-691bd7f59681', d::date, '18:00', '06:00', 60,
  'scheduled', false, true, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'P1 noturno/dias ímpares (planilha oficial + Jordan 08/07).', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='ADEILSON DINIZ DEODATO' AND EXTRACT(DAY FROM d)::int % 2 = 1;

-- 2) Keyson → PRIME ARENA diurno (planilha)
UPDATE allocations a SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan/planilha): migrou p/ Prime Arena (diurno).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='KEYSON DA SILVA PINTO' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='PRIME', posto_atual_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active), updated_at=now()
WHERE nome='KEYSON DA SILVA PINTO';
UPDATE shifts s SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  scale_id=(SELECT sc.id FROM scales sc JOIN posts p ON p.id=sc.post_id WHERE p.name='Condomínio Prime Arena' AND sc.month=7 AND sc.year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Prime (Jordan/planilha 08/07).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='KEYSON DA SILVA PINTO' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 3) Oscar → VILLA DOS PÁSSAROS (planilha)
UPDATE allocations a SET post_id='fdde51f0-a3a6-4668-9714-0b8548824c66',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan/planilha): migrou p/ Villa dos Pássaros.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='OSCAR SOARES DA COSTA FILHO' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='VILLA DOS PASSAROS', posto_atual_id='fdde51f0-a3a6-4668-9714-0b8548824c66', updated_at=now()
WHERE nome='OSCAR SOARES DA COSTA FILHO';
UPDATE shifts s SET post_id='fdde51f0-a3a6-4668-9714-0b8548824c66',
  scale_id=(SELECT id FROM scales WHERE post_id='fdde51f0-a3a6-4668-9714-0b8548824c66' AND month=7 AND year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Villa dos Pássaros (Jordan/planilha 08/07).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='OSCAR SOARES DA COSTA FILHO' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 4) Euler: papel registrado = TIRADOR DE FÉRIAS (volante entre postos)
UPDATE allocations a SET role='AGP — TIRADOR DE FÉRIAS (volante)',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): Euler é tirador de férias — cobre férias em todos os postos.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='EULER FELIPE FERNANDES DA COSTA' AND a.is_active;

-- 5) Quadros + métricas
UPDATE posts p SET current_headcount=q.n, updated_at=now()
FROM (SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
      FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id GROUP BY p2.id) q
WHERE q.id=p.id;
UPDATE posts SET required_headcount=current_headcount WHERE is_active AND id NOT IN ('593e86e5-7b3c-406c-a314-1ca80b03ec9f','0baad2d9-5380-448d-85d9-691bd7f59681');
UPDATE scales s SET total_shifts=COALESCE(q.n,0), filled_shifts=COALESCE(q.n,0), total_hours=COALESCE(q.horas,0), updated_at=now()
FROM (SELECT sc.id AS sid,
        (SELECT count(*) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS n,
        (SELECT COALESCE(sum(sh.planned_hours),0) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS horas
      FROM scales sc WHERE sc.month=7 AND sc.year=2026) q
WHERE s.id=q.sid;
COMMIT;
-- Grades resultantes (Prime e Ideal)
SELECT 'PRIME', e.nome, CASE WHEN s.is_night_shift THEN 'noturno' ELSE 'diurno' END,
 CASE WHEN EXTRACT(DAY FROM min(s.shift_date))::int % 2 = 1 THEN 'imp' ELSE 'par' END
FROM shifts s JOIN employees e ON e.id=s.employee_id JOIN posts p ON p.id=s.post_id
WHERE p.name='Condomínio Prime Arena' AND s.status='scheduled' AND s.planned_hours=12 AND s.shift_date>=CURRENT_DATE
GROUP BY e.nome, s.is_night_shift ORDER BY 3,4;
SELECT 'IDEAL noturno', e.nome, CASE WHEN EXTRACT(DAY FROM min(s.shift_date))::int % 2 = 1 THEN 'imp' ELSE 'par' END
FROM shifts s JOIN employees e ON e.id=s.employee_id
WHERE s.post_id='0baad2d9-5380-448d-85d9-691bd7f59681' AND s.status='scheduled' AND s.is_night_shift AND s.shift_date>=CURRENT_DATE
GROUP BY e.nome ORDER BY 2;
SELECT 'duplo-turno', count(*) FROM (SELECT employee_id, shift_date FROM shifts s JOIN scales sc ON sc.id=s.scale_id WHERE sc.month=7 AND sc.year=2026 AND s.status='scheduled' GROUP BY 1,2 HAVING count(*)>1) x;
