-- ============================================================================
-- MIGRATION REVERSAO — Missão B (SST↔eSocial + NR-1)
-- Reverte: 2026-07-07_sst_ondaB_FORWARD.sql
-- ATENÇÃO: perde protocolos/fichas/LTCAT reais já gravados — restaurar do
-- backup lógico (backup_pre_ondaB_*.sql) se necessário.
-- NOTA: o valor 'ficha_epi' do enum portal_document_type_enum NÃO é removido
-- (PostgreSQL não suporta DROP VALUE; o valor extra é inofensivo).
-- ============================================================================

BEGIN;

ALTER TABLE gp_cats DROP COLUMN IF EXISTS esocial_protocolo;
ALTER TABLE gp_asos DROP COLUMN IF EXISTS esocial_protocolo;
ALTER TABLE sst_afastamentos DROP COLUMN IF EXISTS esocial_protocolo;

ALTER TABLE gp_epi_deliveries DROP COLUMN IF EXISTS ficha_epi_id;

DROP TABLE IF EXISTS sst_fichas_epi;
DROP TABLE IF EXISTS sst_ltcat;

COMMIT;
