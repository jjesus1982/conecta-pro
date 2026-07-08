--
-- PostgreSQL database dump
--

\restrict OoR1cPfo2VxNSKAqe8OfJ1KG8BG7ER9kXAXo4AvwRUxkshNLy1Aet0Bsi3EzN89

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
    esocial_protocolo character varying(100)
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
-- Name: gp_risks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gp_risks (
    id integer NOT NULL,
    risk_id character varying(36) NOT NULL,
    posto_id character varying(36) NOT NULL,
    categoria character varying(20) NOT NULL,
    descricao text NOT NULL,
    nivel character varying(20) DEFAULT 'medio'::character varying,
    fonte_geradora character varying(255),
    medidas_controle jsonb,
    epi_recomendado jsonb,
    status character varying(20) DEFAULT 'identificado'::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone
);


ALTER TABLE public.gp_risks OWNER TO postgres;

--
-- Name: gp_risks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gp_risks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gp_risks_id_seq OWNER TO postgres;

--
-- Name: gp_risks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gp_risks_id_seq OWNED BY public.gp_risks.id;


--
-- Name: gp_asos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos ALTER COLUMN id SET DEFAULT nextval('public.gp_asos_id_seq'::regclass);


--
-- Name: gp_risks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_risks ALTER COLUMN id SET DEFAULT nextval('public.gp_risks_id_seq'::regclass);


