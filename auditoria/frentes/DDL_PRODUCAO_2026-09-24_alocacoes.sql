-- ============================================================================
-- PRODUÇÃO — 24/09/2026 — Alocações e acessos de quem saiu
-- Autorizações explícitas do Jordan no chat, nesta ordem:
--   «pode desligar as duas e tirar a meire da alocação»
--   «encerra as três e a minha também»
--
-- COMO APAREceu: depois do bake da onda fiscal rodei a bateria de travas.
-- `checar_acesso_de_quem_saiu.py` foi de 0 para 2 e `checar_alocacao_de_quem_saiu.py`
-- de 0 para 1. Ao investigar, a trava de alocação estava CEGA: lia só
-- `employee_alocacoes` e a casa tem DUAS tabelas de alocação vivas.
--
--   allocations .......... 89 linhas, 69 ativas, 67 pessoas — importada por 69 módulos
--   employee_alocacoes ... 73 linhas, 51 ativas, 51 pessoas — importada por 21 módulos
--
-- Corrigida a trava para ler as duas, o número foi de 1 para 5.
-- ============================================================================

-- 1) Contas de quem saiu (users.is_active). Nada apagado; o histórico fica.
UPDATE users SET is_active = false, updated_at = now()
 WHERE email IN ('meiregabriellasilvah07@gmail.com', 'elizielgonzagaf@gmail.com');

-- 2) Meire — demitida 18/09. Precisou das DUAS tabelas: encerrei em `allocations` e ela
--    seguia ativa em `employee_alocacoes`. Foi a trava corrigida que mostrou.
UPDATE allocations SET status='ended', is_active=false, end_date=DATE '2026-09-18', ...
 WHERE id = 'e9aee5f6-5c98-4e08-bb65-0ffafe8b185f';
UPDATE employee_alocacoes SET ativo=false, data_fim=DATE '2026-09-18',
       motivo_encerramento='Desligamento 18/09/2026'
  FROM employees e WHERE e.id=employee_alocacoes.employee_id AND e.nome ILIKE '%MEIRE GABRIELA%';

-- 3) Os três demitidos há 31 e 64 dias, ainda alocados em `allocations`.
--    `end_date` = a DEMISSÃO, não hoje: datar hoje inventaria dias de cobertura que não
--    existiram, e é esse número que alimenta faturamento e alarme de posto descoberto.
--      DANIEL SOUZA DOS SANTOS        demitido 24/08  Ideal Flores    (31 dias)
--      FERNANDO MIGUEL GOMES DA SILVA demitido 22/07  Michelangelo    (64 dias)
--      JONATHAN DO NASCIMENTO MENDES  demitido 22/07  Laranjeiras     (64 dias)
UPDATE allocations a SET status='ended', is_active=false, end_date=e.data_demissao, ...
  FROM employees e WHERE e.id=a.employee_id
   AND a.id IN ('c0e6081d-62e2-47d1-93d1-db550c8cff4e',
                '7f790400-b433-4b86-bca5-6b918a93d67c',
                '874f93c4-f554-4a59-91e5-ea4da7d4d4df');

-- 4) O próprio dono, status `candidato`, alocado em posto de CLIENTE desde 19/07.
--    Sem demissão para datar: encerra hoje, e o motivo diz o que era.
UPDATE allocations SET status='ended', is_active=false, end_date=CURRENT_DATE, ...
 WHERE id = '76ba036c-c0c3-4be6-bb24-f25a006d4b95';

-- ============================================================================
-- EFEITO MEDIDO — efetivo alocado por cliente, antes → depois
--
--   Ideal Flores ....... 14 → 13   (o dono confirmou: são 13. BATEU)
--   Laranjeiras ........ 10 →  9   (a planilha dele diz 8 — sobra 1, em aberto)
--   Villa Dei Fiori .....  8 →  7
--   Michelangelo ........  3 →  2
--   Prime Arena .........  4 →  4   (a realidade são 8 — FALTAM 4 sem alocação)
--   Mirante .............  9 →  9
--   Villa Pássaros ......  5 →  5
--   Green Hills .........  1 →  1
--
--   checar_alocacao_de_quem_saiu.py:  5 → 0
--   checar_acesso_de_quem_saiu.py:    2 → 0
--
-- O QUE SOBRA, e é do dono com a frente AA6:
--   · Prime Arena tem 4 pessoas trabalhando SEM alocação registrada. Gente sem alocação
--     some da cobertura do posto, do custo do contrato e da dedução do INSS.
--   · Laranjeiras tem 1 a mais que a planilha.
--   · O dono avisou: «tem muita rotatividade, não só lá mas em todos os condomínios,
--     sempre fica defasado». Contagem de cabeças é dado que apodrece — a apuração de
--     VA/VT passa a sair de QUEM BATEU PONTO no posto, não de quem tem linha de alocação.
-- ============================================================================
