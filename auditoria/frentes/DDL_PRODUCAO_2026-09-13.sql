-- DDL de produção das 10 frentes de paridade com a DGX — 13/09/2026
-- Montado pelo integrador a partir do \"DDL de produção\" de cada FRENTE_NN_*.md.
-- REGRAS: só ADD COLUMN / CREATE TABLE / CREATE INDEX / widening de varchar / INSERT de
-- parâmetro. Nenhum DROP, nenhum ALTER TYPE estreitando, nenhuma linha de negócio.
-- IDEMPOTENTE: pode rodar duas vezes. Conferido rodando 2x no staging antes de produção.
-- ⚠️ Dívida de alembic: estas colunas/tabelas nascem por SQL direto porque alembic/versions
-- é zona proibida para sessão autônoma. Viram migration pela mão do Jordan (mesma dívida
-- já registrada em ANALISE_DOCS_REAIS_vs_CONECTA_PRO_20260909.md §6).
BEGIN;

-- ══════════════════════════ FRENTE 01 ══════════════════════════
ALTER TABLE afd_records ADD COLUMN IF NOT EXISTS punch_id varchar(36);
ALTER TABLE afd_records ADD COLUMN IF NOT EXISTS origem   varchar(20);
ALTER TABLE afd_records ALTER COLUMN afd_line TYPE varchar(400);
CREATE UNIQUE INDEX IF NOT EXISTS ux_afd_records_punch ON afd_records(punch_id);

CREATE TABLE IF NOT EXISTS rep_instrumento_legal (
    id           serial PRIMARY KEY,
    tipo         varchar(30) NOT NULL,   -- INPI | ATESTADO_TECNICO | TERMO_RESPONSABILIDADE
    empresa_id   uuid,
    numero       varchar(60),
    emissor      varchar(150),
    data_emissao date,
    validade     date,
    arquivo_url  varchar(500),
    observacao   text,
    created_at   timestamp NOT NULL DEFAULT now()
);
COMMENT ON TABLE rep_instrumento_legal IS
  'REP-P: registro INPI, atestado técnico e termo de responsabilidade (Portaria 671 art. 89).
   Preenchido pelo dono, nunca por sessão autônoma.';
-- ⚠️ NÃO EXECUTAR AQUI. A tabela nasce VAZIA de propósito: enquanto não houver registro no
-- INPI, atestado técnico e termo de responsabilidade (art. 89 §4º da Portaria 671), o REP-P
-- NÃO está constituído — e o oráculo test_oraculo_rep_p fica vermelho na afirmação (e) para
-- dizer isso todo dia. Preencher é decisão do Jordan com o contador, com número e data REAIS.
-- Modelo, para quando houver o documento na mão:
-- INSERT INTO rep_instrumento_legal (tipo, numero, emissor, data_emissao, validade) VALUES
--  ('INPI', '<nº do registro>', 'INPI', '<data>', NULL),
--  ('ATESTADO_TECNICO', NULL, 'CONECTAMAIS ELETRONICA LTDA', '<data>', '<validade>'),
--  ('TERMO_RESPONSABILIDADE', NULL, 'CONECTAMAIS ELETRONICA LTDA', '<data>', NULL);

-- ══════════════════════════ FRENTE 02 ══════════════════════════
-- status precisa caber 'pendente_de_conferencia' (23 caracteres); varchar(20) truncava.
-- Widening de varchar no Postgres não reescreve a tabela.
ALTER TABLE gp_clock_punches ALTER COLUMN status TYPE varchar(30);

ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS chave_idempotente       varchar(120);
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS divergencia_relogio_seg integer;
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS tentativas_offline      jsonb;
ALTER TABLE gp_clock_punches ADD COLUMN IF NOT EXISTS device_id               varchar(64);

-- a trava que impede a retentativa do aparelho de virar batida nova.
-- Aceita vários NULL (toda batida online tem chave nula) — comportamento desejado no Postgres.
CREATE UNIQUE INDEX IF NOT EXISTS ux_gp_punch_chave_idem ON gp_clock_punches(chave_idempotente);

COMMENT ON COLUMN gp_clock_punches.chave_idempotente IS
  'frente 02: employee_id:minuto-da-hora-do-aparelho:device_id. Unique: a retentativa do SW nunca duplica.';
COMMENT ON COLUMN gp_clock_punches.divergencia_relogio_seg IS
  'frente 02: server_timestamp - punch_timestamp em segundos. Relogio de aparelho e editavel; a defesa e ter o numero.';
