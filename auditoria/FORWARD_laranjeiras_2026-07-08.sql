-- FORWARD — Posto 2/9 LARANJEIRAS (respostas do Jordan, 2026-07-08)
BEGIN;
-- 1) Eidy → VILLA DEI FIORI (no lugar da Cintia afastada) — leva os turnos noturnos dela
UPDATE allocations a SET post_id=(SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active),
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): no Villa Dei Fiori no lugar da Cintia (afastada).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='EIDY CULIER DE CASTRO' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='VILLA DEI FIORI', posto_atual_id=(SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active), updated_at=now()
WHERE nome='EIDY CULIER DE CASTRO';
UPDATE shifts s SET post_id=(SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active),
  scale_id=(SELECT sc.id FROM scales sc JOIN posts p ON p.id=sc.post_id WHERE p.name='Condomínio Villa Dei Fiori' AND sc.month=7 AND sc.year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Villa Dei Fiori (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='EIDY CULIER DE CASTRO' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 2) Francisco Ramon → LARANJEIRAS (diurno, dias pares = padrão real de batidas dele)
UPDATE allocations a SET post_id='a853d52a-594e-40e8-a168-f63d93d88e56',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): Francisco Ramon é do Laranjeiras (diurno).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='FRANCISCO RAMON FARIAS DE SOUZA' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='LARANJEIRAS', posto_atual_id='a853d52a-594e-40e8-a168-f63d93d88e56', updated_at=now()
WHERE nome='FRANCISCO RAMON FARIAS DE SOUZA';
UPDATE shifts s SET post_id='a853d52a-594e-40e8-a168-f63d93d88e56',
  scale_id=(SELECT id FROM scales WHERE post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND month=7 AND year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Laranjeiras (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='FRANCISCO RAMON FARIAS DE SOUZA' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 3) Jonathan é NOTURNO (dias pares — completa o par do Anilson): troca a partir de hoje
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Corrigido p/ noturno (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='JONATHAN DO NASCIMENTO MENDES' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026
  AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND month=7 AND year=2026),
  e.id, 'a853d52a-594e-40e8-a168-f63d93d88e56', d::date, '18:00', '06:00', 60,
  'scheduled', false, true, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Noturno/dias pares (Jordan 2026-07-08) — cobre a Elen.', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='JONATHAN DO NASCIMENTO MENDES' AND EXTRACT(DAY FROM d)::int % 2 = 0;

-- 4) Erika (líder) → 12x36 diurno/dias ímpares (PROVISÓRIO — confirmar turno)
UPDATE shifts s SET status='cancelled', notes=COALESCE(s.notes,'')||' | Líder passa a 12x36 (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='ERIKA CRISTINA MAQUINE PEREIRA' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026
  AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND month=7 AND year=2026),
  e.id, 'a853d52a-594e-40e8-a168-f63d93d88e56', d::date, '07:00', '19:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Líder em 12x36 diurno/dias ímpares — PROVISÓRIO, confirmar turno com Jordan (2026-07-08).', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='ERIKA CRISTINA MAQUINE PEREIRA' AND EXTRACT(DAY FROM d)::int % 2 = 1;

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
SELECT 'grade Laranjeiras', e.nome, CASE WHEN s.is_night_shift THEN 'noturno' ELSE 'diurno' END,
 CASE WHEN EXTRACT(DAY FROM min(s.shift_date))::int % 2 = 1 THEN 'impares' ELSE 'pares' END
FROM shifts s JOIN employees e ON e.id=s.employee_id
WHERE s.post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND s.status='scheduled' AND s.planned_hours=12 AND s.shift_date>=CURRENT_DATE
GROUP BY e.nome, s.is_night_shift ORDER BY 3,4;
SELECT 'duplo-turno', count(*) FROM (SELECT employee_id, shift_date FROM shifts s JOIN scales sc ON sc.id=s.scale_id WHERE sc.month=7 AND sc.year=2026 AND s.status='scheduled' GROUP BY 1,2 HAVING count(*)>1) x;
