-- FORWARD 3 — Verdades do Jordan (Mirante) — 2026-07-08
-- "Malaquias está no Prime Arena. Mirante: 6 AGPs (Ailton, Gama, Ediwilson, Eduardo, Mauricio +
--  vaga do Marcelino — Alexandre Silva em contratação) e 3 ASGs (Telma, Paulo, Vanderlice).
--  AGPs em 12x36; ASGs em 44h."
BEGIN;

-- 1) Malaquias → Prime Arena (alocação + DP + turnos de julho)
UPDATE allocations a SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): Malaquias é do Prime Arena.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='MALAQUIAS PEREIRA FERREIRA' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='PRIME', posto_atual_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active), updated_at=now()
WHERE nome='MALAQUIAS PEREIRA FERREIRA';
UPDATE shifts s SET post_id=(SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active),
  scale_id=(SELECT sc.id FROM scales sc JOIN posts p ON p.id=sc.post_id WHERE p.name='Condomínio Prime Arena' AND sc.month=7 AND sc.year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Prime Arena (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='MALAQUIAS PEREIRA FERREIRA' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 2) Telma e Vanderlice → Condomínio Mirante das Flores (equipe de limpeza do Mirante junto do Paulo)
UPDATE allocations a SET post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): equipe de limpeza do Mirante (Telma/Paulo/Vanderlice).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome IN ('TELMA MARIA LAGES MEIRA','VANDERLICE SANTOS DA SILVA')
  AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f', updated_at=now()
WHERE nome IN ('TELMA MARIA LAGES MEIRA','VANDERLICE SANTOS DA SILVA') AND status='ativo';
UPDATE shifts s SET post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f',
  scale_id=(SELECT id FROM scales WHERE post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND month=7 AND year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Cond. Mirante (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome IN ('TELMA MARIA LAGES MEIRA','VANDERLICE SANTOS DA SILVA')
  AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026 AND s.status='scheduled';

-- 3) Ediwilson é AGP (palavra do Jordan): na volta (22/07+) sai do comercial e entra no 12x36
--    diurno/dias ímpares 07:00-19:00 (lacuna real de cobertura do Mirante; PROVISÓRIO — confirmar turno).
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | Substituído por 12x36 na volta das férias (AGP — Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc0
WHERE s.employee_id=e.id AND e.nome='EDIWILSON CORREA MARQUES' AND s.scale_id=sc0.id AND sc0.month=7 AND sc0.year=2026
  AND s.shift_date>='2026-07-22' AND s.status='scheduled';
INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, planned_start_time, planned_end_time,
  planned_break_minutes, status, is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
  planned_hours, actual_hours, overtime_hours, night_hours, base_pay, overtime_pay, night_bonus, holiday_bonus,
  total_pay, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(),
  (SELECT id FROM scales WHERE post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND month=7 AND year=2026),
  e.id, '593e86e5-7b3c-406c-a314-1ca80b03ec9f', d::date, '07:00', '19:00', 60,
  'scheduled', false, false, false, false, false, 12, 0,0,0,0,0,0,0,0,
  'Volta de férias como AGP 12x36 diurno/dias ímpares — PROVISÓRIO, confirmar turno com Jordan (2026-07-08).',
  true, now(), now()
FROM employees e, generate_series('2026-07-22'::date, '2026-07-31'::date, '1 day') AS d
WHERE e.nome='EDIWILSON CORREA MARQUES' AND EXTRACT(DAY FROM d)::int % 2 = 1;

-- 4) Quadro do Mirante definido pelo Jordan: 6 AGP + 3 ASG = 9 (required fixo; current = real)
UPDATE posts p SET current_headcount=q.n, updated_at=now()
FROM (SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
      FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id
      GROUP BY p2.id) q
WHERE q.id=p.id;
UPDATE posts SET required_headcount=current_headcount WHERE is_active AND id<>'593e86e5-7b3c-406c-a314-1ca80b03ec9f';
UPDATE posts SET required_headcount=9,
  notes=COALESCE(notes,'')||' | Quadro definido pelo Jordan 2026-07-08: 6 AGP + 3 ASG (vaga aberta: substituto do Marcelino — Alexandre Silva em contratação).',
  updated_at=now()
WHERE id='593e86e5-7b3c-406c-a314-1ca80b03ec9f';

-- 5) Métricas das escalas de julho (não-cancelados)
UPDATE scales s SET total_shifts=COALESCE(q.n,0), filled_shifts=COALESCE(q.n,0), total_hours=COALESCE(q.horas,0), updated_at=now()
FROM (SELECT sc.id AS sid,
        (SELECT count(*) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS n,
        (SELECT COALESCE(sum(sh.planned_hours),0) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS horas
      FROM scales sc WHERE sc.month=7 AND sc.year=2026) q
WHERE s.id=q.sid;

COMMIT;

-- Conferências
SELECT 'MIRANTE quadro', p.required_headcount, p.current_headcount FROM posts p WHERE p.id='593e86e5-7b3c-406c-a314-1ca80b03ec9f';
SELECT 'Mirante pessoas', e.nome, e.cargo FROM allocations a JOIN employees e ON e.id=a.employee_id
WHERE a.post_id='593e86e5-7b3c-406c-a314-1ca80b03ec9f' AND a.status='active' AND a.is_active ORDER BY e.cargo, e.nome;
SELECT 'Portaria Principal restante', count(*) FROM allocations a WHERE a.post_id='669e64f1-9829-4c5f-a9c5-84b43e1dc1c3' AND a.status='active' AND a.is_active;
SELECT 'duplo-turno', count(*) FROM (SELECT employee_id, shift_date FROM shifts s JOIN scales sc ON sc.id=s.scale_id WHERE sc.month=7 AND sc.year=2026 AND s.status='scheduled' GROUP BY 1,2 HAVING count(*)>1) x;
