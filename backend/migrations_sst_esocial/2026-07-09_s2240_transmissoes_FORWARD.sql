-- ============================================================================
-- MIGRATION FORWARD — Central de Transmissão eSocial (Missão M2)
-- Data: 2026-07-09 | Reversão: 2026-07-09_s2240_transmissoes_REVERSAO.sql
--
-- Tabela NOVA (nenhuma tabela existente é alterada — sem backup necessário):
-- sst_s2240_transmissoes rastreia a NOSSA transmissão do S-2240 (Condições
-- Ambientais do Trabalho) por funcionário. Os demais eventos SST já têm
-- colunas próprias (gp_asos.recibo_s2220, sst_afastamentos.recibo_s2230,
-- gp_cats.numero_recibo_esocial); o S-2240 não tinha NENHUMA persistência
-- ("retorno apenas no dict") — sem esta tabela a Central não conseguiria
-- impedir dupla transmissão nem casar recibo via beat esocial-pull-recibos.
--
-- HONESTIDADE: protocolo/recibo SEMPRE reais (retornados pelo governo);
-- linha criada pela task Celery no ato do enfileiramento/transmissão.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS sst_s2240_transmissoes (
    employee_id       UUID PRIMARY KEY REFERENCES employees(id),
    esocial_status    VARCHAR(20),   -- enfileirada|transmitida|aceita|rejeitada|erro
    esocial_protocolo VARCHAR(60),   -- protocolo REAL do lote (governo)
    recibo_s2240      VARCHAR(60),   -- recibo REAL do evento (governo, via pull 2h)
    transmitida_em    TIMESTAMPTZ,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE sst_s2240_transmissoes IS
    'Rastreio da transmissão PRÓPRIA do S-2240 (eSocial) por funcionário — 1 linha por vínculo (condição vigente). Protocolo/recibo sempre reais do governo; nada fabricado.';

CREATE INDEX IF NOT EXISTS idx_s2240_transm_status
    ON sst_s2240_transmissoes (esocial_status);

COMMIT;
