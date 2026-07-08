--
-- PostgreSQL database dump
--

\restrict gizRLAyYfH7t2QRY3VhSNeP8iZOpGm9V9ll59LVDNCsdIRcSQndkY5JQ2fTaiQm

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
    exames jsonb
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
-- Name: gp_cats; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gp_cats (
    id integer NOT NULL,
    cat_id character varying(36) NOT NULL,
    employee_id character varying(36) NOT NULL,
    tipo_acidente character varying(50) NOT NULL,
    data_acidente date NOT NULL,
    hora_acidente character varying(5),
    local character varying(255) NOT NULL,
    descricao text NOT NULL,
    gravidade character varying(20) DEFAULT 'leve'::character varying,
    parte_corpo character varying(100),
    agente_causador character varying(255),
    testemunhas jsonb,
    afastamento integer DEFAULT 0,
    numero_cat_inss character varying(60),
    status character varying(20) DEFAULT 'aberta'::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    numero_recibo_esocial character varying(60),
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL,
    esocial_transmitida_em timestamp with time zone,
    esocial_protocolo character varying(100)
);


ALTER TABLE public.gp_cats OWNER TO postgres;

--
-- Name: COLUMN gp_cats.status; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_cats.status IS 'Ciclo de vida da CAT: aberta|transmitida|registrada_inss|encerrada';


--
-- Name: COLUMN gp_cats.numero_recibo_esocial; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_cats.numero_recibo_esocial IS 'Recibo REAL retornado pelo eSocial para o S-2210 (nunca fabricado)';


--
-- Name: COLUMN gp_cats.esocial_status; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_cats.esocial_status IS 'nao_transmitida|transmitida|aceita|rejeitada|erro';


--
-- Name: COLUMN gp_cats.esocial_transmitida_em; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_cats.esocial_transmitida_em IS 'Timestamp da transmissão real ao webservice do eSocial';


--
-- Name: COLUMN gp_cats.esocial_protocolo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gp_cats.esocial_protocolo IS 'Protocolo REAL do lote eSocial (S-2210) — usado pelo pull de recibos; nunca fabricado';


--
-- Name: gp_cats_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gp_cats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gp_cats_id_seq OWNER TO postgres;

--
-- Name: gp_cats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gp_cats_id_seq OWNED BY public.gp_cats.id;


--
-- Name: sst_afastamentos; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sst_afastamentos (
    id uuid NOT NULL,
    employee_id uuid NOT NULL,
    employee_nome character varying(200) NOT NULL,
    employee_cargo character varying(200),
    tipo character varying(50) NOT NULL,
    motivo text,
    data_inicio date NOT NULL,
    data_fim_prevista date,
    data_retorno date,
    dias_previstos integer,
    atestado boolean DEFAULT true,
    cid character varying(10),
    medico character varying(200),
    crm character varying(20),
    status character varying(20) DEFAULT 'ativo'::character varying,
    ajuda_medicamento_ativa boolean DEFAULT false,
    ajuda_medicamento_valor numeric(10,2),
    gera_estabilidade boolean DEFAULT false,
    estabilidade_ate date,
    observacoes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    encaminhado_inss boolean DEFAULT false,
    data_encaminhamento_inss date,
    recibo_s2230 character varying(60),
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL,
    esocial_protocolo character varying(100)
);


ALTER TABLE public.sst_afastamentos OWNER TO postgres;

--
-- Name: COLUMN sst_afastamentos.recibo_s2230; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.sst_afastamentos.recibo_s2230 IS 'Recibo REAL retornado pelo eSocial para o S-2230 (nunca fabricado)';


--
-- Name: COLUMN sst_afastamentos.esocial_status; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.sst_afastamentos.esocial_status IS 'nao_transmitida|transmitida|aceita|rejeitada|erro';


--
-- Name: COLUMN sst_afastamentos.esocial_protocolo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.sst_afastamentos.esocial_protocolo IS 'Protocolo REAL do lote eSocial (S-2230) — usado pelo pull de recibos; nunca fabricado';


--
-- Name: gp_asos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos ALTER COLUMN id SET DEFAULT nextval('public.gp_asos_id_seq'::regclass);


--
-- Name: gp_cats id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_cats ALTER COLUMN id SET DEFAULT nextval('public.gp_cats_id_seq'::regclass);


