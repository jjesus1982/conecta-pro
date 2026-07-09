-- ============================================================================
-- REVERSÃO — Central de Transmissão eSocial (Missão M2) — 2026-07-09
-- Desfaz 2026-07-09_s2240_transmissoes_FORWARD.sql (tabela nova, sem impacto
-- em tabelas pré-existentes). ATENÇÃO: apaga o rastreio de protocolos/recibos
-- REAIS de S-2240 já transmitidos — exporte antes se houver linhas:
--   \copy sst_s2240_transmissoes TO 'backup_s2240_transmissoes.csv' CSV HEADER
-- ============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_s2240_transm_status;
DROP TABLE IF EXISTS sst_s2240_transmissoes;

COMMIT;