--
-- Data for Name: gp_asos; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (1, '95c5a1ed-40f8-4cbe-ba0a-ff6b41f14a0c', 'ab54e4fc-627f-44cd-ae92-c43b459a90ec', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (2, '9ab801a3-b0a5-43cc-922d-7df52430a899', '7f10bafe-6a44-4c7b-ab37-f344a08caa2f', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (3, '81235445-7993-416a-947c-d9624d28f077', '4392a2d4-ea9b-4692-a1f9-289460aab766', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (4, '229a65bd-51cd-4978-bbfe-975e88a82fbb', '0d7f8148-337c-4c66-9000-c9589a23c88a', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (5, '9af67765-0188-4649-8375-fe4e93eaee3a', '5e9fa756-5e32-4772-861b-4bb8bff00ffe', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (6, '6e45cad1-2bbe-4534-8100-0dbcd77ea7c6', '176f110f-237c-44c6-bad3-e5ba7e495b3a', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (7, '1ad5d38f-aad2-42b3-8bcd-c7ade9e96dbf', 'a85f315b-4029-4eb1-9584-7a22ed3a7c78', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (8, '059f4e34-f374-4b19-814d-605fdd1838d0', '2e814e1c-d022-4bb4-8e39-62fab36cd4ac', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (9, 'b811e3f2-c99a-4830-9e4f-20b122f40079', 'e32ea647-7470-43b0-a560-abd3eb6ff412', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (10, '5c2afdec-7ac7-4f59-81bc-7d2013c011ee', '4f4d6166-1327-40e7-89e8-29e0736fbcfe', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (11, '4fc65216-a2cb-4c8c-bb02-be3ac7486203', '9e32646c-8bb3-431e-bde8-03f4dc05f9f6', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (12, 'cfa8f124-d60a-4d82-856c-bb71d7d3e514', '795abf6c-0a41-4b26-9094-87142591e01d', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (13, 'c2d659f6-95ba-4e23-9b42-9ad88a9185cd', '29c7e69f-8fb5-4fc7-a124-cfd06c799fe0', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (14, 'a1e167f9-0efa-402b-9be1-670cd1c00931', 'f5fe3ccb-8529-4525-9241-5f031d3b9204', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (15, '51da0f2f-3f1a-4cb2-8d73-d87fde2d363d', 'e0f63eca-6ace-4169-880e-9c021872329a', 'admissional', 'realizado', NULL, '2026-02-23', '2027-02-23', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (16, 'bd4f1f8a-a362-4140-a017-3eb66dd93a2c', '82a1d1d6-401d-487a-928f-42ed29756bca', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (17, '56afa8dd-be31-483e-af08-ae399e981ee0', '7ccefd89-b89d-463a-a0ba-ffa6475159fb', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (18, 'd599af38-0e31-4ce0-9121-10be7a9094aa', '0adfb14d-4b12-4ac0-9d5a-0570ed4531f5', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (19, '8800ee3a-b055-49b2-aebb-2c78aca5626f', 'b2f5ac0e-fb97-43ce-b7fe-78466284ea1b', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (20, '0eb0a1ba-2750-48fe-8ca8-4dada1cb0a64', '500922e3-4866-454a-8f06-d5685e8e25c1', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (21, '099d77c5-81de-4491-8b30-c5b3768105ea', '109edac0-17a1-4cd4-8bf8-8b7062d905d0', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (22, '3a780e76-f290-4c25-8e48-62ca716453af', '4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (23, '6e4fcf33-e729-4097-b79c-a83e351eb8b7', '2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (24, 'e1be4945-f7ed-42ab-a484-231766acab69', '4f6d1b27-d05b-4315-aa86-f245d70e52bb', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (25, '667f8371-827b-4bc2-b034-6777c17ce174', '12423164-f7d8-4db3-bf36-cffebda5948e', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (26, '87ed08d3-089b-49e9-be2d-010a49d1d8e5', '29dae28f-e688-4df0-8879-2704d8351d87', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (27, 'cf7cdd75-e3d6-4dfb-8094-0552d77682cf', '6bf7804a-4976-44d2-aa3e-5bf1f25c3530', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (28, 'b98f77e4-47e6-4d57-a024-18076a39419f', '9e9e1678-9988-490c-b59b-b2786bb67e1c', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (29, 'c1fd7cd1-8e8f-4661-85a4-a8f866713b87', 'a7d7cb41-0223-466c-8c2b-5353c9fa1511', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (30, '4fc23f59-9d4e-45eb-aab6-8c50e9caf775', '0754e0aa-0be4-4253-9816-003c0149c1cd', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (31, '37ff888c-cdc2-46a4-8db7-a1e108ece4bb', '2430761d-172e-44b8-a817-edfea166e321', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (32, '25b3e324-875f-45b5-abfb-bbeb969a57d8', '13a02a88-abdc-48e0-b128-d1005ba57a04', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (33, 'd72a4695-f6d5-4aa3-836b-498798e37569', '430bc8bc-da1a-4667-b6fc-578774e5d2cf', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (34, '15a92c0e-df79-4162-81ca-61dc5a6ecf0f', '0d7887cc-d824-44ff-86be-201c7ab70dc6', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (35, '3afb394b-d9fd-433c-a4a8-cd804170cf47', '58e002c7-7df8-42a8-aef9-0607d41a306c', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (36, 'df751d49-a64f-4642-9ba5-662368efb4e9', '706edbc3-e0b9-438a-98e7-c2bf7c40db42', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (37, 'f6d65344-85c1-498f-ac8f-772065c5c6bf', 'e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (38, 'f4753207-1f4a-4514-9de6-576645433c4c', 'eb84be29-7760-4d64-9688-dd5433172283', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (39, 'f5988dd0-4356-4ab3-a5b1-28d4e88bd1c5', 'ebfc72fe-7081-47b8-bce6-88b81cdcb09a', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (40, 'ad0af5e4-fe20-45d8-9d86-7eb13ec5859a', '89f89f2c-b0dd-430a-ae84-e4d35981a498', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (41, '5e5d8729-f06c-43c2-b6fc-c30f4b70a300', '41587c09-1b42-469f-9c65-4419c870d07c', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (42, 'ae2b9796-2265-4111-9fcf-e37d891ad1e0', '7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (43, '409ba4ae-9be6-4dff-b22a-0b2f07c2ec39', '783a8170-e951-4406-856e-6b0cc659d8c3', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (44, 'd0262595-a556-4c90-8ea2-95c0f7f155f1', 'b2b39603-19a1-4050-b062-98e500198012', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (45, 'c68e7f54-8ed5-4240-bf63-de83ddfc9d1f', '4714fbc7-608b-443d-9669-7b1d54897b92', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (46, 'd7472666-a360-431f-9837-4d3c7a0c8b14', '13a74a88-beef-4b40-af78-66e15a8f9dff', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (47, 'd62b98fc-5b58-473f-b419-c489073a8135', '2938d6a4-ca53-4406-ad1d-1309fa555fe6', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (48, '2f15e53f-301a-476f-865a-8c6784eda637', '62897018-8de6-4c8d-85da-dfb0acb8a105', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (49, '5abe7c25-f090-4b5a-9eb0-f97702aaaa98', 'c58e8b76-916e-4959-b1dc-7327e110a516', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (50, '3af45615-5835-4369-8a74-fd7614bdd523', '7d6280ad-2471-43e1-9d0c-5a8f576e79b1', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (51, '4c1167c8-4795-49a1-98c4-bd397488e0e1', 'a7d18664-0f10-41b6-adf9-8e824794bc4a', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (52, '48ab24f4-445e-4ecb-98b9-b61b11e21be6', '5bfbd45c-0a80-4be4-9776-e8651471f5dc', 'admissional', 'realizado', NULL, '2025-06-01', '2026-06-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (53, 'c82303d3-3591-41a8-8238-d53f79cbd096', 'ab54e4fc-627f-44cd-ae92-c43b459a90ec', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (54, '391a9ef5-8251-43f0-a60e-a71e0920de93', '7f10bafe-6a44-4c7b-ab37-f344a08caa2f', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (55, 'eeecd1df-17c6-4e5a-9886-11126fac424c', '4392a2d4-ea9b-4692-a1f9-289460aab766', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (56, '7deef76b-fd7a-4e5f-a407-f0bb7fb718a4', '0d7f8148-337c-4c66-9000-c9589a23c88a', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (57, '8ccfa645-2415-4a4e-ad7f-b7a6260d54d5', '5e9fa756-5e32-4772-861b-4bb8bff00ffe', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (58, '687cb29c-46e0-4cff-894c-edfc84cb5935', '176f110f-237c-44c6-bad3-e5ba7e495b3a', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (59, '3df6ba84-e3be-4f97-920a-06f6508af5d8', 'a85f315b-4029-4eb1-9584-7a22ed3a7c78', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (60, '308e9eb7-3098-480c-910d-c11994b27980', '82a1d1d6-401d-487a-928f-42ed29756bca', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (61, '972ee2f7-b5fa-4a37-b632-f1f818d82a78', '7ccefd89-b89d-463a-a0ba-ffa6475159fb', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (62, '8d6d4c0a-bec2-4134-823a-3b9db2414677', '0adfb14d-4b12-4ac0-9d5a-0570ed4531f5', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (63, '57bbd228-a82f-4d58-bff8-a48e6e365e4e', 'b2f5ac0e-fb97-43ce-b7fe-78466284ea1b', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (64, 'fa8af216-cedb-4909-a32e-4ec7162a8cf3', '500922e3-4866-454a-8f06-d5685e8e25c1', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (65, '89294cd7-6c6d-42ce-b34b-6489e96f6273', '109edac0-17a1-4cd4-8bf8-8b7062d905d0', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (66, '91280d20-f412-4db2-99e2-0e36ebf5dc80', '4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (67, 'c28ed25a-fe03-4c1e-a691-07d3bf779a8f', '2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (68, '6f83969c-5d0e-4a04-a4bc-421dd72d2ec1', '4f6d1b27-d05b-4315-aa86-f245d70e52bb', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (69, '4a27a8aa-7412-4c1f-a795-7da57511268b', '12423164-f7d8-4db3-bf36-cffebda5948e', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (70, 'e0165adc-7393-461c-b54d-e4b921d33844', '29dae28f-e688-4df0-8879-2704d8351d87', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (71, '06227d6e-b5d4-423b-b1a3-9df376c2c995', '6bf7804a-4976-44d2-aa3e-5bf1f25c3530', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (72, '7001bdba-2fc6-442a-9eef-6fa866c74f5b', '9e9e1678-9988-490c-b59b-b2786bb67e1c', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (73, '300fff34-ba98-4c80-a900-0e7d19b1d08e', 'a7d7cb41-0223-466c-8c2b-5353c9fa1511', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (74, '4e50bf14-1bf6-484f-9b93-e76ade0f458d', '0754e0aa-0be4-4253-9816-003c0149c1cd', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (75, 'ecdec62a-932d-4830-b734-fb217c21e993', '2430761d-172e-44b8-a817-edfea166e321', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (76, '288a3e9e-7e7e-4168-ad85-1376735f8de4', '13a02a88-abdc-48e0-b128-d1005ba57a04', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (77, '2c6836a9-5dcb-429d-88ef-f6c63bbf3ac3', '430bc8bc-da1a-4667-b6fc-578774e5d2cf', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (78, '46fd2638-a567-4edd-8f81-1b065790eeda', '0d7887cc-d824-44ff-86be-201c7ab70dc6', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (79, '41d551e1-84b9-4ab6-9f7f-3b2c127dc6a2', '58e002c7-7df8-42a8-aef9-0607d41a306c', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (80, '446175ba-117b-439b-8c0c-94a4aa9befe2', '706edbc3-e0b9-438a-98e7-c2bf7c40db42', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (81, 'e04a5b9e-9887-4978-891c-3a6807f53285', 'e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (82, 'b26e1495-34bd-45dc-a0c5-85264df7638d', 'eb84be29-7760-4d64-9688-dd5433172283', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (83, 'ef6ef8f7-066a-49f1-a36f-e0bded3bca2d', 'ebfc72fe-7081-47b8-bce6-88b81cdcb09a', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (84, '22cd204b-c52f-44d8-b2c4-d961e09c4639', '89f89f2c-b0dd-430a-ae84-e4d35981a498', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (85, 'caaa7c26-5076-417a-8e98-a6042a8d4b83', '41587c09-1b42-469f-9c65-4419c870d07c', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (86, 'f00bfa13-fd59-47ca-b77c-5213b96676be', '7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (87, '4da74fc8-78d3-418f-8668-0f82987a3fef', '783a8170-e951-4406-856e-6b0cc659d8c3', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (88, '8631c952-5726-4331-8028-d30baa2b4b3d', 'b2b39603-19a1-4050-b062-98e500198012', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (89, '7535fc51-bf64-4163-849a-6735ed4d1358', '4714fbc7-608b-443d-9669-7b1d54897b92', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (90, '65747fa4-cec5-4827-bd98-e0cc5387a45c', '13a74a88-beef-4b40-af78-66e15a8f9dff', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (91, 'f7484a14-5855-44e7-aa4f-ac0bf7c9ec93', '2938d6a4-ca53-4406-ad1d-1309fa555fe6', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (92, '0ece941f-9180-41c2-93d1-7f9114dbb90e', '62897018-8de6-4c8d-85da-dfb0acb8a105', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (93, 'a2ee9fd0-4090-43e5-86af-4db5d3f97801', 'c58e8b76-916e-4959-b1dc-7327e110a516', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (94, 'b21d0a34-0595-4bb7-90ba-28943e115a14', '7d6280ad-2471-43e1-9d0c-5a8f576e79b1', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (95, '43f3bf3d-98ca-40b3-8fca-33d14bc91892', 'a7d18664-0f10-41b6-adf9-8e824794bc4a', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);
INSERT INTO public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo) VALUES (96, 'bd5a92d6-b6e9-4e49-b25e-0f46bb24c1ff', '5bfbd45c-0a80-4be4-9776-e8651471f5dc', 'periodico', 'vencido', NULL, '2025-03-01', '2026-03-01', NULL, 'Dr. Carlos Mendes', 'CRM-AM 4521', true, NULL, NULL, NULL, '2026-03-16 00:08:17.281448', NULL, NULL, 'nao_transmitida', NULL);


--
-- Data for Name: gp_risks; Type: TABLE DATA; Schema: public; Owner: postgres
--

INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (1, 'c3a3740f-e9a1-426f-8363-995236c3a167', '15b03ff6-42b9-4407-8cd4-a6e564ab204b', 'ergonomico', 'Trabalho em pe prolongado 12h — jornada 12x36', 'medio', 'Jornada de trabalho prolongada em pe', '["Tapete antifadiga no posto", "Cadeira para pausas regulares"]', '["Calcado ergonomico"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (2, '90f43ca6-14be-4a16-833b-4fc928c341fb', '15b03ff6-42b9-4407-8cd4-a6e564ab204b', 'fisico', 'Exposicao ao calor em Manaus (clima equatorial)', 'medio', 'Temperatura ambiente elevada (>35C)', '["Protetor solar FPS30 fornecido", "Uniforme com tecido leve"]', '["Protetor Solar FPS 30"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (3, '8c6874fc-b4c6-4aae-a16c-d9c2a0252c7c', '15b03ff6-42b9-4407-8cd4-a6e564ab204b', 'fisico', 'Trabalho noturno — alteracao do ciclo circadiano', 'medio', 'Escala noturna em regime 12x36', '["Monitoramento periodico de saude via ASO"]', '[]', 'identificado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (4, 'df915da5-e74c-4725-b951-3f7816e8885c', '15b03ff6-42b9-4407-8cd4-a6e564ab204b', 'acidente', 'Confronto com individuos em portaria', 'medio', 'Acesso de pessoas nao autorizadas', '["Treinamento em comunicacao e abordagem", "Botao de panico instalado"]', '["Colete Refletivo"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (5, '82f8bc87-bf98-4c8b-8ea2-d78957b7c2f6', '15b03ff6-42b9-4407-8cd4-a6e564ab204b', 'acidente', 'Ronda em area escura ou com desnivel', 'medio', 'Areas externas com iluminacao deficiente', '["Lanterna tatica obrigatoria", "Colete refletivo obrigatorio"]', '["Lanterna Tatica", "Colete Refletivo"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (6, 'bc0d2d06-7ac4-4847-b0a7-2ae638e2b6d1', 'ed872365-6932-4ec8-bbf6-0ae7d1830e41', 'quimico', 'Exposicao a produtos de limpeza (acidos, alvejantes)', 'baixo', 'Manuseio de produtos quimicos de limpeza', '["Luvas de latex obrigatorias", "Avental de PVC", "Mascara PFF1"]', '["Luvas de Latex", "Avental de PVC", "Mascara Descartavel PFF1"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (7, '6e48a596-5f45-48c4-92ef-a30452fbe3ea', 'ed872365-6932-4ec8-bbf6-0ae7d1830e41', 'ergonomico', 'Postura forcada em limpeza de pisos e vidros', 'baixo', 'Atividades de limpeza em posicao agachada', '["Treinamento de postura correta", "Pausas regulares a cada 2h"]', '[]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (8, '73bb7f57-39ff-4171-b832-6e067e6bfab2', 'ed872365-6932-4ec8-bbf6-0ae7d1830e41', 'fisico', 'Exposicao ao calor e umidade em areas externas', 'baixo', 'Limpeza de areas externas em clima equatorial', '["Protetor solar fornecido", "Hidratacao disponivel no posto"]', '["Protetor Solar FPS 30"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (9, '007ae934-8d5d-45ba-b939-2f50d093974d', 'ed872365-6932-4ec8-bbf6-0ae7d1830e41', 'acidente', 'Queda em superficies molhadas', 'medio', 'Pisos molhados durante atividade de limpeza', '["Bota de borracha antiderrapante obrigatoria", "Sinalizacao de piso molhado"]', '["Bota de Borracha"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (10, '4045495e-33b7-4e14-8c4b-0203260a502b', '5858e622-3d75-4c3b-ac5c-75798274ce37', 'acidente', 'Trabalho em altura em condominios', 'alto', 'Manutencao em areas elevadas sem protecao', '["Cinto de seguranca obrigatorio", "Capacete obrigatorio", "Treinamento NR-35"]', '["Cinto de Seguranca", "Capacete de Seguranca"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (11, 'fc94c6aa-3cb9-4635-bb18-d3bbde95d48c', '5858e622-3d75-4c3b-ac5c-75798274ce37', 'acidente', 'Manutencao eletrica predial', 'alto', 'Instalacoes eletricas em condominios', '["EPI eletrico obrigatorio", "Treinamento NR-10 obrigatorio"]', '["Luvas isolantes", "Botina isolante"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (12, 'ddb73463-0ec9-4f62-97df-8c8b7396a25a', '5858e622-3d75-4c3b-ac5c-75798274ce37', 'fisico', 'Exposicao a ruido de ferramentas', 'medio', 'Uso de furadeira, esmerilhadeira, serra', '["Protetor auricular para trabalhos acima de 85dB"]', '["Protetor Auricular"]', 'identificado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (13, '6b685598-26fb-47fd-a14c-45a7e1cb4877', '5858e622-3d75-4c3b-ac5c-75798274ce37', 'acidente', 'Manuseio de ferramentas cortantes', 'medio', 'Ferramentas manuais de corte', '["Luvas de vaqueta obrigatorias", "Treinamento de uso seguro"]', '["Luvas de Vaqueta"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (14, '1fd1d2d3-1d7d-41d4-9659-530fa9ddd197', 'e4909c49-a33b-440f-bf3d-4e683db739fb', 'ergonomico', 'Trabalho em pe prolongado 12h', 'medio', 'Jornada de supervisao em pe', '["Tapete antifadiga no posto", "Cadeira para pausas"]', '["Calcado ergonomico"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);
INSERT INTO public.gp_risks (id, risk_id, posto_id, categoria, descricao, nivel, fonte_geradora, medidas_controle, epi_recomendado, status, created_at, updated_at) VALUES (15, 'a9c34acc-a6f6-4679-912f-8cd5f062a40f', 'e4909c49-a33b-440f-bf3d-4e683db739fb', 'acidente', 'Confronto com individuos em portaria — funcao de lideranca', 'medio', 'Responsabilidade sobre equipe em situacao de risco', '["Treinamento em gestao de crises", "Apoio psicologico periodico"]', '["Colete Refletivo"]', 'controlado', '2026-03-16 00:09:09.2571', NULL);


--
-- Name: gp_asos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_asos_id_seq', 96, true);


--
-- Name: gp_risks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_risks_id_seq', 17, true);


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
-- Name: gp_risks gp_risks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_risks
    ADD CONSTRAINT gp_risks_pkey PRIMARY KEY (id);


--
-- Name: gp_risks gp_risks_risk_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_risks
    ADD CONSTRAINT gp_risks_risk_id_key UNIQUE (risk_id);


--
-- Name: ix_gp_aso_employee; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_aso_employee ON public.gp_asos USING btree (employee_id);


--
-- Name: ix_gp_risk_posto; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_risk_posto ON public.gp_risks USING btree (posto_id);


--
-- Name: gp_asos fk_aso_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT fk_aso_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict OoR1cPfo2VxNSKAqe8OfJ1KG8BG7ER9kXAXo4AvwRUxkshNLy1Aet0Bsi3EzN89