--
-- Data for Name: gp_asos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status, esocial_protocolo, exames) FROM stdin;
2	9ab801a3-b0a5-43cc-922d-7df52430a899	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
3	81235445-7993-416a-947c-d9624d28f077	4392a2d4-ea9b-4692-a1f9-289460aab766	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
4	229a65bd-51cd-4978-bbfe-975e88a82fbb	0d7f8148-337c-4c66-9000-c9589a23c88a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
5	9af67765-0188-4649-8375-fe4e93eaee3a	5e9fa756-5e32-4772-861b-4bb8bff00ffe	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
6	6e45cad1-2bbe-4534-8100-0dbcd77ea7c6	176f110f-237c-44c6-bad3-e5ba7e495b3a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
7	1ad5d38f-aad2-42b3-8bcd-c7ade9e96dbf	a85f315b-4029-4eb1-9584-7a22ed3a7c78	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
8	059f4e34-f374-4b19-814d-605fdd1838d0	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
9	b811e3f2-c99a-4830-9e4f-20b122f40079	e32ea647-7470-43b0-a560-abd3eb6ff412	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
10	5c2afdec-7ac7-4f59-81bc-7d2013c011ee	4f4d6166-1327-40e7-89e8-29e0736fbcfe	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
11	4fc65216-a2cb-4c8c-bb02-be3ac7486203	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
12	cfa8f124-d60a-4d82-856c-bb71d7d3e514	795abf6c-0a41-4b26-9094-87142591e01d	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
13	c2d659f6-95ba-4e23-9b42-9ad88a9185cd	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
14	a1e167f9-0efa-402b-9be1-670cd1c00931	f5fe3ccb-8529-4525-9241-5f031d3b9204	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
15	51da0f2f-3f1a-4cb2-8d73-d87fde2d363d	e0f63eca-6ace-4169-880e-9c021872329a	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2026-02-23", "cod_procedimento": "0295"}]
16	bd4f1f8a-a362-4140-a017-3eb66dd93a2c	82a1d1d6-401d-487a-928f-42ed29756bca	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
17	56afa8dd-be31-483e-af08-ae399e981ee0	7ccefd89-b89d-463a-a0ba-ffa6475159fb	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
18	d599af38-0e31-4ce0-9121-10be7a9094aa	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
19	8800ee3a-b055-49b2-aebb-2c78aca5626f	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
1	95c5a1ed-40f8-4cbe-ba0a-ff6b41f14a0c	ab54e4fc-627f-44cd-ae92-c43b459a90ec	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
20	0eb0a1ba-2750-48fe-8ca8-4dada1cb0a64	500922e3-4866-454a-8f06-d5685e8e25c1	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
21	099d77c5-81de-4491-8b30-c5b3768105ea	109edac0-17a1-4cd4-8bf8-8b7062d905d0	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
22	3a780e76-f290-4c25-8e48-62ca716453af	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
23	6e4fcf33-e729-4097-b79c-a83e351eb8b7	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
24	e1be4945-f7ed-42ab-a484-231766acab69	4f6d1b27-d05b-4315-aa86-f245d70e52bb	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
25	667f8371-827b-4bc2-b034-6777c17ce174	12423164-f7d8-4db3-bf36-cffebda5948e	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
26	87ed08d3-089b-49e9-be2d-010a49d1d8e5	29dae28f-e688-4df0-8879-2704d8351d87	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
27	cf7cdd75-e3d6-4dfb-8094-0552d77682cf	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
28	b98f77e4-47e6-4d57-a024-18076a39419f	9e9e1678-9988-490c-b59b-b2786bb67e1c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
29	c1fd7cd1-8e8f-4661-85a4-a8f866713b87	a7d7cb41-0223-466c-8c2b-5353c9fa1511	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
30	4fc23f59-9d4e-45eb-aab6-8c50e9caf775	0754e0aa-0be4-4253-9816-003c0149c1cd	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
31	37ff888c-cdc2-46a4-8db7-a1e108ece4bb	2430761d-172e-44b8-a817-edfea166e321	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
32	25b3e324-875f-45b5-abfb-bbeb969a57d8	13a02a88-abdc-48e0-b128-d1005ba57a04	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
33	d72a4695-f6d5-4aa3-836b-498798e37569	430bc8bc-da1a-4667-b6fc-578774e5d2cf	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
34	15a92c0e-df79-4162-81ca-61dc5a6ecf0f	0d7887cc-d824-44ff-86be-201c7ab70dc6	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
35	3afb394b-d9fd-433c-a4a8-cd804170cf47	58e002c7-7df8-42a8-aef9-0607d41a306c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
36	df751d49-a64f-4642-9ba5-662368efb4e9	706edbc3-e0b9-438a-98e7-c2bf7c40db42	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
37	f6d65344-85c1-498f-ac8f-772065c5c6bf	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
38	f4753207-1f4a-4514-9de6-576645433c4c	eb84be29-7760-4d64-9688-dd5433172283	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
39	f5988dd0-4356-4ab3-a5b1-28d4e88bd1c5	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
40	ad0af5e4-fe20-45d8-9d86-7eb13ec5859a	89f89f2c-b0dd-430a-ae84-e4d35981a498	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
41	5e5d8729-f06c-43c2-b6fc-c30f4b70a300	41587c09-1b42-469f-9c65-4419c870d07c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
42	ae2b9796-2265-4111-9fcf-e37d891ad1e0	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
43	409ba4ae-9be6-4dff-b22a-0b2f07c2ec39	783a8170-e951-4406-856e-6b0cc659d8c3	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
44	d0262595-a556-4c90-8ea2-95c0f7f155f1	b2b39603-19a1-4050-b062-98e500198012	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
45	c68e7f54-8ed5-4240-bf63-de83ddfc9d1f	4714fbc7-608b-443d-9669-7b1d54897b92	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
46	d7472666-a360-431f-9837-4d3c7a0c8b14	13a74a88-beef-4b40-af78-66e15a8f9dff	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
47	d62b98fc-5b58-473f-b419-c489073a8135	2938d6a4-ca53-4406-ad1d-1309fa555fe6	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
48	2f15e53f-301a-476f-865a-8c6784eda637	62897018-8de6-4c8d-85da-dfb0acb8a105	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
49	5abe7c25-f090-4b5a-9eb0-f97702aaaa98	c58e8b76-916e-4959-b1dc-7327e110a516	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
50	3af45615-5835-4369-8a74-fd7614bdd523	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
51	4c1167c8-4795-49a1-98c4-bd397488e0e1	a7d18664-0f10-41b6-adf9-8e824794bc4a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
52	48ab24f4-445e-4ecb-98b9-b61b11e21be6	5bfbd45c-0a80-4be4-9776-e8651471f5dc	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-06-01", "cod_procedimento": "0295"}]
53	c82303d3-3591-41a8-8238-d53f79cbd096	ab54e4fc-627f-44cd-ae92-c43b459a90ec	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
54	391a9ef5-8251-43f0-a60e-a71e0920de93	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
55	eeecd1df-17c6-4e5a-9886-11126fac424c	4392a2d4-ea9b-4692-a1f9-289460aab766	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
56	7deef76b-fd7a-4e5f-a407-f0bb7fb718a4	0d7f8148-337c-4c66-9000-c9589a23c88a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
57	8ccfa645-2415-4a4e-ad7f-b7a6260d54d5	5e9fa756-5e32-4772-861b-4bb8bff00ffe	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
58	687cb29c-46e0-4cff-894c-edfc84cb5935	176f110f-237c-44c6-bad3-e5ba7e495b3a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
59	3df6ba84-e3be-4f97-920a-06f6508af5d8	a85f315b-4029-4eb1-9584-7a22ed3a7c78	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
60	308e9eb7-3098-480c-910d-c11994b27980	82a1d1d6-401d-487a-928f-42ed29756bca	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
61	972ee2f7-b5fa-4a37-b632-f1f818d82a78	7ccefd89-b89d-463a-a0ba-ffa6475159fb	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
62	8d6d4c0a-bec2-4134-823a-3b9db2414677	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
63	57bbd228-a82f-4d58-bff8-a48e6e365e4e	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
64	fa8af216-cedb-4909-a32e-4ec7162a8cf3	500922e3-4866-454a-8f06-d5685e8e25c1	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
65	89294cd7-6c6d-42ce-b34b-6489e96f6273	109edac0-17a1-4cd4-8bf8-8b7062d905d0	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
66	91280d20-f412-4db2-99e2-0e36ebf5dc80	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
67	c28ed25a-fe03-4c1e-a691-07d3bf779a8f	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
68	6f83969c-5d0e-4a04-a4bc-421dd72d2ec1	4f6d1b27-d05b-4315-aa86-f245d70e52bb	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
69	4a27a8aa-7412-4c1f-a795-7da57511268b	12423164-f7d8-4db3-bf36-cffebda5948e	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
70	e0165adc-7393-461c-b54d-e4b921d33844	29dae28f-e688-4df0-8879-2704d8351d87	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
71	06227d6e-b5d4-423b-b1a3-9df376c2c995	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
72	7001bdba-2fc6-442a-9eef-6fa866c74f5b	9e9e1678-9988-490c-b59b-b2786bb67e1c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
73	300fff34-ba98-4c80-a900-0e7d19b1d08e	a7d7cb41-0223-466c-8c2b-5353c9fa1511	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
74	4e50bf14-1bf6-484f-9b93-e76ade0f458d	0754e0aa-0be4-4253-9816-003c0149c1cd	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
75	ecdec62a-932d-4830-b734-fb217c21e993	2430761d-172e-44b8-a817-edfea166e321	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
76	288a3e9e-7e7e-4168-ad85-1376735f8de4	13a02a88-abdc-48e0-b128-d1005ba57a04	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
77	2c6836a9-5dcb-429d-88ef-f6c63bbf3ac3	430bc8bc-da1a-4667-b6fc-578774e5d2cf	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
78	46fd2638-a567-4edd-8f81-1b065790eeda	0d7887cc-d824-44ff-86be-201c7ab70dc6	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
79	41d551e1-84b9-4ab6-9f7f-3b2c127dc6a2	58e002c7-7df8-42a8-aef9-0607d41a306c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
80	446175ba-117b-439b-8c0c-94a4aa9befe2	706edbc3-e0b9-438a-98e7-c2bf7c40db42	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
81	e04a5b9e-9887-4978-891c-3a6807f53285	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
82	b26e1495-34bd-45dc-a0c5-85264df7638d	eb84be29-7760-4d64-9688-dd5433172283	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
83	ef6ef8f7-066a-49f1-a36f-e0bded3bca2d	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
84	22cd204b-c52f-44d8-b2c4-d961e09c4639	89f89f2c-b0dd-430a-ae84-e4d35981a498	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
85	caaa7c26-5076-417a-8e98-a6042a8d4b83	41587c09-1b42-469f-9c65-4419c870d07c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
86	f00bfa13-fd59-47ca-b77c-5213b96676be	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
87	4da74fc8-78d3-418f-8668-0f82987a3fef	783a8170-e951-4406-856e-6b0cc659d8c3	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
88	8631c952-5726-4331-8028-d30baa2b4b3d	b2b39603-19a1-4050-b062-98e500198012	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
89	7535fc51-bf64-4163-849a-6735ed4d1358	4714fbc7-608b-443d-9669-7b1d54897b92	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
90	65747fa4-cec5-4827-bd98-e0cc5387a45c	13a74a88-beef-4b40-af78-66e15a8f9dff	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
91	f7484a14-5855-44e7-aa4f-ac0bf7c9ec93	2938d6a4-ca53-4406-ad1d-1309fa555fe6	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
92	0ece941f-9180-41c2-93d1-7f9114dbb90e	62897018-8de6-4c8d-85da-dfb0acb8a105	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
93	a2ee9fd0-4090-43e5-86af-4db5d3f97801	c58e8b76-916e-4959-b1dc-7327e110a516	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
94	b21d0a34-0595-4bb7-90ba-28943e115a14	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
95	43f3bf3d-98ca-40b3-8fca-33d14bc91892	a7d18664-0f10-41b6-adf9-8e824794bc4a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
96	bd5a92d6-b6e9-4e49-b25e-0f46bb24c1ff	5bfbd45c-0a80-4be4-9776-e8651471f5dc	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	2026-07-08 13:39:24.127671	\N	nao_transmitida	\N	[{"nome": "Avaliação clínica ocupacional (anamnese e exame físico)", "fonte": "Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II", "dt_exame": "2025-03-01", "cod_procedimento": "0295"}]
\.


