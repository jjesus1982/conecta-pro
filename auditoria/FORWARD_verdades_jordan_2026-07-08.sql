-- FORWARD — Verdades do Jordan (fonte da verdade) — 2026-07-08
-- "Adeilson e Daniel são do Ideal Flores. Euler cobre férias do Ediwilson no Mirante. Jonathan cobre
--  férias+afastamento por acidente da Elen Nunes. Rene e Angela são do Villa Dei Fiori. Paulo é do
--  Mirante. Gelain é contrato de portaria remota (sem AGP). Afastadas que seguem: Cintia e Elen;
--  demais alocados não-ativos não são mais funcionários. Kalel já voltou (já estava ativo no sistema)."
BEGIN;

CREATE TEMP TABLE novos (nome_like text, dp_nome text, post_id uuid, temporario boolean, obs text);
INSERT INTO novos VALUES
 ('ADEILSON DINIZ DEODATO',          'IDEAL FLORES',    '0baad2d9-5380-448d-85d9-691bd7f59681', false, 'Lotação definida pelo Jordan 2026-07-08.'),
 ('DANIEL SOUZA DOS SANTOS',         'IDEAL FLORES',    '0baad2d9-5380-448d-85d9-691bd7f59681', false, 'Lotação definida pelo Jordan 2026-07-08.'),
 ('EULER FELIPE FERNANDES DA COSTA', 'MIRANTE',         '593e86e5-7b3c-406c-a314-1ca80b03ec9f', true,  'Cobertura de férias do EDIWILSON (líder Mirante) — ordem Jordan 2026-07-08.'),
 ('JONATHAN DO NASCIMENTO MENDES',   'MIRANTE',         '593e86e5-7b3c-406c-a314-1ca80b03ec9f', true,  'Cobre férias + afastamento por acidente da ELEN NUNES — ordem Jordan 2026-07-08.'),
 ('RENE RICARDO CRUZ GONÇALVES',     'VILLA DEI FIORI', (SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active), false, 'Lotação definida pelo Jordan 2026-07-08.'),
 ('ANGELA LOPES MACEDO',             'VILLA DEI FIORI', (SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active), false, 'Lotação definida pelo Jordan 2026-07-08.'),
 ('PAULO DA SILVA LAMEGO',           'MIRANTE',         '593e86e5-7b3c-406c-a314-1ca80b03ec9f', false, 'Lotação definida pelo Jordan 2026-07-08.');

-- 1) DP: lotação (nome + FK)
UPDATE employees e SET posto_atual_nome=n.dp_nome, posto_atual_id=n.post_id, updated_at=now()
FROM novos n WHERE e.nome=n.nome_like AND e.status='ativo';

-- 2) Operacional: alocações (não existiam)
INSERT INTO allocations (id, post_id, employee_id, status, start_date, is_primary, is_temporary,
                         role, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), n.post_id, e.id, 'active', CURRENT_DATE, NOT n.temporario, n.temporario,
       e.cargo, n.obs, true, now(), now()
FROM novos n JOIN employees e ON e.nome=n.nome_like AND e.status='ativo'
WHERE NOT EXISTS (SELECT 1 FROM allocations a WHERE a.employee_id=e.id AND a.status='active' AND a.is_active);

-- 3) Encerrar alocações de quem "não é mais funcionário" (mantém Cintia e Elen — afastadas com vaga)
UPDATE allocations a SET status='terminated', is_active=false, end_date=CURRENT_DATE,
  termination_reason='Não é mais funcionário (ordem Jordan 2026-07-08).', updated_at=now()
FROM employees e
WHERE a.employee_id=e.id AND a.status='active' AND a.is_active
  AND e.status IN ('demitido','inativo')
  AND e.nome IN ('LORINALDO OLIVEIRA DA SILVA','MARCELINO AURISMAR DA SILVA','MARTA DA SILVA PINHEIRO',
                 'THAIS FERREIRA MATOS','FERNANDA VINHOTE MACIEL','RAILSON ASSUNÇÃO LIMA');

-- 4) Gelain: contrato de portaria remota (sem AGP presencial)
UPDATE posts SET post_type='monitoramento',
  notes=COALESCE(notes,'')||' | 2026-07-08 (Jordan): contrato de PORTARIA REMOTA — sem AGP presencial; quadro presencial 0.',
  updated_at=now()
WHERE id='7e548218-ff82-4ce0-a026-e315c97643d5';

-- 5) Headcount real por posto (todos)
UPDATE posts p SET required_headcount=q.n, current_headcount=q.n, updated_at=now()
FROM (SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
      FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id
      GROUP BY p2.id) q
WHERE q.id=p.id;

COMMIT;

SELECT p.name, p.required_headcount FROM posts p WHERE p.is_active ORDER BY p.name;
SELECT 'ativos sem alocação', count(*) FROM employees e WHERE e.status='ativo'
  AND NOT EXISTS (SELECT 1 FROM allocations a WHERE a.employee_id=e.id AND a.status='active' AND a.is_active);
