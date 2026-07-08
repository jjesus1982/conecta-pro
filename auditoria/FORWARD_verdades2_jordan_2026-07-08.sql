-- FORWARD 2 — Verdades do Jordan (2026-07-08, parte 2)
-- "Elen é do Laranjeiras Village; Cintia é do Villa Dei Fiori (manter assim, ajustar DP/módulos).
--  Ediwilson: férias de 03/07 até dia 21 (acabam dia 22, quando ele JÁ ESTÁ no posto Mirante)."
BEGIN;

-- 1) Elen (afastada): vaga no LARANJEIRAS (DP já dizia; a alocação estava no Mirante)
UPDATE allocations a SET post_id='a853d52a-594e-40e8-a168-f63d93d88e56',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): vaga é no Laranjeiras Village.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='ELEN XAVIER NUNES' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_id='a853d52a-594e-40e8-a168-f63d93d88e56', updated_at=now()
WHERE nome='ELEN XAVIER NUNES';

-- 2) Cintia (afastada): vaga no VILLA DEI FIORI
UPDATE allocations a SET post_id=(SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active),
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): vaga é no Villa Dei Fiori.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='CINTIA BEZERRA OLIVEIRA' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_id=(SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active), updated_at=now()
WHERE nome='CINTIA BEZERRA OLIVEIRA';

-- 3) Jonathan cobre a vaga da Elen → vai junto pro LARANJEIRAS
UPDATE allocations a SET post_id='a853d52a-594e-40e8-a168-f63d93d88e56',
  notes=COALESCE(a.notes,'')||' | 2026-07-08 (Jordan): cobre a Elen — vaga dela é no Laranjeiras.', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='JONATHAN DO NASCIMENTO MENDES' AND a.status='active' AND a.is_active;
UPDATE employees SET posto_atual_nome='LARANJEIRAS', posto_atual_id='a853d52a-594e-40e8-a168-f63d93d88e56', updated_at=now()
WHERE nome='JONATHAN DO NASCIMENTO MENDES' AND status='ativo';

-- 4) Cobertura do Euler termina quando o Ediwilson volta (22/07 ele já está no posto)
UPDATE allocations a SET end_date='2026-07-21',
  notes=COALESCE(a.notes,'')||' | Cobertura até 21/07 — Ediwilson retorna 22/07 (Jordan).', updated_at=now()
FROM employees e WHERE a.employee_id=e.id AND e.nome='EULER FELIPE FERNANDES DA COSTA' AND a.status='active' AND a.is_active;

-- 5) Férias do Ediwilson no DP (03/07→21/07, retorno 22/07): registro APROVADO (fato em curso)
INSERT INTO hr_vacation_requests (id, condominio_id, employee_id, status, request_code,
  start_date, end_date, return_date, days_requested, sell_days, advance_13th,
  internal_notes, created_at, updated_at)
SELECT gen_random_uuid(), 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', e.id, 'APPROVED',
  'FER-2026-EDIW-JUL', '2026-07-03', '2026-07-21', '2026-07-22', 19, 0, false,
  'Registrado 2026-07-08 por ordem do Jordan: "férias acabam dia 22 e dia 22 ele já estará no posto Mirante das Flores".',
  now(), now()
FROM employees e WHERE e.nome='EDIWILSON CORREA MARQUES'
  AND NOT EXISTS (SELECT 1 FROM hr_vacation_requests h WHERE h.request_code='FER-2026-EDIW-JUL');

-- 6) Turnos do Ediwilson durante as férias (03-21/07): cancelados como férias (honesto)
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | FÉRIAS 03-21/07 (Jordan 2026-07-08).', updated_at=now()
FROM employees e, scales sc
WHERE s.employee_id=e.id AND e.nome='EDIWILSON CORREA MARQUES'
  AND s.scale_id=sc.id AND sc.month=7 AND sc.year=2026
  AND s.shift_date BETWEEN '2026-07-03' AND '2026-07-21' AND s.status='scheduled';

-- 7) Turnos do Euler a partir de 22/07: fim da cobertura
UPDATE shifts s SET status='cancelled',
  notes=COALESCE(s.notes,'')||' | Fim da cobertura de férias em 21/07 (Ediwilson retorna 22/07).', updated_at=now()
FROM employees e, scales sc
WHERE s.employee_id=e.id AND e.nome='EULER FELIPE FERNANDES DA COSTA'
  AND s.scale_id=sc.id AND sc.month=7 AND sc.year=2026
  AND s.shift_date >= '2026-07-22' AND s.status='scheduled';

-- 8) Turnos do Jonathan em julho: mover do Mirante p/ Laranjeiras (mesma escala mensal do posto novo)
UPDATE shifts s SET post_id='a853d52a-594e-40e8-a168-f63d93d88e56',
  scale_id=(SELECT id FROM scales WHERE post_id='a853d52a-594e-40e8-a168-f63d93d88e56' AND month=7 AND year=2026),
  notes=COALESCE(s.notes,'')||' | Movido p/ Laranjeiras (vaga da Elen) — Jordan 2026-07-08.', updated_at=now()
FROM employees e, scales sc
WHERE s.employee_id=e.id AND e.nome='JONATHAN DO NASCIMENTO MENDES'
  AND s.scale_id=sc.id AND sc.month=7 AND sc.year=2026 AND s.status='scheduled';

-- 9) Métricas das escalas (contando só não-cancelados) + headcount real
UPDATE scales s SET total_shifts=COALESCE(q.n,0), filled_shifts=COALESCE(q.n,0), total_hours=COALESCE(q.horas,0), updated_at=now()
FROM (SELECT sc.id AS sid,
        (SELECT count(*) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS n,
        (SELECT COALESCE(sum(sh.planned_hours),0) FROM shifts sh WHERE sh.scale_id=sc.id AND sh.is_active AND sh.status<>'cancelled') AS horas
      FROM scales sc WHERE sc.month=7 AND sc.year=2026) q
WHERE s.id=q.sid;

UPDATE posts p SET required_headcount=q.n, current_headcount=q.n, updated_at=now()
FROM (SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
      FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id
      GROUP BY p2.id) q
WHERE q.id=p.id;

COMMIT;

SELECT 'ferias registrada', request_code, status, start_date, end_date, return_date FROM hr_vacation_requests WHERE request_code='FER-2026-EDIW-JUL';
SELECT 'ediwilson turnos ferias cancelados', count(*) FROM shifts s JOIN employees e ON e.id=s.employee_id WHERE e.nome='EDIWILSON CORREA MARQUES' AND s.status='cancelled' AND s.shift_date BETWEEN '2026-07-03' AND '2026-07-21';
SELECT 'jonathan turnos no laranjeiras', count(*) FROM shifts s JOIN employees e ON e.id=s.employee_id WHERE e.nome='JONATHAN DO NASCIMENTO MENDES' AND s.post_id='a853d52a-594e-40e8-a168-f63d93d88e56';
SELECT 'vagas', p.name, p.required_headcount FROM posts p WHERE p.name ~* 'laranjeiras|dei fiori|mirante das flores' AND p.is_active ORDER BY p.name;