--
-- Data for Name: gp_cats; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gp_cats (id, cat_id, employee_id, tipo_acidente, data_acidente, hora_acidente, local, descricao, gravidade, parte_corpo, agente_causador, testemunhas, afastamento, numero_cat_inss, status, created_at, updated_at, numero_recibo_esocial, esocial_status, esocial_transmitida_em, esocial_protocolo) FROM stdin;
1	CAT-2026-001	0754e0aa-0be4-4253-9816-003c0149c1cd	tipico	2026-03-20	\N	Estacionamento B2 Mirante das Flores	Escorregou no piso molhado descendo rampa	leve	\N	\N	\N	0	\N	aberta	2026-03-29 20:45:39.136029	\N	\N	nao_transmitida	\N	\N
2	CAT-2026-002	430bc8bc-da1a-4667-b6fc-578774e5d2cf	trajeto	2026-03-15	\N	Av das Torres proximo ao Prime Arena	Acidente de moto no trajeto trabalho	leve	\N	\N	\N	0	\N	aberta	2026-03-29 20:45:39.136029	\N	\N	nao_transmitida	\N	\N
3	CAT-2026-003-CINTIA	4f4d6166-1327-40e7-89e8-29e0736fbcfe	trajeto	2026-05-21	06:45	Via Arterial Norte, Rua Manoel Ortiz S/N, Compensa, Manaus-AM (CEP 69036-310)	Acidente de trajeto. CID T07 - traumatismos multiplas regioes; fratura femur distal/tibia direita com cirurgia e internacao. Atendimento 21/05 11:48, Dr. Fernando Moralles Espinosa CRM-AM 2236. Tratamento 15d + afastamento. Codigos eSocial: sitGeradora 200004600, parteAting 757010600 (lat.2), agente 303075900, lesao 702035000. TRANSMITIDA PELA MB CONSULTORIA (INDEXMED, CNPJ 41.339.889/0001-13). Dossie: uploads/sst_mb/	grave	Multiplas regioes (fratura femur/tibia direita)	Acidente de transito (trajeto)	\N	15	1.1.0000000041689118049	registrada_inss	2026-07-08 00:55:05.099433	\N	1.1.0000000041689118049	aceita	2026-06-25 22:17:00+00	1.1.202606.0000000013335372706
\.


