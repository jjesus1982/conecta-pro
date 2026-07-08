-- ============================================================================
-- MIGRATION REVERSÃO — ESPELHO OFICIAL do eSocial (Missão D)
-- Reverte: 2026-07-08_esocial_espelho_FORWARD.sql
-- ATENÇÃO: derruba as tabelas do espelho (dados baixados do governo podem ser
-- re-baixados, mas contam no orçamento de 10 acessos/dia — reverta consciente).
-- ============================================================================

BEGIN;

ALTER TABLE gp_cats
    DROP COLUMN IF EXISTS espelho_recibo,
    DROP COLUMN IF EXISTS espelho_fonte;

ALTER TABLE sst_afastamentos
    DROP COLUMN IF EXISTS espelho_recibo,
    DROP COLUMN IF EXISTS espelho_fonte;

ALTER TABLE gp_asos
    DROP COLUMN IF EXISTS espelho_recibo,
    DROP COLUMN IF EXISTS espelho_fonte;

DROP TABLE IF EXISTS esocial_espelho_janelas;
DROP TABLE IF EXISTS esocial_espelho_acessos;
DROP TABLE IF EXISTS esocial_eventos_espelho;

COMMIT;