COMMENT ON COLUMN gp_clock_punches.tentativas_offline IS
  'frente 02: falhas de reconhecimento ocorridas NO APARELHO enquanto offline, para a estatistica nao sumir.';

-- parâmetros (§4). Trocar o valor aqui muda o comportamento sem tocar em código.
INSERT INTO system_configs (id, chave, nome, valor, valor_type, scope, priority, ativo, created_at, updated_at)
VALUES
 (gen_random_uuid(),'ponto.facial.limiar_distancia','Limiar de distancia do reconhecimento facial','0.68','float','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.divergencia_relogio_max_seg','Divergencia maxima entre relogio do aparelho e do servidor (s)','300','int','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.validade_cache_horas','Validade do cache do descriptor no aparelho (h)','24','int','global','normal',true,now(),now()),
 (gen_random_uuid(),'ponto.offline.janela_idempotencia_min','Janela de idempotencia da batida offline (min)','20','int','global','normal',true,now(),now())
ON CONFLICT (chave) DO NOTHING;   -- integrador: reexecutável; o valor vigente manda, não o do script.
-- (a linha acima, no relatório da frente 02, era um TRECHO ILUSTRATIVO da consulta que o
--  rep_p.py usa para decidir o que entra no AFD — não é DDL. Removida daqui: o código já está
--  no repositório; o que ela documenta é que batida `pendente_de_conferencia` não vira linha AFD.)

-- ══════════════════════════ FRENTE 03 ══════════════════════════
CREATE TABLE IF NOT EXISTS folha_beneficio_conferencia (
  id bigserial PRIMARY KEY,
  employee_id uuid NOT NULL,
  competencia date NOT NULL,
  beneficio varchar(4) NOT NULL,
  operadora varchar(20),
  estado varchar(24) NOT NULL,
  planejado_anterior integer, trabalhado_anterior integer, recebido_anterior numeric(12,2),
  direito_anterior integer, saldo_anterior integer,
  previsao integer, mais_ponto integer, menos_ponto integer, credito_debito integer, quantidade integer,
  unitario numeric(12,2), total numeric(12,2),
  concedido_folha numeric(12,2),
  portal_valor numeric(12,2), portal_pedido varchar(40), portal_cartao varchar(40),
  mapa jsonb,
  fonte_escala varchar(30),
  calculado_em timestamptz DEFAULT now(),
  UNIQUE (employee_id, competencia, beneficio)
);
-- ⚠️ DUAS correções do integrador neste bloco:
-- 1) `cct_benefit_configs` não tem chave única nestes campos: rodar o script duas vezes
--    DUPLICARIA o parâmetro de benefício em silêncio (cada linha tem gen_random_uuid()), e o
--    motor passaria a ler dois valores para o mesmo benefício. Guardado com NOT EXISTS.
-- 2) `beneficio_horas_minimas_dia = 4h` foi REMOVIDO: o próprio relatório da frente 03 marca
--    como "DECISÃO PENDENTE" — é chute do agente, não medição. Sem ele o motor trata como
--    "parâmetro ausente" (que é o desenho: ausente nunca vira default). O Jordan decide o
--    número e aí a linha entra. Os três abaixo são MEDIDOS nos pedidos dos portais de agosto.
INSERT INTO cct_benefit_configs (id, empresa_id, tipo_beneficio, valor_empresa, desconto_empregado, operadora, vigencia_inicio, ativo, observacoes)
SELECT gen_random_uuid(), NULL, v.tipo, v.valor, 0, v.operadora, v.vig::date, true, v.obs
FROM (VALUES
  ('vale_refeicao',   22.00, 'SOLIDES',  '2026-01-01', 'frente 03: R$/dia — pedido Sólides Agosto/2026 (330 = 15 x 22) e piso CCT'),
  ('vale_transporte', 10.00, 'SOLIDES',  '2026-01-01', 'frente 03: R$/dia — mobilidade Sólides Agosto/2026 (150 = 15 x 10)'),
  ('vale_transporte', 10.00, 'SINETRAM', '2026-01-01', 'frente 03: R$/dia — SINETRAM (270 = 27 x 10) — confirmar com a Pyetra')
) AS v(tipo, valor, operadora, vig, obs)
WHERE NOT EXISTS (
  SELECT 1 FROM cct_benefit_configs c
   WHERE c.tipo_beneficio = v.tipo
     AND c.operadora IS NOT DISTINCT FROM v.operadora
     AND c.vigencia_inicio = v.vig::date
);