--
-- Data for Name: sst_afastamentos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sst_afastamentos (id, employee_id, employee_nome, employee_cargo, tipo, motivo, data_inicio, data_fim_prevista, data_retorno, dias_previstos, atestado, cid, medico, crm, status, ajuda_medicamento_ativa, ajuda_medicamento_valor, gera_estabilidade, estabilidade_ate, observacoes, created_at, updated_at, encaminhado_inss, data_encaminhamento_inss, recibo_s2230, esocial_status, esocial_protocolo) FROM stdin;
6aa7a9c0-5220-49f5-936d-75bcd1ba2c93	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	FERNANDA VINHOTE MACIEL	Agente de Portaria	doenca	Doenca com atestado medico	2026-02-22	\N	\N	\N	t	M54	Dra. Ana Beatriz Costa	CRM-AM 3897	ativo	t	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-15 16:59:53.412998+00	f	\N	\N	nao_transmitida	\N
1a112f87-cb23-47c4-b8a2-50bbc3f18342	b2b39603-19a1-4050-b062-98e500198012	GELSON BERNARDO LIMA	Agente de Portaria	doenca	Doenca com atestado medico — 6 dias	2026-02-22	2026-02-28	2026-02-28	6	t	J03	Dr. Carlos Mendes	CRM-AM 4521	encerrado	f	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-16 00:18:39.123943+00	f	\N	\N	nao_transmitida	\N
dfb938af-0e8d-4503-9527-0f024fbd5136	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	CARLOS ALBERTO ASSIS DE LIMA	Artifice	doenca	Doenca com atestado medico	2026-03-02	\N	\N	\N	t	M51	Dr. Roberto Silva	CRM-AM 5102	ativo	t	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-15 16:59:53.412998+00	f	\N	\N	nao_transmitida	\N
5227c094-e969-4de8-a2e5-b37fde4d6676	2430761d-172e-44b8-a817-edfea166e321		\N	doenca	Dengue — atestado medico 7 dias	2026-03-25	\N	\N	\N	t	A90	Dr. Carlos Mendes	CRM-AM 5432	ativo	t	300.00	f	\N	\N	2026-03-29 20:34:06.885731+00	2026-03-29 20:34:06.885731+00	f	\N	\N	nao_transmitida	\N
00157b5c-a28e-4b1e-9db1-6d1b13202d0a	12423164-f7d8-4db3-bf36-cffebda5948e	KALEL SILVA DE JESUS	Artifice	doenca	Doenca com atestado medico — 60 dias	2026-03-04	2026-05-03	2026-05-03	60	t	S82	Dr. Roberto Silva	CRM-AM 5102	encerrado	t	300.00	f	\N	ATENCAO: Afastamento > 15 dias — encaminhar para INSS (B31/B91). Data prevista encaminhamento: 2026-03-19.	2026-03-15 16:59:53.412998+00	2026-05-30 15:47:57.431215+00	t	2026-03-19	\N	nao_transmitida	\N
37838f4c-abd9-4c5b-9be0-9b3dd3fbc0ef	82a1d1d6-401d-487a-928f-42ed29756bca	ARYELTON BRAGA FIGUEIRA	AGENTE DE PORTARIA	suspensao_contratual	Suspensão contratual por ajuizamento de rescisão indireta (eSocial motivo 44). Recibo 1.1.0000000037643.	2026-02-02	\N	\N	\N	f	\N	\N	\N	ativo	f	\N	f	\N	\N	2026-07-02 16:45:33.470546+00	2026-07-02 16:45:33.470546+00	f	\N	\N	nao_transmitida	\N
25fc57d2-3af2-4f3f-9fa1-ca5efce4dd76	a85f315b-4029-4eb1-9584-7a22ed3a7c78	RAILSON COELHO BATISTA	Agente de Servicos Gerais	doenca	Doenca com atestado medico — 2 dias	2026-02-20	2026-02-22	2026-02-22	2	t	J06	Dr. Carlos Mendes	CRM-AM 4521	encerrado	f	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-07-07 23:18:35.153453+00	f	\N	\N	transmitida	1.2.202607.0000000000217663514
61a7f4b0-cc7d-4e79-a1fc-4acbcbd68776	4f4d6166-1327-40e7-89e8-29e0736fbcfe	CINTIA BEZERRA OLIVEIRA	AGENTE DE PORTARIA	acidente_trajeto	Acidente de trajeto 21/05/2026 - fratura femur/tibia direita (CID T07), cirurgia + internacao	2026-05-21	\N	\N	\N	t	T07	Fernando Moralles Espinosa	CRM-AM 2236	em_andamento	f	\N	t	2027-05-21	Importado do dossie MB Consultoria (Drive 07/07/2026). CAT S-2210 ja registrada no INSS (recibo 1.1.0000000041689118049). VERIFICAR com a MB/Marcia se o S-2230 tambem foi transmitido antes de transmitir pelo Conecta PRO.	2026-07-08 00:53:53.197571+00	2026-07-08 00:53:53.197571+00	t	\N	\N	nao_transmitida	\N
\.


