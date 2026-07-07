-- ============================================================================
-- MIGRATION FORWARD — Missão B (SST↔eSocial + NR-1)
-- Data: 2026-07-07 | Onda B (gatilhos + pull de recibos + ficha EPI + LTCAT)
-- Tabelas: gp_cats, gp_asos, sst_afastamentos (coluna esocial_protocolo),
--          gp_epi_deliveries (ficha_epi_id), sst_fichas_epi (nova),
--          sst_ltcat (nova) + enum portal_document_type_enum (+ficha_epi)
-- Reversão: 2026-07-07_sst_ondaB_REVERSAO.sql
-- Backup lógico prévio obrigatório (pg_dump -t) — ver backup_pre_ondaB_*.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Protocolo de envio eSocial (necessário para o pull de recibos por lote)
--    O protocolo é retornado pelo WsEnviarLoteEventos; o recibo vem DEPOIS,
--    via WsConsultarLoteEventos (beat esocial-pull-recibos a cada 2h).
-- ---------------------------------------------------------------------------
ALTER TABLE gp_cats
    ADD COLUMN IF NOT EXISTS esocial_protocolo VARCHAR(100);
ALTER TABLE gp_asos
    ADD COLUMN IF NOT EXISTS esocial_protocolo VARCHAR(100);
ALTER TABLE sst_afastamentos
    ADD COLUMN IF NOT EXISTS esocial_protocolo VARCHAR(100);

COMMENT ON COLUMN gp_cats.esocial_protocolo IS
    'Protocolo REAL do lote eSocial (S-2210) — usado pelo pull de recibos; nunca fabricado';
COMMENT ON COLUMN gp_asos.esocial_protocolo IS
    'Protocolo REAL do lote eSocial (S-2220) — usado pelo pull de recibos; nunca fabricado';
COMMENT ON COLUMN sst_afastamentos.esocial_protocolo IS
    'Protocolo REAL do lote eSocial (S-2230) — usado pelo pull de recibos; nunca fabricado';

-- ---------------------------------------------------------------------------
-- 2. Ficha de EPI digital (NR-1/NR-6) — assinada digitalmente pelo funcionário
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sst_fichas_epi (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     UUID NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    employee_nome   VARCHAR(200),
    delivery_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    itens           JSONB NOT NULL DEFAULT '[]'::jsonb,
    status          VARCHAR(30) NOT NULL DEFAULT 'pendente_assinatura',
    assinatura_hash VARCHAR(256),
    assinado_em     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_sst_fichas_epi_employee ON sst_fichas_epi (employee_id);
CREATE INDEX IF NOT EXISTS ix_sst_fichas_epi_status ON sst_fichas_epi (status);

COMMENT ON TABLE sst_fichas_epi IS
    'Ficha de EPI (NR-6) gerada por entrega — PDF padrão-ouro, assinatura digital do FUNCIONÁRIO (hash SHA-256, infra do Portal)';
COMMENT ON COLUMN sst_fichas_epi.status IS 'pendente_assinatura|assinada';
COMMENT ON COLUMN sst_fichas_epi.itens IS
    'Snapshot dos EPIs da ficha: [{delivery_id, epi_nome, ca, quantidade, data_entrega, data_validade}]';
COMMENT ON COLUMN sst_fichas_epi.assinatura_hash IS
    'Hash REAL gravado em portal_digital_signatures (document_type=ficha_epi) — nunca fabricado';

ALTER TABLE gp_epi_deliveries
    ADD COLUMN IF NOT EXISTS ficha_epi_id UUID REFERENCES sst_fichas_epi(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_gp_epi_deliveries_ficha ON gp_epi_deliveries (ficha_epi_id);
COMMENT ON COLUMN gp_epi_deliveries.ficha_epi_id IS
    'Ficha de EPI (sst_fichas_epi) que cobre esta entrega — NULL = entrega ainda sem ficha';

-- ---------------------------------------------------------------------------
-- 3. LTCAT real (fim do status hardcoded no endpoint /sst/ltcat/status)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sst_ltcat (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status              VARCHAR(30) NOT NULL DEFAULT 'pendente_elaboracao',
    responsavel_tecnico VARCHAR(200),
    registro_conselho   VARCHAR(60),
    validade_inicio     DATE,
    validade_fim        DATE,
    observacoes         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ
);
COMMENT ON TABLE sst_ltcat IS
    'LTCAT — Laudo Técnico das Condições Ambientais de Trabalho (Lei 8.213/91 Art. 58). Fonte REAL do /sst/ltcat/status';
COMMENT ON COLUMN sst_ltcat.status IS
    'pendente_elaboracao|em_elaboracao|vigente|vencido';

-- Seed honesto: 1 registro pendente (estado REAL — laudo ainda não elaborado)
INSERT INTO sst_ltcat (status, observacoes)
SELECT 'pendente_elaboracao',
       'Registro inicial (migração 2026-07-07, Onda B). LTCAT ainda não elaborado — contratar engenheiro de segurança do trabalho. Campos responsavel/validade editáveis via PUT /sst/ltcat.'
WHERE NOT EXISTS (SELECT 1 FROM sst_ltcat);

COMMIT;

-- ---------------------------------------------------------------------------
-- 4. Enum do Portal: novo tipo de documento assinável (fora de transação —
--    exigência do ALTER TYPE ... ADD VALUE)
-- ---------------------------------------------------------------------------
ALTER TYPE portal_document_type_enum ADD VALUE IF NOT EXISTS 'ficha_epi';
