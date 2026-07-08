-- ============================================================================
-- MIGRATION FORWARD — ESPELHO OFICIAL do eSocial (Missão D)
-- Data: 2026-07-08 | Reversão: 2026-07-08_esocial_espelho_REVERSAO.sql
-- Backup lógico prévio: backup_pre_espelho_2026-07-08.sql (gp_cats, gp_asos,
--   sst_afastamentos — as 3 tabelas alteradas; as demais são NOVAS)
--
-- Objetivo: guardar os eventos JÁ TRANSMITIDOS ao eSocial (baixados dos
-- webservices de consulta/download — read-only no governo) e correlacioná-los
-- com os registros locais (ANTI-DUPLICIDADE antes de transmitir o backlog).
--
-- Decisão de desenho (documentada): a correlação usa COLUNAS nas tabelas
-- locais (espelho_recibo/espelho_fonte) em vez de tabela de correlação —
-- 1 evento governo ↔ 1 registro local, e as telas SST já leem essas tabelas;
-- a fonte completa (XML) fica em esocial_eventos_espelho via nr_recibo.
-- ============================================================================

BEGIN;

-- 1) Espelho: um registro por EVENTO existente no governo
CREATE TABLE IF NOT EXISTS esocial_eventos_espelho (
    id               BIGSERIAL PRIMARY KEY,
    id_evento        VARCHAR(60) NOT NULL UNIQUE,  -- atributo Id da tag evtXXXX
    tipo             VARCHAR(10),                  -- S-2210, S-2220... (NULL até baixar o XML)
    cpf_trabalhador  VARCHAR(11),                  -- extraído do XML (ou do filtro da consulta)
    nr_recibo        VARCHAR(60),                  -- recibo REAL devolvido pelo governo
    dt_recepcao      TIMESTAMPTZ,                  -- recepção no eSocial (dhRecepcao do recibo)
    dt_evento        DATE,                         -- data-fato (dtAcid/dtAso/dtIniAfast/dtAdm/dtDeslig)
    transmissor_cnpj VARCHAR(14),                  -- quem transmitiu (se presente no retorno)
    ver_proc         VARCHAR(40),                  -- software transmissor do XML (ex.: 'INDEXMED 2.0.0')
    xml_completo     TEXT,                         -- XML integral do evento (NULL = só identificador)
    baixado_em       TIMESTAMPTZ,                  -- quando o XML foi baixado
    download_status  VARCHAR(20),                  -- ok|tentar_recibo|nao_encontrado (NULL = pendente por id)
    download_erro    TEXT,                         -- descResposta honesta do governo em caso de falha
    fonte_consulta   VARCHAR(40),                  -- consulta_trabalhador|consulta_empregador|download_recibo
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE esocial_eventos_espelho IS
    'Espelho oficial do eSocial: eventos JÁ TRANSMITIDOS do empregador, baixados dos webservices de consulta/download (read-only). Fonte da verdade p/ anti-duplicidade do backlog SST.';
CREATE INDEX IF NOT EXISTS idx_espelho_tipo_cpf ON esocial_eventos_espelho (tipo, cpf_trabalhador);
CREATE INDEX IF NOT EXISTS idx_espelho_nr_recibo ON esocial_eventos_espelho (nr_recibo);
CREATE INDEX IF NOT EXISTS idx_espelho_cpf ON esocial_eventos_espelho (cpf_trabalhador);

-- 2) Log de ACESSOS ao governo (orçamento oficial: 10 acessos/dia nos 2 webservices)
CREATE TABLE IF NOT EXISTS esocial_espelho_acessos (
    id             BIGSERIAL PRIMARY KEY,
    servico        VARCHAR(30) NOT NULL,  -- consulta_trabalhador|consulta_empregador|consulta_tabela|download_id|download_recibo
    parametros     JSONB,
    cd_resposta    VARCHAR(10),
    desc_resposta  TEXT,
    qtde_retornada INTEGER,
    http_status    INTEGER,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE esocial_espelho_acessos IS
    'Cada chamada REAL aos webservices dwlcirurgico do eSocial (consulta identificadores + download). Base do orçamento de 10 acessos/dia imposto pelo governo.';
CREATE INDEX IF NOT EXISTS idx_espelho_acessos_dia ON esocial_espelho_acessos (criado_em);

-- 3) Janelas de varredura por CPF (progresso da enumeração — 31 dias máx/consulta)
CREATE TABLE IF NOT EXISTS esocial_espelho_janelas (
    id               BIGSERIAL PRIMARY KEY,
    cpf              VARCHAR(11) NOT NULL,
    dt_ini           TIMESTAMPTZ NOT NULL,
    dt_fim           TIMESTAMPTZ NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'pendente',  -- pendente|consultada|vazia|erro
    qtde_encontrada  INTEGER,
    cd_resposta      VARCHAR(10),
    consultada_em    TIMESTAMPTZ,
    UNIQUE (cpf, dt_ini, dt_fim)
);
COMMENT ON TABLE esocial_espelho_janelas IS
    'Fila de janelas CPF×período (recepção, máx. 31 dias) a consultar no espelho. O beat semanal consome dentro do orçamento diário.';

-- 4) Correlação anti-duplicidade nos registros locais
ALTER TABLE gp_asos
    ADD COLUMN IF NOT EXISTS espelho_recibo VARCHAR(60),
    ADD COLUMN IF NOT EXISTS espelho_fonte  VARCHAR(40);
COMMENT ON COLUMN gp_asos.espelho_recibo IS
    'Recibo do S-2220 JÁ EXISTENTE no governo (casado por CPF+data do exame via espelho) — NÃO retransmitir';
COMMENT ON COLUMN gp_asos.espelho_fonte IS
    'CNPJ do transmissor do evento espelhado (ex.: MB/INDEXMED) ou "espelho_esocial" se desconhecido';

ALTER TABLE sst_afastamentos
    ADD COLUMN IF NOT EXISTS espelho_recibo VARCHAR(60),
    ADD COLUMN IF NOT EXISTS espelho_fonte  VARCHAR(40);
COMMENT ON COLUMN sst_afastamentos.espelho_recibo IS
    'Recibo do S-2230 JÁ EXISTENTE no governo (casado por CPF+dtIniAfast via espelho) — NÃO retransmitir';
COMMENT ON COLUMN sst_afastamentos.espelho_fonte IS
    'CNPJ do transmissor do evento espelhado ou "espelho_esocial" se desconhecido';

ALTER TABLE gp_cats
    ADD COLUMN IF NOT EXISTS espelho_recibo VARCHAR(60),
    ADD COLUMN IF NOT EXISTS espelho_fonte  VARCHAR(40);
COMMENT ON COLUMN gp_cats.espelho_recibo IS
    'Recibo do S-2210 JÁ EXISTENTE no governo (casado por CPF+dtAcid via espelho) — NÃO retransmitir';
COMMENT ON COLUMN gp_cats.espelho_fonte IS
    'CNPJ do transmissor do evento espelhado ou "espelho_esocial" se desconhecido';

COMMIT;
