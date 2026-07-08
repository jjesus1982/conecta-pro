-- FORWARD — Replicação DP (employees.posto_atual_nome) → Operacional (allocations) — 2026-07-08
-- Ordem do Jordan: DP é a fonte; ajustar por posto. Exceção: ERIKA fica no LARANJEIRAS
-- (palavra explícita do Jordan 2026-07-07 — o texto do DP dela estava velho; corrigimos o DP).
-- Backup: conecta_pro_PRE_DP_REPLICA_20260708_085253.dump

BEGIN;

-- 0) Exceção Erika: atualizar o DP dela (MIRANTE estava desatualizado há 8+ meses)
UPDATE employees SET posto_atual_nome='LARANJEIRAS', updated_at=now()
WHERE id='6bf7804a-4976-44d2-aa3e-5bf1f25c3530' AND posto_atual_nome='MIRANTE';

-- 1) Mapa nome-DP → posto (ids confirmados no banco)
CREATE TEMP TABLE dp_map (dp_nome text PRIMARY KEY, post_id uuid);
INSERT INTO dp_map VALUES
 ('IDEAL FLORES',       '0baad2d9-5380-448d-85d9-691bd7f59681'),
 ('LARANJEIRAS',        'a853d52a-594e-40e8-a168-f63d93d88e56'),
 ('MIRANTE',            '593e86e5-7b3c-406c-a314-1ca80b03ec9f'),
 ('MICHELLANGELO',      (SELECT id FROM posts WHERE name='Condomínio Michelangelo' AND is_active)),
 ('PRIME',              (SELECT id FROM posts WHERE name='Condomínio Prime Arena' AND is_active)),
 ('VILLA DEI FIORI',    (SELECT id FROM posts WHERE name='Condomínio Villa Dei Fiori' AND is_active)),
 ('VILLA DOS PASSAROS', 'fdde51f0-a3a6-4668-9714-0b8548824c66');

-- 2) Semear o vínculo FK no DP (posto_atual_id) para todos os ativos com nome mapeado
UPDATE employees e SET posto_atual_id=m.post_id, updated_at=now()
FROM dp_map m
WHERE e.status='ativo' AND upper(trim(e.posto_atual_nome))=m.dp_nome
  AND (e.posto_atual_id IS DISTINCT FROM m.post_id);

-- 3) Corrigir alocações ativas divergentes (DP manda), preservando o par Mirante:
--    quem o DP diz MIRANTE e já está na "Portaria Principal - Mirante das Flores" fica lá.
UPDATE allocations a SET post_id=m.post_id,
  notes=COALESCE(a.notes,'') || ' | Replicação DP 2026-07-08: posto alinhado ao posto_atual_nome do DP.',
  updated_at=now()
FROM employees e, dp_map m
WHERE a.employee_id=e.id AND a.status='active' AND a.is_active
  AND e.status='ativo' AND upper(trim(e.posto_atual_nome))=m.dp_nome
  AND a.post_id <> m.post_id
  AND NOT (m.dp_nome='MIRANTE' AND a.post_id='669e64f1-9829-4c5f-a9c5-84b43e1dc1c3');

-- 4) Criar alocações para ativos com posto no DP e SEM alocação ativa
INSERT INTO allocations (id, post_id, employee_id, status, start_date, is_primary, is_temporary,
                         role, notes, is_active, created_at, updated_at)
SELECT gen_random_uuid(), m.post_id, e.id, 'active',
       COALESCE(e.data_inicio_posto::date, CURRENT_DATE), true, false,
       e.cargo, 'Criada 2026-07-08 replicando o DP (posto_atual_nome) — estava sem alocação.',
       true, now(), now()
FROM employees e JOIN dp_map m ON upper(trim(e.posto_atual_nome))=m.dp_nome
WHERE e.status='ativo'
  AND NOT EXISTS (SELECT 1 FROM allocations a WHERE a.employee_id=e.id AND a.status='active' AND a.is_active);

-- 5) Headcount real por posto (recalcular todos)
UPDATE posts p SET required_headcount=q.n, current_headcount=q.n, updated_at=now()
FROM (
  SELECT p2.id, count(a.id) FILTER (WHERE a.status='active' AND a.is_active AND e.status='ativo') AS n
  FROM posts p2 LEFT JOIN allocations a ON a.post_id=p2.id LEFT JOIN employees e ON e.id=a.employee_id
  GROUP BY p2.id
) q WHERE q.id=p.id;

COMMIT;

-- Conferência
SELECT p.name, p.required_headcount,
  (SELECT count(*) FROM allocations a JOIN employees e ON e.id=a.employee_id
   WHERE a.post_id=p.id AND a.status='active' AND a.is_active AND e.status='ativo') AS aloc_ativos
FROM posts p WHERE p.is_active ORDER BY p.name;
