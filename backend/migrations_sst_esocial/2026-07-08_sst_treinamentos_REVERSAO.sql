-- ============================================================================
-- MIGRATION REVERSAO — Missão 2 (4º pilar NR-1: Treinamentos NR)
-- Reverte: 2026-07-08_sst_treinamentos_FORWARD.sql
-- ATENÇÃO: perde os treinamentos REAIS já registrados — se necessário,
-- fazer pg_dump -t sst_treinamentos ANTES de reverter.
-- Nenhuma tabela pré-existente foi alterada pelo FORWARD, então a reversão
-- é apenas o DROP da tabela nova (índices e checks caem junto).
-- ============================================================================

BEGIN;

DROP TABLE IF EXISTS sst_treinamentos;

COMMIT;
