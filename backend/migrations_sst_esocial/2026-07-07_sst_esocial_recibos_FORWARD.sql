-- ============================================================================
-- MIGRATION FORWARD — eSocial SST: colunas de recibo/status de transmissão
-- Data: 2026-07-07 | Missão A (núcleo eSocial SST)
-- Tabelas: gp_cats, gp_asos, sst_afastamentos
-- Reversão: 2026-07-07_sst_esocial_recibos_REVERSAO.sql
-- Backup lógico prévio obrigatório (pg_dump -t) — ver README/relatório.
--
-- Semântica de esocial_status: nao_transmitida|transmitida|aceita|rejeitada|erro
-- Ciclo de vida gp_cats.status (varchar mantido):
--   aberta|transmitida|registrada_inss|encerrada
-- ============================================================================

BEGIN;

-- gp_cats: S-2210 (CAT)
ALTER TABLE gp_cats
    ADD COLUMN IF NOT EXISTS numero_recibo_esocial VARCHAR(60),
    ADD COLUMN IF NOT EXISTS esocial_status VARCHAR(20) NOT NULL DEFAULT 'nao_transmitida',
    ADD COLUMN IF NOT EXISTS esocial_transmitida_em TIMESTAMPTZ;

COMMENT ON COLUMN gp_cats.numero_recibo_esocial IS
    'Recibo REAL retornado pelo eSocial para o S-2210 (nunca fabricado)';
COMMENT ON COLUMN gp_cats.esocial_status IS
    'nao_transmitida|transmitida|aceita|rejeitada|erro';
COMMENT ON COLUMN gp_cats.esocial_transmitida_em IS
    'Timestamp da transmissão real ao webservice do eSocial';
COMMENT ON COLUMN gp_cats.status IS
    'Ciclo de vida da CAT: aberta|transmitida|registrada_inss|encerrada';

-- gp_asos: S-2220 (Monitoramento da Saúde)
ALTER TABLE gp_asos
    ADD COLUMN IF NOT EXISTS recibo_s2220 VARCHAR(60),
    ADD COLUMN IF NOT EXISTS esocial_status VARCHAR(20) NOT NULL DEFAULT 'nao_transmitida';

COMMENT ON COLUMN gp_asos.recibo_s2220 IS
    'Recibo REAL retornado pelo eSocial para o S-2220 (nunca fabricado)';
COMMENT ON COLUMN gp_asos.esocial_status IS
    'nao_transmitida|transmitida|aceita|rejeitada|erro';

-- sst_afastamentos: S-2230 (Afastamento Temporário)
ALTER TABLE sst_afastamentos
    ADD COLUMN IF NOT EXISTS recibo_s2230 VARCHAR(60),
    ADD COLUMN IF NOT EXISTS esocial_status VARCHAR(20) NOT NULL DEFAULT 'nao_transmitida';

COMMENT ON COLUMN sst_afastamentos.recibo_s2230 IS
    'Recibo REAL retornado pelo eSocial para o S-2230 (nunca fabricado)';
COMMENT ON COLUMN sst_afastamentos.esocial_status IS
    'nao_transmitida|transmitida|aceita|rejeitada|erro';

COMMIT;
