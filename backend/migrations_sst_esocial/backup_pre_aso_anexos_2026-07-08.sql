--
-- PostgreSQL database dump
--

\restrict WlVSqwarytOJHqdaRVQbCWGxbnUATQr2cTGjbCgi0VefbsbFFHyciBIPyJiYvcx

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
-- Name: gp_asos; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gp_asos (
    id integer NOT NULL,
    aso_id character varying(36) NOT NULL,
    employee_id uuid NOT NULL,
    tipo character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'agendado'::character varying NOT NULL,
    data_agendamento date,
    data_realizacao date,
    data_validade date,
    clinica character varying(255),
    medico character varying(255),
    crm character varying(20),
    apto boolean,
    restricoes jsonb,
    observacoes text,
    documento_url character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    recibo_s2220 character varying(60),
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL,
    esocial_protocolo character varying(100),
    exames jsonb,
    espelho_recibo character varying(60),
    espelho_fonte character varying(40)
);


ALTER TABLE public.gp_asos OWNER TO postgres;

--
-- Name: COLUMN gp_asos.recibo_s2220; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.recibo_s2220 IS 'Recibo REAL retornado pelo eSocial para o S-2220 (nunca fabricado)';


--
-- Name: COLUMN gp_asos.esocial_status; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.esocial_status IS 'nao_transmitida|transmitida|aceita|rejeitada|erro';


--
-- Name: COLUMN gp_asos.esocial_protocolo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.esocial_protocolo IS 'Protocolo REAL do lote eSocial (S-2220) — usado pelo pull de recibos; nunca fabricado';


--
-- Name: COLUMN gp_asos.exames; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.exames IS 'Procedimentos Tabela 27 do ASO: [{dt_exame, cod_procedimento, nome, fonte}]. O exame clínico (0295) é derivação determinística de data_realizacao (todo ASO realizado inclui avaliação clínica ocupacional — NR-7/PCMSO); exames complementares só entram com evidência documental.';


--
-- Name: COLUMN gp_asos.espelho_recibo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.espelho_recibo IS 'Recibo do S-2220 JÁ EXISTENTE no governo (casado por CPF+data do exame via espelho) — NÃO retransmitir';


--
-- Name: COLUMN gp_asos.espelho_fonte; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_asos.espelho_fonte IS 'CNPJ do transmissor do evento espelhado (ex.: MB/INDEXMED) ou "espelho_esocial" se desconhecido';


--
-- Name: gp_asos_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gp_asos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gp_asos_id_seq OWNER TO postgres;

--
-- Name: gp_asos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gp_asos_id_seq OWNED BY public.gp_asos.id;


--
-- Name: gp_asos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos ALTER COLUMN id SET DEFAULT nextval('public.gp_asos_id_seq'::regclass);


--
-- Name: gp_asos gp_asos_aso_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT gp_asos_aso_id_key UNIQUE (aso_id);


--
-- Name: gp_asos gp_asos_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT gp_asos_pkey PRIMARY KEY (id);


--
-- Name: ix_gp_aso_employee; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_aso_employee ON public.gp_asos USING btree (employee_id);


--
-- Name: gp_asos fk_aso_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT fk_aso_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict WlVSqwarytOJHqdaRVQbCWGxbnUATQr2cTGjbCgi0VefbsbFFHyciBIPyJiYvcx

