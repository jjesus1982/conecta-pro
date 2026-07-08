-- ============================================================================
-- MIGRATION FORWARD — Anexos de ASO + Carga Retroativa
-- Data: 2026-07-08
-- Tabela alterada: gp_asos (4 colunas novas, nada é removido/renomeado)
-- Fato de negócio (CEO): TODOS os funcionários fizeram exames admissionais
--   antes de contratar (em papel, pré-sistema). "Sem ASO" no compliance =
--   documento não digitalizado, NÃO exame não feito. Estas colunas guardam
--   o documento digitalizado e marcam a carga retroativa.
-- Reversão: 2026-07-08_sst_aso_anexos_REVERSAO.sql
-- Backup lógico prévio obrigatório — ver backup_pre_aso_anexos_2026-07-08.sql
--   (schema de gp_asos ANTES; prova: information_schema não tinha nenhuma
--    das 4 colunas — SELECT retornou 0 rows)
-- SEM SEED: nenhum ASO retroativo é fabricado — cada registro entra pela tela
--   de Carga Retroativa COM o documento digitalizado anexado (obrigatório).
-- ============================================================================

BEGIN;

ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS arquivo_path      VARCHAR(500);
ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS arquivo_nome      VARCHAR(255);
ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS arquivo_subido_em TIMESTAMPTZ;
ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS retroativo        BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN gp_asos.arquivo_path IS
    'Caminho do ASO digitalizado no volume ./uploads (/app/uploads/asos/{aso_id}.{ext} — PDF/JPG/PNG, max 10MB)';
COMMENT ON COLUMN gp_asos.arquivo_nome IS
    'Nome original do arquivo enviado (exibição/download)';
COMMENT ON COLUMN gp_asos.arquivo_subido_em IS
    'Quando o documento foi anexado (auditoria)';
COMMENT ON COLUMN gp_asos.retroativo IS
    'TRUE = carga retroativa de exame feito em papel ANTES do sistema (anexo obrigatório). Conta normalmente no compliance NR-1 (é gp_asos realizado)';

COMMIT;
