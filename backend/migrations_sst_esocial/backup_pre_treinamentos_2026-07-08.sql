-- Backup pré-migração sst_treinamentos — 2026-07-08
-- Prova de pré-estado: to_regclass('sst_treinamentos') = NULL
-- (tabela NÃO existia; nenhuma tabela existente é alterada pelo FORWARD)
-- Schema do alvo do FK (employees), para referência:
--
-- PostgreSQL database dump
--

\restrict lAcYtf9F8UxBWeJDbVadGKb7EPQAcWuHYJUr2sHhhozBL8XP6raLiBQ7MqTzVia

-- Dumped from database version 16.11
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: employees; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.employees (
    id uuid NOT NULL,
    solides_id character varying(50),
    matricula character varying(50),
    codigo character varying(20),
    nome character varying(255) NOT NULL,
    nome_social character varying(255),
    cpf character varying(14),
    rg character varying(20),
    rg_orgao character varying(20),
    rg_uf character varying(2),
    data_nascimento date,
    sexo character varying(1),
    estado_civil character varying(20),
    nacionalidade character varying(50),
    naturalidade character varying(100),
    nome_mae character varying(255),
    nome_pai character varying(255),
    email character varying(255),
    telefone character varying(20),
    celular character varying(20),
    contato_emergencia character varying(255),
    telefone_emergencia character varying(20),
    cep character varying(10),
    logradouro character varying(255),
    numero character varying(20),
    complemento character varying(100),
    bairro character varying(100),
    cidade character varying(100),
    uf character varying(2),
    cargo character varying(100),
    cargo_id uuid,
    departamento character varying(100),
    departamento_id uuid,
    setor character varying(100),
    centro_custo character varying(100),
    gestor_id uuid,
    gestor_nome character varying(255),
    data_admissao date,
    data_demissao date,
    tipo_contrato character varying(50),
    regime_trabalho character varying(50),
    jornada_trabalho character varying(100),
    carga_horaria_semanal integer,
    escala_padrao character varying(20),
    salario_base numeric(10,2),
    tipo_pagamento character varying(20),
    banco character varying(100),
    agencia character varying(20),
    conta character varying(30),
    tipo_conta character varying(20),
    pix character varying(100),
    ctps_numero character varying(20),
    ctps_serie character varying(10),
    ctps_uf character varying(2),
    ctps_data_emissao date,
    pis character varying(20),
    titulo_eleitor character varying(20),
    zona_eleitoral character varying(10),
    secao_eleitoral character varying(10),
    certificado_reservista character varying(20),
    cnh_numero character varying(20),
    cnh_categoria character varying(5),
    cnh_validade date,
    curso_vigilante boolean,
    curso_vigilante_validade date,
    cnv character varying(30),
    cnv_validade date,
    porte_arma boolean,
    porte_arma_numero character varying(30),
    porte_arma_validade date,
    certificacoes jsonb,
    posto_atual_id uuid,
    posto_atual_nome character varying(255),
    cliente_id uuid,
    cliente_nome character varying(255),
    data_inicio_posto date,
    turno_padrao character varying(20),
    status character varying(20),
    motivo_inatividade character varying(255),
    data_retorno_previsto date,
    perfil_disc jsonb,
    perfil_predominante character varying(50),
    competencias jsonb,
    foto_url character varying(500),
    biometria_facial boolean,
    biometria_digital boolean,
    cracha_numero character varying(20),
    dependentes jsonb,
    observacoes text,
    dados_adicionais jsonb,
    sync_source character varying(20),
    last_synced_at timestamp without time zone,
    created_by uuid,
    updated_by uuid,
    is_active boolean,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    scale_template_id uuid,
    motivo_desligamento character varying(100) DEFAULT NULL::character varying,
    data_desligamento date,
    observacao_desligamento text,
    portal_password_hash character varying(128),
    portal_password_set_at timestamp with time zone,
    portal_first_access boolean DEFAULT true,
    cct_cargo_id uuid,
    pix_key character varying(150),
    pix_key_type character varying(20) DEFAULT 'CPF'::character varying,
    banco_codigo character varying(10),
    banco_agencia character varying(10),
    banco_conta character varying(20),
    banco_tipo character varying(20) DEFAULT 'CORRENTE'::character varying,
    insalubridade_percentual numeric(5,2) DEFAULT 0,
    periculosidade_percentual numeric(5,2) DEFAULT 0,
    adicional_ronda_percentual numeric(5,2) DEFAULT 0,
    recebe_intrajornada boolean DEFAULT false,
    pix_confirmada boolean DEFAULT false
);


ALTER TABLE public.employees OWNER TO postgres;

--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: idx_employees_competencias_gin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_employees_competencias_gin ON public.employees USING gin (competencias);


--
-- Name: idx_employees_dados_adicionais_gin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_employees_dados_adicionais_gin ON public.employees USING gin (dados_adicionais);


--
-- Name: ix_employees_cargo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_cargo ON public.employees USING btree (cargo);


--
-- Name: ix_employees_cct_cargo_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_cct_cargo_id ON public.employees USING btree (cct_cargo_id);


--
-- Name: ix_employees_cliente; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_cliente ON public.employees USING btree (cliente_id);


--
-- Name: ix_employees_cpf; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_cpf ON public.employees USING btree (cpf);


--
-- Name: ix_employees_matricula; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_matricula ON public.employees USING btree (matricula);


--
-- Name: ix_employees_nome; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_nome ON public.employees USING btree (nome);


--
-- Name: ix_employees_posto_atual; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_posto_atual ON public.employees USING btree (posto_atual_id);


--
-- Name: ix_employees_solides_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_solides_id ON public.employees USING btree (solides_id);


--
-- Name: ix_employees_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_employees_status ON public.employees USING btree (status);


--
-- Name: employees fk_employees_cct_cargo; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT fk_employees_cct_cargo FOREIGN KEY (cct_cargo_id) REFERENCES public.cct_cargos(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict lAcYtf9F8UxBWeJDbVadGKb7EPQAcWuHYJUr2sHhhozBL8XP6raLiBQ7MqTzVia

