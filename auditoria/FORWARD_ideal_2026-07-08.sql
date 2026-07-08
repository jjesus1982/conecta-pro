-- FORWARD — Posto 1/9 IDEAL FLORES (respostas do Jordan, 2026-07-08)
BEGIN;
-- 1) Antonio Diniz Assis → PRIME ARENA (há ~1 ano; erro de atualização)
UPDATE allocations a SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): no Prime Arena há ~1 ano — correção de cadastro.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='ANTONIO DINIZ ASSIS DOS SANTOS' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='PRIME', posto_atual_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active), updated_at=now()
WHERE nome='ANTONIO DINIZ ASSIS DOS SANTOS';
UPDATE shifts s SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  scale_id=(SELECT sc.id FROM scales sc JOIN posts p ON p.id=sc.post_id WHERE p.name='Condomínio Prime Arena' AND sc.month=7 AND sc.year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Prime Arena (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='ANTONIO DINIZ ASSIS DOS SANTOS' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 2) Antonio Walcicley (líder) → 12x36 (sai do comercial a partir de hoje)
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | Líder passa a 12x36 (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='ANTONIO WALCICLEY PEREIRA DA SILVA' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026
  AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), (SELECT id FROM scales WHERE post_id='0baad2d9-5380-448d-85d9-691bd7f59681' AND month=7 AND year=2026),
  e.id, '0baad2d9-5380-448d-85d9-691bd7f59681', d::date, '07:00', '19:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Líder em 12x36 diurno/dias pares — PROVISÓRIO, confirmar turno com Jordan (2026-07-08).', true, now(), now()
FROM employees e, generate_series(CURRENT_DATE, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='ANTONIO WALCICLEY PEREIRA DA SILVA' AND EXTRACT(DAY FROM d)::int % 2 = 0;

-- 3) Sebastião: fora do Ideal; experiência vence 22/07, dispensa programada
UPDATE allocations a SET status='terminated', is_active=false, end_date=CURRENT_DATE,
  termination_reason='Fora do Ideal; contrato de experiência vence 22/07 — dispensa programada (Jordan 2026-07-08).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='SEBASTIAO LIMA DE FREITAS' AND a.status='active' AND a.is_active;
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | Desligado do Ideal (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='SEBASTIAO LIMA DE FREITAS' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026
  AND s.shift_date>=CURRENT_DATE AND s.status='scheduled';

-- 4) Quadros: Ideal required=12 (11 atuais + vaga artífice em teste); Prime segue current
UPDATE posts p SET current_headcount=q.n, updated_at=now()
FROM (SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
      FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id GROUP BY p2.id) q
WHERE q.id=p.id;
UPDATE posts SET required_headcount=current_headcount WHERE is_active AND id NOT IN ('593e86e5-7b3c-406c-a314-1ca80b03ec9f','0baad2d9-5380-448d-85d9-691bd7f59681');
UPDATE posts SET required_headcount=current_headcount+1,
  notes=COALESCE(notes,'')||' | 2026-07-08 (Jordan): vaga de ARTÍFICE em fase de teste (substituto do Sebastião).', updated_at=now()
WHERE id='0baad2d9-5380-448d-85d9-691bd7f59681';

-- 5) Métricas das escalas
UPDATE scales s SET total_shifts=COALESCE(q.n,0), filled_shifts=COALESCE(q.n,0), total_hours=COALESCE(q.horas,0), updated_at=now()
FROM (SELECT sc.id AS sid,
        (SELECT count(*) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS n,
        (SELECT COALESCE(sum(sh.planned_hours),0) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS horas
      FROM scales sc WHERE sc.month=7 AND sc.year=2026) q
WHERE s.id=q.sid;
COMMIT;
SELECT 'IDEAL', required_headcount, current_headcount FROM posts WHERE id='0baad2d9-5380-448d-85d9-691bd7f59681';
SELECT 'PRIME', required_headcount, current_headcount FROM posts WHERE name='Condomínio Prime Arena' AND is_active;
SELECT 'duplo-turno', count(*) FROM (SELECT employee_id, shift_date FROM shifts s JOIN scales sc ON sc.id=s.scale_id WHERE sc.month=7 AND sc.year=2026 AND s.status='scheduled' GROUP BY 1,2 HAVING count(*)>1) x;
