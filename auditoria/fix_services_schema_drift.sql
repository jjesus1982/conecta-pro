-- =====================================================================
-- fix_services_schema_drift.sql
-- Correcao de SCHEMA DRIFT do modulo services (Conecta PRO)
--
-- CONTEXTO: os models ORM (SQLAlchemy) declaram colunas que NAO existem
-- nas tabelas do banco, causando HTTP 500 em /services/catalog,
-- /services/orders/stats e /services/orders/at-risk (SELECT * gera SQL
-- com colunas inexistentes -> UndefinedColumnError).
--
-- Este script adiciona SOMENTE as colunas presentes no MODEL e ausentes
-- na TABELA. Colunas extras no banco (nao mapeadas) NAO sao tocadas.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS. Seguro para re-execucao.
--
-- Mapeamento de tipos SQLAlchemy -> PostgreSQL:
--   String(n)   -> varchar(n)
--   Text        -> text
--   Numeric(p,s)-> numeric(p,s)
--   Integer     -> integer
--   Boolean     -> boolean
--   DateTime    -> timestamp        (models usam datetime.utcnow NAIVE;
--                                     colunas existentes = timestamp WITHOUT tz)
--   UUID        -> uuid
--   JSONB       -> jsonb
--   ARRAY(String) -> varchar[]
--
-- NOT NULL: aplicado somente quando o model declara nullable=False, sempre
-- com DEFAULT (tabelas quase vazias: catalog=1, demais=0 -> seguro).
--
-- Gerado por investigacao E2E (drift computado via introspecao
-- SQLAlchemy __table__ vs information_schema.columns).
-- Data: 2026-07-02
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- TABELA: service_catalog  (9 colunas faltantes)
-- ---------------------------------------------------------------------
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS currency                varchar(3)      NOT NULL DEFAULT 'BRL';
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS default_sla_availability numeric(5, 2)  DEFAULT 99.0;
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS documentation_url        varchar(500);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS external_service_code    varchar(50);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS image_url                varchar(500);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS max_duration_hours       numeric(10, 2);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS min_duration_hours       numeric(10, 2);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS plus_service_code        varchar(50);
ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS required_certifications  varchar[];

-- ---------------------------------------------------------------------
-- TABELA: service_orders  (12 colunas faltantes)
-- Obs.: latitude/longitude sao NUMERIC no model (nao Float). Mantido numeric.
-- ---------------------------------------------------------------------
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS additional_charges_reason varchar(200);
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS approval_notes            text;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS assigned_team_id          uuid;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS cancelled_by              uuid;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS first_response_at         timestamp;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS latitude                  numeric(10, 8);
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS longitude                 numeric(11, 8);
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS rating_comment            text;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS rejected_at               timestamp;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS rejected_by               uuid;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS requires_approval         boolean NOT NULL DEFAULT false;
ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS tags                      jsonb;

-- ---------------------------------------------------------------------
-- TABELA: service_executions  (20 colunas faltantes)
-- ---------------------------------------------------------------------
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS arrival_time              timestamp;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS attachments               jsonb;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS client_signature          text;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS client_signature_date     timestamp;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS client_signature_name     varchar(200);
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS departure_time            timestamp;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS end_latitude              numeric(10, 8);
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS end_longitude             numeric(11, 8);
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS issues_found              text;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS other_costs               numeric(15, 2) DEFAULT 0;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS pause_count               integer        NOT NULL DEFAULT 0;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS pause_history             jsonb;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS photos_after              jsonb;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS photos_before             jsonb;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS start_latitude            numeric(10, 8);
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS start_longitude           numeric(11, 8);
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS technician_signature      text;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS technician_signature_date timestamp;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS travel_end                timestamp;
ALTER TABLE service_executions ADD COLUMN IF NOT EXISTS waiting_duration_minutes  integer;

-- ---------------------------------------------------------------------
-- TABELA: service_reports  (12 colunas faltantes)
-- ---------------------------------------------------------------------
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS corrective_actions        jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS documents                 jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS equipment_inspected       jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS equipment_recommendations jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS equipment_status          jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS pdf_generated_at          timestamp;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS preventive_actions        jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS sent_method               varchar(50);
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS tags                      jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS technical_data            jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS test_results              jsonb;
ALTER TABLE service_reports ADD COLUMN IF NOT EXISTS version_history           jsonb;

-- ---------------------------------------------------------------------
-- TABELA: sla_configs  -> SEM DRIFT (nenhuma coluna faltante). Nada a fazer.
-- ---------------------------------------------------------------------

COMMIT;

-- Total de ALTER TABLE ADD COLUMN: 53
--   service_catalog     :  9
--   service_orders      : 12
--   service_executions  : 20
--   service_reports     : 12
--   sla_configs         :  0
