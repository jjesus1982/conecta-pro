-- ============================================================================
-- MIGRATION REVERSAO — eSocial SST: remove colunas de recibo/status
-- Reverte: 2026-07-07_sst_esocial_recibos_FORWARD.sql
-- ATENÇÃO: perde recibos reais já gravados — restaurar do backup lógico
-- (pg_dump -t) se necessário.
-- ============================================================================

BEGIN;

ALTER TABLE gp_cats
    DROP COLUMN IF EXISTS numero_recibo_esocial,
    DROP COLUMN IF EXISTS esocial_status,
    DROP COLUMN IF EXISTS esocial_transmitida_em;

COMMENT ON COLUMN gp_cats.status IS NULL;

ALTER TABLE gp_asos
    DROP COLUMN IF EXISTS recibo_s2220,
    DROP COLUMN IF EXISTS esocial_status;

ALTER TABLE sst_afastamentos
    DROP COLUMN IF EXISTS recibo_s2230,
    DROP COLUMN IF EXISTS esocial_status;

COMMIT;