--
-- Name: gp_asos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_asos_id_seq', 96, true);


--
-- Name: gp_cats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_cats_id_seq', 3, true);


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
-- Name: gp_cats gp_cats_cat_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_cats
    ADD CONSTRAINT gp_cats_cat_id_key UNIQUE (cat_id);


--
-- Name: gp_cats gp_cats_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_cats
    ADD CONSTRAINT gp_cats_pkey PRIMARY KEY (id);


--
-- Name: sst_afastamentos sst_afastamentos_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sst_afastamentos
    ADD CONSTRAINT sst_afastamentos_pkey PRIMARY KEY (id);


--
-- Name: idx_sst_af_emp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sst_af_emp ON public.sst_afastamentos USING btree (employee_id);


--
-- Name: idx_sst_af_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sst_af_status ON public.sst_afastamentos USING btree (status);


--
-- Name: ix_gp_aso_employee; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_aso_employee ON public.gp_asos USING btree (employee_id);


--
-- Name: ix_gp_cat_employee; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_cat_employee ON public.gp_cats USING btree (employee_id);


--
-- Name: gp_asos fk_aso_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT fk_aso_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: sst_afastamentos fk_sa_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sst_afastamentos
    ADD CONSTRAINT fk_sa_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict gizRLAyYfH7t2QRY3VhSNeP8iZOpGm9V9ll59LVDNCsdIRcSQndkY5JQ2fTaiQm

