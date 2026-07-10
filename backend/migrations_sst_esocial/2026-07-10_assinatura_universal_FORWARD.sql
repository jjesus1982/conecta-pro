-- =============================================================================
-- MIGRATION: Assinatura Universal (motor central de assinatura eletrônica)
-- Data: 2026-07-10
-- Autor: agente motor de assinatura
--
-- CONTEXTO
--   As tabelas sig_signature_requests e sig_signatures JÁ EXISTEM (criadas em
--   alembic sprint40_create_signature_tables). O motor universal as reutiliza
--   como persistência única — NÃO recria tabelas.
--
--   Drift detectado: os models SQLAlchemy (modules/ai/signature/models/*)
--   declaram o atributo `extra_data` (Column JSONB), mas a migration original
--   criou a coluna com o nome `metadata`. Como `metadata` é palavra reservada
--   do SQLAlchemy Declarative, o atributo do model é `extra_data` e mapeia para
--   uma coluna `extra_data` que NÃO existe no banco. Gravar assinatura falharia
--   com UndefinedColumn.
--
-- AÇÃO (aditiva e reversível)
--   1. Adiciona coluna extra_data (JSONB) em sig_signatures e
--      sig_signature_requests, se ausente (o model espera esse nome).
--   2. Copia o conteúdo de `metadata` -> `extra_data` (ambas convivem; metadata
--      permanece intacta para não quebrar nada que a leia).
--   3. Índice para a consulta por (document_type) do status por documento.
--
--   NENHUMA tabela é dropada. NENHUMA coluna existente é alterada/removida.
--   Não toca allocations/posts/employees.
--
-- BACKUP (rodar ANTES — fora deste arquivo):
--   docker exec conecta-pro-postgres pg_dump -U postgres -d conecta_pro \
--     -t sig_signatures -t sig_signature_requests \
--     > /opt/conecta-pro/backups/sig_tables_2026-07-10.sql
-- =============================================================================

BEGIN;

-- 1) sig_signatures.extra_data
ALTER TABLE sig_signatures
    ADD COLUMN IF NOT EXISTS extra_data JSONB;

UPDATE sig_signatures
    SET extra_data = metadata
    WHERE extra_data IS NULL AND metadata IS NOT NULL;

-- 2) sig_signature_requests.extra_data
ALTER TABLE sig_signature_requests
    ADD COLUMN IF NOT EXISTS extra_data JSONB;

UPDATE sig_signature_requests
    SET extra_data = metadata
    WHERE extra_data IS NULL AND metadata IS NOT NULL;

-- 3) Índice para status por documento (busca por document_type)
CREATE INDEX IF NOT EXISTS ix_sig_requests_doctype
    ON sig_signature_requests (document_type);

COMMIT;

-- Verificação:
--   SELECT column_name FROM information_schema.columns
--     WHERE table_name='sig_signature_requests' AND column_name='extra_data';
