-- =============================================================================
-- REVERSÃO: Assinatura Universal (2026-07-10)
--
-- Desfaz APENAS o que o FORWARD adicionou (colunas extra_data + índice).
-- A coluna `metadata` original e os dados nunca foram tocados, então a reversão
-- é segura. NÃO dropa as tabelas sig_* (pré-existentes).
--
-- ATENÇÃO: dropar extra_data volta a expor o drift (o model quebra ao gravar).
-- Só reverter se for também reverter o código do módulo signatures.
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS ix_sig_requests_doctype;

ALTER TABLE sig_signature_requests
    DROP COLUMN IF EXISTS extra_data;

ALTER TABLE sig_signatures
    DROP COLUMN IF EXISTS extra_data;

COMMIT;
