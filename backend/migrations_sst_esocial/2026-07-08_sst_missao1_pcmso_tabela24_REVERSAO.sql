-- ============================================================================
-- MIGRATION REVERSAO — Missão 1 SST/MB (PDFs reais → dado estruturado)
-- Reverte: 2026-07-08_sst_missao1_pcmso_tabela24_FORWARD.sql
-- ATENÇÃO: perde o registro real do PCMSO e os enquadramentos Tabela 24 —
-- restaurar do backup (backup_pre_missao1_2026-07-08_gp_risks_gp_asos.sql)
-- se necessário voltar ao estado exato.
-- ============================================================================

BEGIN;

-- 1. Remove os 4 riscos novos (fonte: laudos MB) — risk_ids fixos da FORWARD
DELETE FROM gp_risks WHERE risk_id IN (
    'a1b5f0e1-2026-0708-9001-000000000001',
    'a1b5f0e1-2026-0708-9002-000000000002',
    'a1b5f0e1-2026-0708-9003-000000000003',
    'a1b5f0e1-2026-0708-9004-000000000004'
);

-- 2. Restaura os posto_id órfãos originais (valores do backup pré-migration)
UPDATE gp_risks SET posto_id = '15b03ff6-42b9-4407-8cd4-a6e564ab204b' WHERE id IN (1,2,3,4,5);
UPDATE gp_risks SET posto_id = 'ed872365-6932-4ec8-bbf6-0ae7d1830e41' WHERE id IN (6,7,8,9);
UPDATE gp_risks SET posto_id = '5858e622-3d75-4c3b-ac5c-75798274ce37' WHERE id IN (10,11,12,13);
UPDATE gp_risks SET posto_id = 'e4909c49-a33b-440f-bf3d-4e683db739fb' WHERE id IN (14,15);
ALTER TABLE gp_risks ALTER COLUMN posto_id SET NOT NULL;

-- 3. Remove colunas novas de gp_risks
ALTER TABLE gp_risks
    DROP COLUMN IF EXISTS cod_agente_nocivo,
    DROP COLUMN IF EXISTS utiliz_epc,
    DROP COLUMN IF EXISTS utiliz_epi,
    DROP COLUMN IF EXISTS medicao,
    DROP COLUMN IF EXISTS funcoes_aplicaveis;

-- 4. Remove coluna exames de gp_asos
ALTER TABLE gp_asos DROP COLUMN IF EXISTS exames;

-- 5. Remove a tabela do PCMSO
DROP TABLE IF EXISTS sst_pcmso;

COMMIT;