-- ══════════════════════════ FRENTE 05 ══════════════════════════
ALTER TABLE employees ADD COLUMN IF NOT EXISTS nome_de_guerra varchar(60);
-- employees.cnv_validade JÁ existe (sprint33) — não recriar.

CREATE TABLE IF NOT EXISTS vigilante_cursos (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  tipo            varchar(40) NOT NULL CHECK (tipo IN ('formacao','reciclagem_patrimonial','reciclagem_escolta_armada','reciclagem_vspp','outro')),
  data_conclusao  date NOT NULL,
  validade_meses  int  NOT NULL CHECK (validade_meses > 0),
  vence_em        date NOT NULL,
  local           varchar(120),
  certificado_url text,
  created_by      uuid,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vigilante_cursos_employee ON vigilante_cursos (employee_id, vence_em DESC);

CREATE TABLE IF NOT EXISTS equipamentos_controlados (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo         varchar(20) NOT NULL CHECK (tipo IN ('armamento','colete')),
  numero_serie varchar(60) NOT NULL UNIQUE,
  modelo       varchar(80),
  calibre      varchar(20),
  status       varchar(20) NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo','manutencao','baixado')),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS equipamentos_controlados_alocacoes (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  equipamento_id uuid NOT NULL REFERENCES equipamentos_controlados(id),
  employee_id    uuid NOT NULL REFERENCES employees(id),
  entregue_em    timestamptz NOT NULL DEFAULT now(),
  devolvido_em   timestamptz,
  entregue_por   uuid,
  devolvido_por  uuid,
  observacao     text,
  CHECK (devolvido_em IS NULL OR devolvido_em >= entregue_em)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_equip_aloc_aberta
  ON equipamentos_controlados_alocacoes (equipamento_id) WHERE devolvido_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_equip_aloc_employee ON equipamentos_controlados_alocacoes (employee_id);

INSERT INTO system_configs (id, chave, valor, tipo, escopo, prioridade, descricao, grupo, nome)
VALUES (gen_random_uuid(), 'vigilante.reciclagem_validade_meses', '24', 'string', 'global', 'normal',
        'Validade (meses) da reciclagem de vigilante, contada da conclusão do curso (Lei 7.102/83; PF exige 2 anos)',
        'vigilante', 'vigilante.reciclagem_validade_meses')
ON CONFLICT (chave) DO NOTHING;
INSERT INTO system_configs (id, chave, valor, tipo, escopo, prioridade, descricao, grupo, nome)
VALUES (gen_random_uuid(), 'vigilante.funcoes_exigem_credencial', '["vigilante","escolta"]', 'string', 'global', 'normal',
        'Trechos de cargo/tipo de posto que exigem CNV e reciclagem (lista JSON). Ausente = todos sujeitos.',
        'vigilante', 'vigilante.funcoes_exigem_credencial')
ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, ativo = true;

-- ══════════════════════════ FRENTE 06 ══════════════════════════
ALTER TABLE inspection_checkpoints
  ADD COLUMN IF NOT EXISTS foto_obrigatoria  boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS hora_aparelho     timestamptz,
  ADD COLUMN IF NOT EXISTS hora_servidor     timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS device_id         varchar(80),
  ADD COLUMN IF NOT EXISTS chave_idempotente varchar(120),
  ADD COLUMN IF NOT EXISTS origem_offline    boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS ux_inspection_checkpoints_chave_idempotente
  ON inspection_checkpoints (chave_idempotente);

-- ══════════════════════════ FRENTE 10 ══════════════════════════
CREATE TABLE IF NOT EXISTS sst_uniforme_grade (
  id serial PRIMARY KEY, item varchar(120) NOT NULL, tamanho varchar(10) NOT NULL,
  sku_norm varchar(140) NOT NULL UNIQUE, minimo integer NOT NULL CHECK (minimo >= 0),
  maximo integer NOT NULL CHECK (maximo >= minimo), atual integer CHECK (atual >= 0),
  valor_unitario numeric(12,2), catalog_id uuid, ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS sst_uniforme_entregas (
  id serial PRIMARY KEY, lote varchar(40) NOT NULL, grade_id integer NOT NULL REFERENCES sst_uniforme_grade(id),
  employee_id uuid NOT NULL, quantidade integer NOT NULL CHECK (quantidade > 0), motivo varchar(30) NOT NULL, prazo date,
  status varchar(20) NOT NULL DEFAULT 'solicitado' CHECK (status IN ('solicitado','separado','entregue','devolvido')),
  solicitado_em timestamptz NOT NULL DEFAULT now(), separado_em timestamptz, entregue_em timestamptz, devolvido_em timestamptz,
  created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_sst_uniforme_entregas_grade ON sst_uniforme_entregas (grade_id, status);
CREATE TABLE IF NOT EXISTS frota_veiculos (
  id serial PRIMARY KEY, placa varchar(10) NOT NULL UNIQUE, modelo varchar(80),
  km_proxima_troca_oleo integer, km_proxima_troca_pneu integer, km_proxima_troca_correia integer,
  ativo boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS frota_leituras (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(15) NOT NULL CHECK (tipo IN ('km','abastecimento')), km integer NOT NULL CHECK (km >= 0),
  litros numeric(8,2), valor numeric(10,2), condutor_id uuid, lida_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_frota_leituras_veiculo ON frota_leituras (veiculo_id, lida_em);
CREATE TABLE IF NOT EXISTS frota_vistorias (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(10) NOT NULL CHECK (tipo IN ('chegada','saida')), os_ref varchar(40) NOT NULL, condutor_id uuid NOT NULL,
  km integer, checklist varchar(10) NOT NULL CHECK (checklist IN ('ok','avariado')), areas jsonb NOT NULL DEFAULT '{}'::jsonb,
  par_id integer REFERENCES frota_vistorias(id),
  status_saida varchar(25) CHECK (status_saida IN ('sem_diferencas','houve_diferencas','aguardando_checklist')),
  criado_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS aval_ambientes (
  id serial PRIMARY KEY, contract_id uuid NOT NULL, nome varchar(80) NOT NULL, itens jsonb NOT NULL DEFAULT '[]'::jsonb,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE (contract_id, nome));
CREATE TABLE IF NOT EXISTS aval_links (
  token varchar(48) PRIMARY KEY, contract_id uuid NOT NULL, exige_identificacao boolean NOT NULL DEFAULT false,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aval_respostas (
  id serial PRIMARY KEY, token varchar(48) NOT NULL REFERENCES aval_links(token),
  ambiente_id integer NOT NULL REFERENCES aval_ambientes(id), turno varchar(10) NOT NULL CHECK (turno IN ('manha','tarde','noite')),
  identificacao varchar(120), notas jsonb NOT NULL, comentario text, criado_em timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_aval_respostas_amb ON aval_respostas (ambiente_id, criado_em);

-- ══════════════════════════ FRENTE 07 ══════════════════════════
-- ⚠️ ACRESCENTADO DEPOIS (13/09, 09h): a primeira montagem deste script pulou a frente 07 por
-- erro meu de integrador — e a prova de fora denunciou, com os dois oráculos de precificação
-- estourando em produção por parâmetro inexistente. É o valor de rodar o oráculo em produção
-- em vez de confiar no verde do staging.
ALTER TABLE crm_pricing_params
  ADD COLUMN IF NOT EXISTS vigencia_inicio date,
  ADD COLUMN IF NOT EXISTS vigencia_fim date,
  ADD COLUMN IF NOT EXISTS origem varchar(200),
  ADD COLUMN IF NOT EXISTS confirmado_por varchar(120),
  ADD COLUMN IF NOT EXISTS confirmado_em timestamptz;

-- valor 0 + confirmado_em NULL = "parâmetro ausente": NÃO entra no custo até o Jordan confirmar.
INSERT INTO crm_pricing_params (chave, valor, label, grupo, vigencia_inicio, vigencia_fim, origem) VALUES
 ('reserva_tecnica_pct', 0, 'Reserva técnica — % sobre o efetivo do posto (cobertura de faltas/férias)', 'contrato',
  '2026-01-01', '2026-12-31', 'Decisão do dono — A CONFIRMAR PELO JORDAN (sem confirmação NÃO entra no custo)'),
 ('plr_sindicato_pct', 0, 'PLR sindicato — % sobre a mão de obra', 'contrato',
  '2026-01-01', '2026-12-31', 'CCT SINDECOMPRESTS AM000613/2025 não traz PLR em % (cct_beneficios sem PLR) — A CONFIRMAR PELO JORDAN'),
 ('taxa_admin_pct', 0, 'Taxa administrativa — % sobre o subtotal do contrato', 'contrato',
  '2026-01-01', '2026-12-31', 'Decisão do dono — A CONFIRMAR PELO JORDAN (sem confirmação NÃO entra no custo)')
ON CONFLICT (chave) DO NOTHING;

COMMIT;
