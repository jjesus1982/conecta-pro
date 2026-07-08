-- ============================================================================
-- MIGRATION REVERSÃO — Anexos de ASO + Carga Retroativa
-- Data: 2026-07-08
-- Desfaz: 2026-07-08_sst_aso_anexos_FORWARD.sql
-- ATENÇÃO: dropar as colunas perde os metadados dos anexos (o arquivo físico
--   em ./uploads/asos permanece no disco — remoção de arquivos é decisão
--   humana, nunca automática). Registros retroativos viram ASOs comuns.
-- ============================================================================

BEGIN;

ALTER TABLE gp_asos DROP COLUMN IF EXISTS arquivo_path;
ALTER TABLE gp_asos DROP COLUMN IF EXISTS arquivo_nome;
ALTER TABLE gp_asos DROP COLUMN IF EXISTS arquivo_subido_em;
ALTER TABLE gp_asos DROP COLUMN IF EXISTS retroativo;

COMMIT;
