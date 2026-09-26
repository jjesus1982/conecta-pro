BEGIN;
-- Régua dada pelo dono em 25/09/2026: CLIENTE = CONTRATO ASSINADO.
-- (A régua anterior, "quem recebeu nota", não cobria contrato assinado sem nota emitida ainda —
--  é o caso do Smart Tower Itapuranga e da Hawk Eye.)

-- PERDEMOS — palavra do dono, um a um
UPDATE clients SET status='churned', ativo=false, updated_at=now()
WHERE status='active' AND unaccent(upper(name)) IN (
  'ASSOCIACAO BRASIL SGI',
  'CONDOMINIO RESIDENCIAL SMILE PARQUE DAS FLORES',
  'GRUPO PARVI',
  'RACAO CONFIANCA AGROINDUSTRIAL LTDA',
  'VEGA MANAUS TRANSPORTE DE PASSAGEIROS LTDA');

-- EM NEGOCIAÇÃO — sem contrato assinado, logo não é cliente. Seguem no funil.
UPDATE clients SET status='prospect', updated_at=now()
WHERE status='active' AND unaccent(upper(name)) IN (
  'CONDOMINIO BOSQUE RESIDENCIAL KOPENHAGEN',       -- análise de contrato
  'CONDOMINIO DO CONJUNTO DOS JORNALISTAS',         -- análise de proposta
  'CONDOMINIO RESIDENCIAL PRAIA DOS PASSARINHOS',   -- análise de proposta
  'CONDOMINIO RESIDENCIAL THE SUN',                 -- falta enviar proposta formalizada
  'CONDOMINIO DO EDIFICIO RIO JAGUARIBE',           -- análise de proposta
  'CONDOMINIO PARK VILLAGE');                       -- ⚠️ proposta APROVADA, assina em dezembro

-- Park Village: ganho, mas o contrato atual do concorrente encerra 25/12 e o nosso vale de
-- 26/12 em diante. Guardo a data para ninguém tratar como perdido.
UPDATE clients SET contract_start_date = DATE '2026-12-26', updated_at=now()
WHERE unaccent(upper(name)) = 'CONDOMINIO PARK VILLAGE'
  AND EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_name='clients' AND column_name='contract_start_date');
COMMIT;
