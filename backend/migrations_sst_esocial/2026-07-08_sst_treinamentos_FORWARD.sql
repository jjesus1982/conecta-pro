-- ============================================================================
-- MIGRATION FORWARD — Missão 2 (4º pilar NR-1: Treinamentos NR)
-- Data: 2026-07-08
-- Tabela nova: sst_treinamentos (nenhuma tabela existente é alterada)
-- Fecha o check "treinamentos" do painel /sst/nr1/compliance (era 'sem_fonte')
-- Reversão: 2026-07-08_sst_treinamentos_REVERSAO.sql
-- Backup lógico prévio obrigatório — ver backup_pre_treinamentos_2026-07-08.sql
--   (schema de employees, alvo do FK; sst_treinamentos NÃO existia antes —
--    prova: SELECT to_regclass('sst_treinamentos') era NULL)
-- SEM SEED: nenhum treinamento é fabricado — dado real entra pela tela/endpoint.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS sst_treinamentos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id      UUID NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
    norma            VARCHAR(30) NOT NULL
                     CHECK (norma IN ('NR-1', 'NR-6', 'brigada', 'primeiros_socorros', 'outro')),
    descricao        TEXT,
    data_realizacao  DATE NOT NULL,
    validade_meses   INTEGER NOT NULL DEFAULT 12
                     CHECK (validade_meses BETWEEN 1 AND 120),
    -- vencimento é CALCULADO pelo backend (data_realizacao + validade_meses meses)
    -- e persistido para consultas/índice; nunca digitado à mão.
    vencimento       DATE NOT NULL,
    certificado_path VARCHAR(500),
    created_by       VARCHAR(200),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sst_treinamentos_employee   ON sst_treinamentos (employee_id);
CREATE INDEX IF NOT EXISTS ix_sst_treinamentos_vencimento ON sst_treinamentos (vencimento);
CREATE INDEX IF NOT EXISTS ix_sst_treinamentos_norma      ON sst_treinamentos (norma);

COMMENT ON TABLE sst_treinamentos IS
    'Treinamentos NR (NR-1 cap. 1.4.1: informação e capacitação) — 4º pilar do painel de compliance NR-1. Dado REAL: registro só quando o treinamento aconteceu.';
COMMENT ON COLUMN sst_treinamentos.norma IS
    'NR-1|NR-6|brigada|primeiros_socorros|outro';
COMMENT ON COLUMN sst_treinamentos.vencimento IS
    'Calculado no backend: data_realizacao + validade_meses (meses). Vencido = pendência no compliance NR-1';
COMMENT ON COLUMN sst_treinamentos.certificado_path IS
    'Caminho/URL do certificado digitalizado (opcional — sem certificado o registro continua honesto, mas sem prova documental)';
COMMENT ON COLUMN sst_treinamentos.created_by IS
    'E-mail/nome do usuário que registrou (auditoria)';

COMMIT;
