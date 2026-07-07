--
-- PostgreSQL database dump
--

\restrict k0DOCwmLaNKSAO1FQOId41g5abnfmT7XbMtPa2NWKiHVWYCc3t6TFfbZxGC3rtd

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
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL
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
    numero_cat_inss character varying(20),
    status character varying(20) DEFAULT 'aberta'::character varying,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    numero_recibo_esocial character varying(60),
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL,
    esocial_transmitida_em timestamp with time zone
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
-- Name: gp_epi_deliveries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gp_epi_deliveries (
    id integer NOT NULL,
    delivery_id character varying(36) NOT NULL,
    employee_id uuid NOT NULL,
    epi_nome character varying(255) NOT NULL,
    epi_ca character varying(20),
    quantidade integer DEFAULT 1,
    nr character varying(10) DEFAULT 'NR-6'::character varying,
    data_entrega date NOT NULL,
    data_validade date,
    data_devolucao date,
    motivo_devolucao text,
    assinatura_funcionario character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.gp_epi_deliveries OWNER TO postgres;

--
-- Name: gp_epi_deliveries_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gp_epi_deliveries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gp_epi_deliveries_id_seq OWNER TO postgres;

--
-- Name: gp_epi_deliveries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gp_epi_deliveries_id_seq OWNED BY public.gp_epi_deliveries.id;


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
    esocial_status character varying(20) DEFAULT 'nao_transmitida'::character varying NOT NULL
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
-- Name: gp_asos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos ALTER COLUMN id SET DEFAULT nextval('public.gp_asos_id_seq'::regclass);


--
-- Name: gp_cats id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_cats ALTER COLUMN id SET DEFAULT nextval('public.gp_cats_id_seq'::regclass);


--
-- Name: gp_epi_deliveries id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_epi_deliveries ALTER COLUMN id SET DEFAULT nextval('public.gp_epi_deliveries_id_seq'::regclass);


--
-- Data for Name: gp_asos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gp_asos (id, aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, data_validade, clinica, medico, crm, apto, restricoes, observacoes, documento_url, created_at, updated_at, recibo_s2220, esocial_status) FROM stdin;
1	95c5a1ed-40f8-4cbe-ba0a-ff6b41f14a0c	ab54e4fc-627f-44cd-ae92-c43b459a90ec	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
2	9ab801a3-b0a5-43cc-922d-7df52430a899	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
3	81235445-7993-416a-947c-d9624d28f077	4392a2d4-ea9b-4692-a1f9-289460aab766	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
4	229a65bd-51cd-4978-bbfe-975e88a82fbb	0d7f8148-337c-4c66-9000-c9589a23c88a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
5	9af67765-0188-4649-8375-fe4e93eaee3a	5e9fa756-5e32-4772-861b-4bb8bff00ffe	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
6	6e45cad1-2bbe-4534-8100-0dbcd77ea7c6	176f110f-237c-44c6-bad3-e5ba7e495b3a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
7	1ad5d38f-aad2-42b3-8bcd-c7ade9e96dbf	a85f315b-4029-4eb1-9584-7a22ed3a7c78	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
8	059f4e34-f374-4b19-814d-605fdd1838d0	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
9	b811e3f2-c99a-4830-9e4f-20b122f40079	e32ea647-7470-43b0-a560-abd3eb6ff412	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
10	5c2afdec-7ac7-4f59-81bc-7d2013c011ee	4f4d6166-1327-40e7-89e8-29e0736fbcfe	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
11	4fc65216-a2cb-4c8c-bb02-be3ac7486203	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
12	cfa8f124-d60a-4d82-856c-bb71d7d3e514	795abf6c-0a41-4b26-9094-87142591e01d	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
13	c2d659f6-95ba-4e23-9b42-9ad88a9185cd	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
14	a1e167f9-0efa-402b-9be1-670cd1c00931	f5fe3ccb-8529-4525-9241-5f031d3b9204	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
15	51da0f2f-3f1a-4cb2-8d73-d87fde2d363d	e0f63eca-6ace-4169-880e-9c021872329a	admissional	realizado	\N	2026-02-23	2027-02-23	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
16	bd4f1f8a-a362-4140-a017-3eb66dd93a2c	82a1d1d6-401d-487a-928f-42ed29756bca	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
17	56afa8dd-be31-483e-af08-ae399e981ee0	7ccefd89-b89d-463a-a0ba-ffa6475159fb	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
18	d599af38-0e31-4ce0-9121-10be7a9094aa	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
19	8800ee3a-b055-49b2-aebb-2c78aca5626f	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
20	0eb0a1ba-2750-48fe-8ca8-4dada1cb0a64	500922e3-4866-454a-8f06-d5685e8e25c1	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
21	099d77c5-81de-4491-8b30-c5b3768105ea	109edac0-17a1-4cd4-8bf8-8b7062d905d0	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
22	3a780e76-f290-4c25-8e48-62ca716453af	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
23	6e4fcf33-e729-4097-b79c-a83e351eb8b7	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
24	e1be4945-f7ed-42ab-a484-231766acab69	4f6d1b27-d05b-4315-aa86-f245d70e52bb	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
25	667f8371-827b-4bc2-b034-6777c17ce174	12423164-f7d8-4db3-bf36-cffebda5948e	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
26	87ed08d3-089b-49e9-be2d-010a49d1d8e5	29dae28f-e688-4df0-8879-2704d8351d87	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
27	cf7cdd75-e3d6-4dfb-8094-0552d77682cf	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
28	b98f77e4-47e6-4d57-a024-18076a39419f	9e9e1678-9988-490c-b59b-b2786bb67e1c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
29	c1fd7cd1-8e8f-4661-85a4-a8f866713b87	a7d7cb41-0223-466c-8c2b-5353c9fa1511	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
30	4fc23f59-9d4e-45eb-aab6-8c50e9caf775	0754e0aa-0be4-4253-9816-003c0149c1cd	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
31	37ff888c-cdc2-46a4-8db7-a1e108ece4bb	2430761d-172e-44b8-a817-edfea166e321	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
32	25b3e324-875f-45b5-abfb-bbeb969a57d8	13a02a88-abdc-48e0-b128-d1005ba57a04	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
33	d72a4695-f6d5-4aa3-836b-498798e37569	430bc8bc-da1a-4667-b6fc-578774e5d2cf	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
34	15a92c0e-df79-4162-81ca-61dc5a6ecf0f	0d7887cc-d824-44ff-86be-201c7ab70dc6	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
35	3afb394b-d9fd-433c-a4a8-cd804170cf47	58e002c7-7df8-42a8-aef9-0607d41a306c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
36	df751d49-a64f-4642-9ba5-662368efb4e9	706edbc3-e0b9-438a-98e7-c2bf7c40db42	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
37	f6d65344-85c1-498f-ac8f-772065c5c6bf	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
38	f4753207-1f4a-4514-9de6-576645433c4c	eb84be29-7760-4d64-9688-dd5433172283	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
39	f5988dd0-4356-4ab3-a5b1-28d4e88bd1c5	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
40	ad0af5e4-fe20-45d8-9d86-7eb13ec5859a	89f89f2c-b0dd-430a-ae84-e4d35981a498	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
41	5e5d8729-f06c-43c2-b6fc-c30f4b70a300	41587c09-1b42-469f-9c65-4419c870d07c	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
42	ae2b9796-2265-4111-9fcf-e37d891ad1e0	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
43	409ba4ae-9be6-4dff-b22a-0b2f07c2ec39	783a8170-e951-4406-856e-6b0cc659d8c3	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
44	d0262595-a556-4c90-8ea2-95c0f7f155f1	b2b39603-19a1-4050-b062-98e500198012	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
45	c68e7f54-8ed5-4240-bf63-de83ddfc9d1f	4714fbc7-608b-443d-9669-7b1d54897b92	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
46	d7472666-a360-431f-9837-4d3c7a0c8b14	13a74a88-beef-4b40-af78-66e15a8f9dff	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
47	d62b98fc-5b58-473f-b419-c489073a8135	2938d6a4-ca53-4406-ad1d-1309fa555fe6	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
48	2f15e53f-301a-476f-865a-8c6784eda637	62897018-8de6-4c8d-85da-dfb0acb8a105	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
49	5abe7c25-f090-4b5a-9eb0-f97702aaaa98	c58e8b76-916e-4959-b1dc-7327e110a516	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
50	3af45615-5835-4369-8a74-fd7614bdd523	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
51	4c1167c8-4795-49a1-98c4-bd397488e0e1	a7d18664-0f10-41b6-adf9-8e824794bc4a	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
52	48ab24f4-445e-4ecb-98b9-b61b11e21be6	5bfbd45c-0a80-4be4-9776-e8651471f5dc	admissional	realizado	\N	2025-06-01	2026-06-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
53	c82303d3-3591-41a8-8238-d53f79cbd096	ab54e4fc-627f-44cd-ae92-c43b459a90ec	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
54	391a9ef5-8251-43f0-a60e-a71e0920de93	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
55	eeecd1df-17c6-4e5a-9886-11126fac424c	4392a2d4-ea9b-4692-a1f9-289460aab766	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
56	7deef76b-fd7a-4e5f-a407-f0bb7fb718a4	0d7f8148-337c-4c66-9000-c9589a23c88a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
57	8ccfa645-2415-4a4e-ad7f-b7a6260d54d5	5e9fa756-5e32-4772-861b-4bb8bff00ffe	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
58	687cb29c-46e0-4cff-894c-edfc84cb5935	176f110f-237c-44c6-bad3-e5ba7e495b3a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
59	3df6ba84-e3be-4f97-920a-06f6508af5d8	a85f315b-4029-4eb1-9584-7a22ed3a7c78	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
60	308e9eb7-3098-480c-910d-c11994b27980	82a1d1d6-401d-487a-928f-42ed29756bca	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
61	972ee2f7-b5fa-4a37-b632-f1f818d82a78	7ccefd89-b89d-463a-a0ba-ffa6475159fb	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
62	8d6d4c0a-bec2-4134-823a-3b9db2414677	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
63	57bbd228-a82f-4d58-bff8-a48e6e365e4e	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
64	fa8af216-cedb-4909-a32e-4ec7162a8cf3	500922e3-4866-454a-8f06-d5685e8e25c1	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
65	89294cd7-6c6d-42ce-b34b-6489e96f6273	109edac0-17a1-4cd4-8bf8-8b7062d905d0	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
66	91280d20-f412-4db2-99e2-0e36ebf5dc80	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
67	c28ed25a-fe03-4c1e-a691-07d3bf779a8f	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
68	6f83969c-5d0e-4a04-a4bc-421dd72d2ec1	4f6d1b27-d05b-4315-aa86-f245d70e52bb	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
69	4a27a8aa-7412-4c1f-a795-7da57511268b	12423164-f7d8-4db3-bf36-cffebda5948e	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
70	e0165adc-7393-461c-b54d-e4b921d33844	29dae28f-e688-4df0-8879-2704d8351d87	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
71	06227d6e-b5d4-423b-b1a3-9df376c2c995	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
72	7001bdba-2fc6-442a-9eef-6fa866c74f5b	9e9e1678-9988-490c-b59b-b2786bb67e1c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
73	300fff34-ba98-4c80-a900-0e7d19b1d08e	a7d7cb41-0223-466c-8c2b-5353c9fa1511	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
74	4e50bf14-1bf6-484f-9b93-e76ade0f458d	0754e0aa-0be4-4253-9816-003c0149c1cd	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
75	ecdec62a-932d-4830-b734-fb217c21e993	2430761d-172e-44b8-a817-edfea166e321	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
76	288a3e9e-7e7e-4168-ad85-1376735f8de4	13a02a88-abdc-48e0-b128-d1005ba57a04	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
77	2c6836a9-5dcb-429d-88ef-f6c63bbf3ac3	430bc8bc-da1a-4667-b6fc-578774e5d2cf	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
78	46fd2638-a567-4edd-8f81-1b065790eeda	0d7887cc-d824-44ff-86be-201c7ab70dc6	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
79	41d551e1-84b9-4ab6-9f7f-3b2c127dc6a2	58e002c7-7df8-42a8-aef9-0607d41a306c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
80	446175ba-117b-439b-8c0c-94a4aa9befe2	706edbc3-e0b9-438a-98e7-c2bf7c40db42	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
81	e04a5b9e-9887-4978-891c-3a6807f53285	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
82	b26e1495-34bd-45dc-a0c5-85264df7638d	eb84be29-7760-4d64-9688-dd5433172283	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
83	ef6ef8f7-066a-49f1-a36f-e0bded3bca2d	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
84	22cd204b-c52f-44d8-b2c4-d961e09c4639	89f89f2c-b0dd-430a-ae84-e4d35981a498	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
85	caaa7c26-5076-417a-8e98-a6042a8d4b83	41587c09-1b42-469f-9c65-4419c870d07c	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
86	f00bfa13-fd59-47ca-b77c-5213b96676be	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
87	4da74fc8-78d3-418f-8668-0f82987a3fef	783a8170-e951-4406-856e-6b0cc659d8c3	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
88	8631c952-5726-4331-8028-d30baa2b4b3d	b2b39603-19a1-4050-b062-98e500198012	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
89	7535fc51-bf64-4163-849a-6735ed4d1358	4714fbc7-608b-443d-9669-7b1d54897b92	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
90	65747fa4-cec5-4827-bd98-e0cc5387a45c	13a74a88-beef-4b40-af78-66e15a8f9dff	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
91	f7484a14-5855-44e7-aa4f-ac0bf7c9ec93	2938d6a4-ca53-4406-ad1d-1309fa555fe6	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
92	0ece941f-9180-41c2-93d1-7f9114dbb90e	62897018-8de6-4c8d-85da-dfb0acb8a105	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
93	a2ee9fd0-4090-43e5-86af-4db5d3f97801	c58e8b76-916e-4959-b1dc-7327e110a516	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
94	b21d0a34-0595-4bb7-90ba-28943e115a14	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
95	43f3bf3d-98ca-40b3-8fca-33d14bc91892	a7d18664-0f10-41b6-adf9-8e824794bc4a	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
96	bd5a92d6-b6e9-4e49-b25e-0f46bb24c1ff	5bfbd45c-0a80-4be4-9776-e8651471f5dc	periodico	vencido	\N	2025-03-01	2026-03-01	\N	Dr. Carlos Mendes	CRM-AM 4521	t	\N	\N	\N	2026-03-16 00:08:17.281448	\N	\N	nao_transmitida
\.


--
-- Data for Name: gp_cats; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gp_cats (id, cat_id, employee_id, tipo_acidente, data_acidente, hora_acidente, local, descricao, gravidade, parte_corpo, agente_causador, testemunhas, afastamento, numero_cat_inss, status, created_at, updated_at, numero_recibo_esocial, esocial_status, esocial_transmitida_em) FROM stdin;
1	CAT-2026-001	0754e0aa-0be4-4253-9816-003c0149c1cd	tipico	2026-03-20	\N	Estacionamento B2 Mirante das Flores	Escorregou no piso molhado descendo rampa	leve	\N	\N	\N	0	\N	aberta	2026-03-29 20:45:39.136029	\N	\N	nao_transmitida	\N
2	CAT-2026-002	430bc8bc-da1a-4667-b6fc-578774e5d2cf	trajeto	2026-03-15	\N	Av das Torres proximo ao Prime Arena	Acidente de moto no trajeto trabalho	leve	\N	\N	\N	0	\N	aberta	2026-03-29 20:45:39.136029	\N	\N	nao_transmitida	\N
\.


--
-- Data for Name: gp_epi_deliveries; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gp_epi_deliveries (id, delivery_id, employee_id, epi_nome, epi_ca, quantidade, nr, data_entrega, data_validade, data_devolucao, motivo_devolucao, assinatura_funcionario, created_at) FROM stdin;
1	e0b2a455-427b-4949-84a8-6094dae6d674	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
2	6e2bd2ae-cbad-42a5-8c79-409239a939fe	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
3	8e9d5e6c-5c47-425f-9533-738af3ff2b08	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
4	435c2d9c-a058-4d3b-bd0e-6111042cd40d	2e814e1c-d022-4bb4-8e39-62fab36cd4ac	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
5	c5a49bdc-3fa6-41f9-85f6-eb90efb068cc	e32ea647-7470-43b0-a560-abd3eb6ff412	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
6	078c924a-f91d-412a-84f8-2caccf88091f	e32ea647-7470-43b0-a560-abd3eb6ff412	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
7	7885362e-5446-4d98-8d58-117cb12aa745	e32ea647-7470-43b0-a560-abd3eb6ff412	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
8	ca4fb469-5895-4f5d-83e7-8b9570f59243	e32ea647-7470-43b0-a560-abd3eb6ff412	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
9	3525d41c-2b62-47c8-82d9-026d8ce00046	4f4d6166-1327-40e7-89e8-29e0736fbcfe	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
10	66a772fd-d066-4fe7-8a42-913ed66b12bf	4f4d6166-1327-40e7-89e8-29e0736fbcfe	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
11	bc4b1a7a-a3c7-4417-a355-15a3183817e0	4f4d6166-1327-40e7-89e8-29e0736fbcfe	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
12	f1d16c8c-63f6-4c11-b89f-dd2dfb33cf5e	4f4d6166-1327-40e7-89e8-29e0736fbcfe	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
13	bd065e0e-5dba-454e-af58-97d45dd70361	795abf6c-0a41-4b26-9094-87142591e01d	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
14	6aa20bd1-6894-400f-a8b9-07c5348da23c	795abf6c-0a41-4b26-9094-87142591e01d	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
15	7272ba1e-d35d-4164-8873-455c8330981e	795abf6c-0a41-4b26-9094-87142591e01d	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
16	442a8f66-f4ad-4627-a58a-9acce18de886	795abf6c-0a41-4b26-9094-87142591e01d	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
17	482a2b4f-05da-411f-a584-d3d7dfa5222a	f5fe3ccb-8529-4525-9241-5f031d3b9204	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
18	64e7c514-1fb5-4d19-884d-aed1ebeb6f2a	f5fe3ccb-8529-4525-9241-5f031d3b9204	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
19	cba5afc9-8c9b-4d23-b19a-b469a61b56ac	f5fe3ccb-8529-4525-9241-5f031d3b9204	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
20	44459d5f-0595-4b05-bb25-fdd21b0287cb	f5fe3ccb-8529-4525-9241-5f031d3b9204	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
21	c1acb4eb-394f-4110-8696-8bc2f6ba235c	e0f63eca-6ace-4169-880e-9c021872329a	Colete Refletivo	CA-40123	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
22	406d58e6-97b4-4f77-bff6-c80bb11dfcc8	e0f63eca-6ace-4169-880e-9c021872329a	Lanterna Tatica	CA-55789	1	NR-6	2026-02-23	2028-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
23	98ad7ace-738b-4838-a6a3-cd9f63519a49	e0f63eca-6ace-4169-880e-9c021872329a	Capa de Chuva	CA-31456	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
24	551883b6-eabd-4e0b-9594-db9fc5283c20	e0f63eca-6ace-4169-880e-9c021872329a	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
25	127a45ff-30bc-44f7-93a8-50c9cce06cca	82a1d1d6-401d-487a-928f-42ed29756bca	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
26	b9e5d2e0-02ab-4b2f-aeee-963aa5be0d6a	82a1d1d6-401d-487a-928f-42ed29756bca	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
27	421f9620-10fd-4407-9a6d-febe803b208d	82a1d1d6-401d-487a-928f-42ed29756bca	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
28	3ce0d09c-1ed2-42fe-9d4e-87061e4d80ec	82a1d1d6-401d-487a-928f-42ed29756bca	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
29	028af040-8e45-42d2-98d6-e21c5a5a8c04	7ccefd89-b89d-463a-a0ba-ffa6475159fb	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
30	9a21151e-9aad-47e7-b10a-9ef68d434a1f	7ccefd89-b89d-463a-a0ba-ffa6475159fb	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
31	7fb8bc06-2406-4abc-ae75-6dd500fc220a	7ccefd89-b89d-463a-a0ba-ffa6475159fb	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
32	5873fbed-e22f-4ff5-aab9-482bc92f8802	7ccefd89-b89d-463a-a0ba-ffa6475159fb	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
33	f3c9b1dc-23fd-4e65-88f5-3484d75de3e3	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
34	aacb5dc4-80b0-4b25-a990-59a588473957	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
35	63cb8614-a125-461a-9970-dbb8fa4e85da	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
36	124b73e8-29f5-4a8a-91aa-799003aec73e	0adfb14d-4b12-4ac0-9d5a-0570ed4531f5	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
37	059164ae-2f14-44c1-947b-ba1b77faa449	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
38	48e4e363-f485-4656-8a37-2ce86510d8ed	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
39	cec7148f-d5b4-416c-b491-31a73a261d09	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
40	f1b4501c-9ba2-463f-b270-58505b639065	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
41	b25f5b29-0093-4202-bdfe-5a5b8723fafb	500922e3-4866-454a-8f06-d5685e8e25c1	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
42	2df731fb-6793-4d2b-a533-74ae29902abf	500922e3-4866-454a-8f06-d5685e8e25c1	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
43	0b27a3cc-9b0a-4fa9-9496-6b2adf9a4e4b	500922e3-4866-454a-8f06-d5685e8e25c1	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
44	f7f79922-a2ed-431c-88ec-081051027470	500922e3-4866-454a-8f06-d5685e8e25c1	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
45	8c6e752e-94e3-4912-a9dc-f418565b00c6	109edac0-17a1-4cd4-8bf8-8b7062d905d0	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
46	42981bea-93d6-44e4-8130-46125334c7e3	109edac0-17a1-4cd4-8bf8-8b7062d905d0	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
47	17c2b14d-62b9-44c1-8926-e7781052afc8	109edac0-17a1-4cd4-8bf8-8b7062d905d0	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
48	330778bc-d95c-4ef6-9fb5-040c72a3aca0	109edac0-17a1-4cd4-8bf8-8b7062d905d0	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
49	6b577824-08eb-4d78-9d7d-67862208ebd8	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
50	2d5e1b1b-5f28-4ec7-a7a8-b8112f881dc2	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
51	f505ccd2-8b09-4e14-ad2a-b6ba2c7d0946	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
52	7ee8f007-f022-4dce-8569-f865c6eb1a4b	4fb9bcb3-8ca9-42b7-903e-6c2e0ee7d12e	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
53	fdb02b2b-3c81-4c35-9ccb-bc1cda718f34	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
54	f9b64b4e-156f-4f78-bd28-1baacde1de2b	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
55	6a8043b3-4937-444d-a5b5-b4e3f9cd19cf	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
56	f13d5b64-303f-45b2-bec9-2946c7f0783f	2b4f0614-f3c4-4acd-bdce-cf16d27c3fc2	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
57	8b7a5b72-801c-4362-8205-ab617d0520de	a7d7cb41-0223-466c-8c2b-5353c9fa1511	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
58	1fdcc6ad-4a72-4305-9769-5174875d1136	a7d7cb41-0223-466c-8c2b-5353c9fa1511	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
59	17fbc5b2-57c6-4875-8e29-baf3f76e0dbf	a7d7cb41-0223-466c-8c2b-5353c9fa1511	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
60	5251da53-6030-44fa-9661-3a551e73f8c7	a7d7cb41-0223-466c-8c2b-5353c9fa1511	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
61	0ebf036c-76a5-4552-bb1a-339da477ea23	2430761d-172e-44b8-a817-edfea166e321	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
62	b7070782-3bf3-414e-956b-92f0763807f0	2430761d-172e-44b8-a817-edfea166e321	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
63	b1598763-7e0c-4a6c-a288-f2ce61557355	2430761d-172e-44b8-a817-edfea166e321	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
64	876144c4-c41d-4888-a3c4-4431f4c5a425	2430761d-172e-44b8-a817-edfea166e321	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
65	e5ba83ee-0f51-4db3-bcdb-0d264830c2a7	13a02a88-abdc-48e0-b128-d1005ba57a04	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
66	ed594e83-b98f-49ab-b2e5-d6f32d57b9a5	13a02a88-abdc-48e0-b128-d1005ba57a04	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
67	419cfdf3-241e-43f8-936e-9eaaa9bdfba4	13a02a88-abdc-48e0-b128-d1005ba57a04	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
68	e2983eaa-85e5-4cbf-b64e-f5d60838893b	13a02a88-abdc-48e0-b128-d1005ba57a04	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
69	8f308433-acf6-4774-94c3-3dafca47fd72	430bc8bc-da1a-4667-b6fc-578774e5d2cf	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
70	b5fa6360-983a-4813-81c5-040ede963378	430bc8bc-da1a-4667-b6fc-578774e5d2cf	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
71	c6a39022-6463-4163-ba28-bb479bbfee0a	430bc8bc-da1a-4667-b6fc-578774e5d2cf	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
72	8fbdc5ae-b20a-4661-a8c4-905ee86329cb	430bc8bc-da1a-4667-b6fc-578774e5d2cf	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
73	0f751ef1-2071-4f24-81ea-02622a3079c7	0d7887cc-d824-44ff-86be-201c7ab70dc6	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
74	4d0bbb0a-529d-44f1-9637-c62b7cdc42ad	0d7887cc-d824-44ff-86be-201c7ab70dc6	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
75	31a10cfa-8fc1-4d00-b24c-d6ed91745d40	0d7887cc-d824-44ff-86be-201c7ab70dc6	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
76	e6d41a05-33a5-40cc-b57a-066e16beea43	0d7887cc-d824-44ff-86be-201c7ab70dc6	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
77	34de9df4-dc71-4762-b122-a86a7ff3be6b	58e002c7-7df8-42a8-aef9-0607d41a306c	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
78	d8bd5a7c-e677-4d17-8643-28701cc44adf	58e002c7-7df8-42a8-aef9-0607d41a306c	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
79	b541cff4-e96a-47f1-8ab1-e14cb631fa23	58e002c7-7df8-42a8-aef9-0607d41a306c	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
80	cf4339f7-f468-44c3-a461-ed797ab7b878	58e002c7-7df8-42a8-aef9-0607d41a306c	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
81	3cd27bef-2851-4332-a61b-19aabab46b84	706edbc3-e0b9-438a-98e7-c2bf7c40db42	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
82	053c2d12-8646-4bf0-8fa0-7b0b96701c38	706edbc3-e0b9-438a-98e7-c2bf7c40db42	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
83	64c2aede-a986-43f4-bc90-58c488176ce7	706edbc3-e0b9-438a-98e7-c2bf7c40db42	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
84	cbc31c3f-6781-4ad2-a641-3a3e254eefa5	706edbc3-e0b9-438a-98e7-c2bf7c40db42	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
85	6f746eba-13ef-45ac-af10-4a1f6cac0273	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
86	8e9076f5-40be-4eae-9173-ba19b5d249fc	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
87	ec8936e9-4fe9-4654-b7c5-9289b278c04f	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
88	dcdbf019-9487-4c97-a177-dca47afb5984	e38fc9dc-dd7c-44f7-af7b-952ec4c7ccb2	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
89	98eb1350-4be5-4ece-a3fc-e21b2f42bd5d	eb84be29-7760-4d64-9688-dd5433172283	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
90	df11d840-0b37-40db-a14d-ff75750c6718	eb84be29-7760-4d64-9688-dd5433172283	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
91	47fa0df9-fdde-4c6d-b30b-2fb4d9f44e5f	eb84be29-7760-4d64-9688-dd5433172283	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
92	5f17422c-4490-4a29-8cdb-b2f15f03286b	eb84be29-7760-4d64-9688-dd5433172283	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
93	c83c35d4-ca28-470d-90bc-94a396ef1a15	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
94	6f4c239d-380f-432f-9832-ef3717f32b22	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
95	7db14257-f650-47ec-b5f1-708dc20ae6ea	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
96	16d13862-38c3-4781-ae30-cde508addac6	ebfc72fe-7081-47b8-bce6-88b81cdcb09a	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
97	2a86c940-399c-47ec-a426-c5a33b990a79	89f89f2c-b0dd-430a-ae84-e4d35981a498	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
98	10672ac3-5803-47db-a2b9-5764d72592dd	89f89f2c-b0dd-430a-ae84-e4d35981a498	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
99	699cc407-eb06-40ef-847b-8807c80b6598	89f89f2c-b0dd-430a-ae84-e4d35981a498	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
100	02b10fe1-1d25-4eb7-8019-b9e9ce621a2e	89f89f2c-b0dd-430a-ae84-e4d35981a498	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
101	9c3dda89-e50f-4643-b019-e3d2bdb53964	41587c09-1b42-469f-9c65-4419c870d07c	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
102	8bf88af9-c312-4c97-abd6-30076d4c8932	41587c09-1b42-469f-9c65-4419c870d07c	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
103	92d758d5-70f3-4826-be42-e4ae33503373	41587c09-1b42-469f-9c65-4419c870d07c	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
104	b7dc94f4-4d94-4b5c-b4ea-e2839221cf6c	41587c09-1b42-469f-9c65-4419c870d07c	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
105	e5065fc2-e42b-44c6-ac35-f7a5bdeb611d	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
106	5591ad76-6d42-4931-8ae9-742edb59b88a	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
107	61828934-01d5-4c4c-8ba8-bed05e165579	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
108	c37e22ae-a638-4024-a851-eb04a2eef1d3	7e5e4c49-a1d2-4bbf-8699-9e2fa22063aa	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
109	f3d8edef-74d1-4921-8523-e71c0c8002fc	b2b39603-19a1-4050-b062-98e500198012	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
110	4eb4cdf5-25b8-400a-9f78-50fcbfc39e6e	b2b39603-19a1-4050-b062-98e500198012	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
111	1357de5d-7300-4f3f-8492-21fa6ecddf63	b2b39603-19a1-4050-b062-98e500198012	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
112	bc5b34a5-5e92-436f-b7a6-5807b2fe9cad	b2b39603-19a1-4050-b062-98e500198012	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
113	eb1fc3c1-359a-409c-bfb3-f99aecc0bf46	4714fbc7-608b-443d-9669-7b1d54897b92	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
114	d8a21cee-019f-4076-bacd-da70c0707c83	4714fbc7-608b-443d-9669-7b1d54897b92	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
115	4cac2e0e-3155-4e0d-a9b3-7255d1d84c9f	4714fbc7-608b-443d-9669-7b1d54897b92	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
116	4657dda8-714e-41e4-ae89-18bce44734a5	4714fbc7-608b-443d-9669-7b1d54897b92	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
117	15e1570f-c143-41ef-bc2e-0420eabc44c5	13a74a88-beef-4b40-af78-66e15a8f9dff	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
118	ce73a364-7161-4ffc-8ca6-8176db15b705	13a74a88-beef-4b40-af78-66e15a8f9dff	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
119	76598620-80f9-4a4f-9ba3-1c8b610a5d81	13a74a88-beef-4b40-af78-66e15a8f9dff	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
120	e010e8fd-d466-43a6-be8d-92bcbd825fd1	13a74a88-beef-4b40-af78-66e15a8f9dff	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
121	3d734e9a-f736-4d04-9966-613d1235a536	2938d6a4-ca53-4406-ad1d-1309fa555fe6	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
122	622de245-524c-40c3-8354-1dda44ee789e	2938d6a4-ca53-4406-ad1d-1309fa555fe6	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
123	92c41b1e-811a-47c1-921f-c47198291e93	2938d6a4-ca53-4406-ad1d-1309fa555fe6	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
124	e72d4c33-3e03-4409-b237-bc5cdc1be2d6	2938d6a4-ca53-4406-ad1d-1309fa555fe6	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
125	fe45de1a-b3d4-4ab7-9757-2faf3b54e3dc	62897018-8de6-4c8d-85da-dfb0acb8a105	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
126	081e574e-534d-4803-b88f-09dd57f065c1	62897018-8de6-4c8d-85da-dfb0acb8a105	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
127	82c2cd7e-57d7-41de-926b-68154e058917	62897018-8de6-4c8d-85da-dfb0acb8a105	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
128	ca8237bf-8bfd-4055-97e8-408421ece506	62897018-8de6-4c8d-85da-dfb0acb8a105	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
129	c1fa3411-6bd5-4c4f-b3d0-3b744783b252	c58e8b76-916e-4959-b1dc-7327e110a516	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
130	1b221919-62d6-430c-932b-c1bf354dda0f	c58e8b76-916e-4959-b1dc-7327e110a516	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
131	d1a858bd-7cf1-4715-8457-ecc9ebf80674	c58e8b76-916e-4959-b1dc-7327e110a516	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
132	a961fa34-e1af-4bc1-9f80-5202f17d3b46	c58e8b76-916e-4959-b1dc-7327e110a516	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
133	bc59002b-9ca4-456f-9282-fa690440d8f7	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
134	1eb676a4-b9b0-42e0-b5ea-1f4cfc981bee	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
135	baac0cba-0c98-49fa-b2b7-7b5fb2f560cf	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	Capa de Chuva	CA-31456	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
136	6b48ec4a-31e1-4623-84cd-0744d4d8a1dd	7d6280ad-2471-43e1-9d0c-5a8f576e79b1	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
137	06c2b754-e6f8-498e-9a88-e60757163a2d	4392a2d4-ea9b-4692-a1f9-289460aab766	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
138	8861baa3-56e4-444c-a0d3-fedab77f6772	4392a2d4-ea9b-4692-a1f9-289460aab766	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
139	4070279d-651e-489c-896e-ae1c09cc2734	4392a2d4-ea9b-4692-a1f9-289460aab766	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
140	1455494e-f9e8-4260-b323-e8a33253020f	4392a2d4-ea9b-4692-a1f9-289460aab766	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
141	2160cc2b-95a2-4b24-a310-1c1bc3991f5f	4392a2d4-ea9b-4692-a1f9-289460aab766	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
142	6448c347-32b3-45d0-951f-5db386e450aa	0d7f8148-337c-4c66-9000-c9589a23c88a	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
143	4a193072-1274-4a25-821f-e13707cd8e73	0d7f8148-337c-4c66-9000-c9589a23c88a	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
144	2320a257-39ca-413d-b05c-0eb5f94f2036	0d7f8148-337c-4c66-9000-c9589a23c88a	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
145	9fe9299d-9b31-4972-88eb-dce046dd1e80	0d7f8148-337c-4c66-9000-c9589a23c88a	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
146	aa7e3623-e172-400a-b4bf-d49e3d2f393c	0d7f8148-337c-4c66-9000-c9589a23c88a	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
147	4bc564c1-ceda-436f-976d-b9e816379bea	5e9fa756-5e32-4772-861b-4bb8bff00ffe	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
148	713d007e-4052-4a61-8a44-915eb66b8a39	5e9fa756-5e32-4772-861b-4bb8bff00ffe	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
149	228086f3-fac8-41a5-ab1b-64b652cb1f5b	5e9fa756-5e32-4772-861b-4bb8bff00ffe	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
150	f08889d5-295f-4459-986e-cb3e6a11c4a0	5e9fa756-5e32-4772-861b-4bb8bff00ffe	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
151	38131539-e435-43ff-b33e-9a862ea06a78	5e9fa756-5e32-4772-861b-4bb8bff00ffe	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
152	90a14332-502d-44c1-9bcc-3a1d887d5ecc	176f110f-237c-44c6-bad3-e5ba7e495b3a	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
153	5dc29af9-eff6-4165-81de-9f980c7fd30d	176f110f-237c-44c6-bad3-e5ba7e495b3a	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
154	c4870085-fa68-40ae-96b0-5308c96363c9	176f110f-237c-44c6-bad3-e5ba7e495b3a	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
155	9101b3a5-6066-42a3-9c03-66d4b6e151e7	176f110f-237c-44c6-bad3-e5ba7e495b3a	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
156	e95fbece-5b11-49b2-9a5a-8a613f7f2773	176f110f-237c-44c6-bad3-e5ba7e495b3a	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
157	3941408d-0400-49f9-bb47-073cd44c0194	a85f315b-4029-4eb1-9584-7a22ed3a7c78	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
158	7ec20fd8-a431-4133-8a3c-5dae3bbb1a84	a85f315b-4029-4eb1-9584-7a22ed3a7c78	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
159	6b3b07f4-fb4f-4f3d-8bec-b13430b66f2c	a85f315b-4029-4eb1-9584-7a22ed3a7c78	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
160	19d4a740-7b5f-4872-8af5-59f43d0e3cb3	a85f315b-4029-4eb1-9584-7a22ed3a7c78	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
161	54fd7301-cc60-43f0-ad3c-90aad535c8fd	a85f315b-4029-4eb1-9584-7a22ed3a7c78	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
162	717e265b-1f4a-4a4c-9abb-c9fb4c12b8ac	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	Luvas de Latex	CA-11234	1	NR-6	2026-02-23	2026-05-23	\N	\N	\N	2026-03-16 00:08:35.000287
163	ab19bea0-cf9b-4829-bd7c-8581db54d62c	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	Avental de PVC	CA-44567	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
164	94c04a49-5473-4b96-8f33-88d44855ac2a	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-02-23	2026-03-23	\N	\N	\N	2026-03-16 00:08:35.000287
165	2f998a4c-3ee4-4c8a-8352-8b8853ccd0d7	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
166	74371e18-f5c2-41cd-b4ca-198a62a1fcf7	9e32646c-8bb3-431e-bde8-03f4dc05f9f6	Bota de Borracha	CA-66789	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
167	1c9ccbe6-975c-45de-b1eb-d50a6523a123	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	Luvas de Latex	CA-11234	1	NR-6	2026-02-23	2026-05-23	\N	\N	\N	2026-03-16 00:08:35.000287
168	e6cabddf-6180-4e71-9f8c-74c221a94548	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	Avental de PVC	CA-44567	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
169	3495b4f4-5917-4e63-873c-a28acf2d41a6	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-02-23	2026-03-23	\N	\N	\N	2026-03-16 00:08:35.000287
170	f4af838b-c3d8-4c06-a4ae-c3129c935bc8	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-02-23	2026-08-23	\N	\N	\N	2026-03-16 00:08:35.000287
171	f0403fc3-af05-4d92-aea5-ec48e14ec7ba	29c7e69f-8fb5-4fc7-a124-cfd06c799fe0	Bota de Borracha	CA-66789	1	NR-6	2026-02-23	2027-02-23	\N	\N	\N	2026-03-16 00:08:35.000287
172	1ef571a0-70a1-432a-a890-c7cb78bc453d	9e9e1678-9988-490c-b59b-b2786bb67e1c	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
173	5ebfe915-58db-4174-9153-207d3337570b	9e9e1678-9988-490c-b59b-b2786bb67e1c	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
174	2386e8be-90b6-4866-aa75-3b4959f568e2	9e9e1678-9988-490c-b59b-b2786bb67e1c	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
175	2fd9c4fd-61a7-495d-99fc-90be09fb7cb3	9e9e1678-9988-490c-b59b-b2786bb67e1c	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
176	3330f1bd-6552-43a5-8e35-403bb597d903	9e9e1678-9988-490c-b59b-b2786bb67e1c	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
177	74cb82f9-f5c6-415f-b96e-2b251d0a6569	0754e0aa-0be4-4253-9816-003c0149c1cd	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
178	a045e154-b1f8-41d8-9957-7d8f251df604	0754e0aa-0be4-4253-9816-003c0149c1cd	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
179	5f5eab68-7d55-4f08-96c7-3b25c8c9e9af	0754e0aa-0be4-4253-9816-003c0149c1cd	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
180	b8f46bac-cd27-4abb-a9c8-272d0b89055a	0754e0aa-0be4-4253-9816-003c0149c1cd	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
181	4616380d-68b3-4e1a-b213-6ff5e36f2c8d	0754e0aa-0be4-4253-9816-003c0149c1cd	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
182	0fced0dc-80cc-451a-9b60-11f093f18b52	783a8170-e951-4406-856e-6b0cc659d8c3	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
183	dec3f700-2864-4554-8480-a536e7e61b16	783a8170-e951-4406-856e-6b0cc659d8c3	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
184	b9481a79-fa42-4725-a2d5-78790057f9c7	783a8170-e951-4406-856e-6b0cc659d8c3	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
185	a0f29385-a4e3-48aa-b4fc-278957835c43	783a8170-e951-4406-856e-6b0cc659d8c3	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
186	84031e44-2c12-4d31-bf88-0444d1e3027c	783a8170-e951-4406-856e-6b0cc659d8c3	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
187	e3f9cf92-3d67-45de-940b-e7906b29b9cf	a7d18664-0f10-41b6-adf9-8e824794bc4a	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
188	460c3441-5ae2-4dc5-a746-6228a5277bc5	a7d18664-0f10-41b6-adf9-8e824794bc4a	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
189	2edec0ee-bfcb-4015-91ad-00b1f34e4454	a7d18664-0f10-41b6-adf9-8e824794bc4a	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
190	540762a5-f6bd-438e-af2c-4f05c974df85	a7d18664-0f10-41b6-adf9-8e824794bc4a	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
191	0b6c1262-e2a5-43b6-8099-e02a3a26b9fa	a7d18664-0f10-41b6-adf9-8e824794bc4a	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
192	36734490-a145-4b0d-aa90-503e8503edee	5bfbd45c-0a80-4be4-9776-e8651471f5dc	Luvas de Latex	CA-11234	1	NR-6	2026-01-15	2026-04-15	\N	\N	\N	2026-03-16 00:08:35.000287
193	2413478e-5886-4efc-9635-aadbf243905a	5bfbd45c-0a80-4be4-9776-e8651471f5dc	Avental de PVC	CA-44567	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
194	66920c59-d6fb-43f3-a81e-744e263bbc21	5bfbd45c-0a80-4be4-9776-e8651471f5dc	Mascara Descartavel PFF1	CA-33890	1	NR-6	2026-01-15	2026-02-15	\N	\N	\N	2026-03-16 00:08:35.000287
195	0bed2258-da94-40ba-9fcd-dfd4c78a56a1	5bfbd45c-0a80-4be4-9776-e8651471f5dc	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
196	c6554e61-a14a-47d4-a1f5-87ad6ee88957	5bfbd45c-0a80-4be4-9776-e8651471f5dc	Bota de Borracha	CA-66789	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
197	a1cde0df-0318-4581-b374-1819d116a7ee	ab54e4fc-627f-44cd-ae92-c43b459a90ec	Capacete de Seguranca	CA-98765	1	NR-6	2026-01-15	2029-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
198	1df87ad4-9a72-4548-9ce1-0b8ac92e265b	ab54e4fc-627f-44cd-ae92-c43b459a90ec	Oculos de Protecao	CA-87654	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
199	cf614e67-0071-4f2e-8c4c-69c3ab35ce7d	ab54e4fc-627f-44cd-ae92-c43b459a90ec	Luvas de Vaqueta	CA-76543	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
200	d51df2ae-2f06-4c7b-a6a2-931600244e46	ab54e4fc-627f-44cd-ae92-c43b459a90ec	Botina com Biqueira de Aco	CA-65432	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
201	6b5601b9-43bb-410d-920e-e097449b1d70	ab54e4fc-627f-44cd-ae92-c43b459a90ec	Cinto de Seguranca	CA-54321	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
202	d8fbde61-8638-47c6-92de-7f034ac34776	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	Capacete de Seguranca	CA-98765	1	NR-6	2026-01-15	2029-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
203	48f1d98d-efae-47c1-96cc-ecbc5bf6e52a	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	Oculos de Protecao	CA-87654	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
204	df0443e7-ec3a-4871-91b7-2b831cdec10e	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	Luvas de Vaqueta	CA-76543	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
205	59b2051e-6b4f-45b5-a612-1838edcdd92b	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	Botina com Biqueira de Aco	CA-65432	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
206	bcf7456e-4385-4bb5-a6cd-df2d7f2bbb76	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	Cinto de Seguranca	CA-54321	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
207	a8df460c-b048-4809-98cf-4a429d0d950e	12423164-f7d8-4db3-bf36-cffebda5948e	Capacete de Seguranca	CA-98765	1	NR-6	2026-01-15	2029-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
208	a3e0c03b-5b5e-4813-bf4b-0929513658f7	12423164-f7d8-4db3-bf36-cffebda5948e	Oculos de Protecao	CA-87654	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
209	14b0e5fb-19bd-43ce-b593-ebcf1ea4f354	12423164-f7d8-4db3-bf36-cffebda5948e	Luvas de Vaqueta	CA-76543	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
210	7c29399b-2f93-4773-8141-afa4f13f0074	12423164-f7d8-4db3-bf36-cffebda5948e	Botina com Biqueira de Aco	CA-65432	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
211	6e592e3f-61e9-4503-b996-cca9caebce90	12423164-f7d8-4db3-bf36-cffebda5948e	Cinto de Seguranca	CA-54321	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
212	c6516db2-83b0-41db-b9f7-e3ca1cff1737	4f6d1b27-d05b-4315-aa86-f245d70e52bb	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
213	a692d049-1b41-441b-8804-b102ecb801d5	4f6d1b27-d05b-4315-aa86-f245d70e52bb	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
214	a46e9bca-283a-4ffc-975b-0d6e0faa520d	4f6d1b27-d05b-4315-aa86-f245d70e52bb	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
215	8c794079-65a0-47e8-b534-f114c3487ba0	29dae28f-e688-4df0-8879-2704d8351d87	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
216	776221e2-4076-4666-9c06-26f02bf2d768	29dae28f-e688-4df0-8879-2704d8351d87	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
217	2c0d7f7e-72d5-4c61-8c47-5141f3619150	29dae28f-e688-4df0-8879-2704d8351d87	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
218	29f469ed-a6f8-4a53-9995-a74b6cb3b8b0	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	Colete Refletivo	CA-40123	1	NR-6	2026-01-15	2027-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
219	0f9d493c-05b9-4dec-8642-dc7ceb2dff61	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	Lanterna Tatica	CA-55789	1	NR-6	2026-01-15	2028-01-15	\N	\N	\N	2026-03-16 00:08:35.000287
220	ff439bbb-65d3-4e51-97dd-a8a7691a98dc	6bf7804a-4976-44d2-aa3e-5bf1f25c3530	Protetor Solar FPS 30	CA-22334	1	NR-6	2026-01-15	2026-07-15	\N	\N	\N	2026-03-16 00:08:35.000287
\.


--
-- Data for Name: sst_afastamentos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sst_afastamentos (id, employee_id, employee_nome, employee_cargo, tipo, motivo, data_inicio, data_fim_prevista, data_retorno, dias_previstos, atestado, cid, medico, crm, status, ajuda_medicamento_ativa, ajuda_medicamento_valor, gera_estabilidade, estabilidade_ate, observacoes, created_at, updated_at, encaminhado_inss, data_encaminhamento_inss, recibo_s2230, esocial_status) FROM stdin;
25fc57d2-3af2-4f3f-9fa1-ca5efce4dd76	a85f315b-4029-4eb1-9584-7a22ed3a7c78	RAILSON COELHO BATISTA	Agente de Servicos Gerais	doenca	Doenca com atestado medico — 2 dias	2026-02-20	2026-02-22	2026-02-22	2	t	J06	Dr. Carlos Mendes	CRM-AM 4521	encerrado	f	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-16 00:18:39.123943+00	f	\N	\N	nao_transmitida
6aa7a9c0-5220-49f5-936d-75bcd1ba2c93	b2f5ac0e-fb97-43ce-b7fe-78466284ea1b	FERNANDA VINHOTE MACIEL	Agente de Portaria	doenca	Doenca com atestado medico	2026-02-22	\N	\N	\N	t	M54	Dra. Ana Beatriz Costa	CRM-AM 3897	ativo	t	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-15 16:59:53.412998+00	f	\N	\N	nao_transmitida
1a112f87-cb23-47c4-b8a2-50bbc3f18342	b2b39603-19a1-4050-b062-98e500198012	GELSON BERNARDO LIMA	Agente de Portaria	doenca	Doenca com atestado medico — 6 dias	2026-02-22	2026-02-28	2026-02-28	6	t	J03	Dr. Carlos Mendes	CRM-AM 4521	encerrado	f	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-16 00:18:39.123943+00	f	\N	\N	nao_transmitida
dfb938af-0e8d-4503-9527-0f024fbd5136	7f10bafe-6a44-4c7b-ab37-f344a08caa2f	CARLOS ALBERTO ASSIS DE LIMA	Artifice	doenca	Doenca com atestado medico	2026-03-02	\N	\N	\N	t	M51	Dr. Roberto Silva	CRM-AM 5102	ativo	t	300.00	f	\N	\N	2026-03-15 16:59:53.412998+00	2026-03-15 16:59:53.412998+00	f	\N	\N	nao_transmitida
5227c094-e969-4de8-a2e5-b37fde4d6676	2430761d-172e-44b8-a817-edfea166e321		\N	doenca	Dengue — atestado medico 7 dias	2026-03-25	\N	\N	\N	t	A90	Dr. Carlos Mendes	CRM-AM 5432	ativo	t	300.00	f	\N	\N	2026-03-29 20:34:06.885731+00	2026-03-29 20:34:06.885731+00	f	\N	\N	nao_transmitida
00157b5c-a28e-4b1e-9db1-6d1b13202d0a	12423164-f7d8-4db3-bf36-cffebda5948e	KALEL SILVA DE JESUS	Artifice	doenca	Doenca com atestado medico — 60 dias	2026-03-04	2026-05-03	2026-05-03	60	t	S82	Dr. Roberto Silva	CRM-AM 5102	encerrado	t	300.00	f	\N	ATENCAO: Afastamento > 15 dias — encaminhar para INSS (B31/B91). Data prevista encaminhamento: 2026-03-19.	2026-03-15 16:59:53.412998+00	2026-05-30 15:47:57.431215+00	t	2026-03-19	\N	nao_transmitida
37838f4c-abd9-4c5b-9be0-9b3dd3fbc0ef	82a1d1d6-401d-487a-928f-42ed29756bca	ARYELTON BRAGA FIGUEIRA	AGENTE DE PORTARIA	suspensao_contratual	Suspensão contratual por ajuizamento de rescisão indireta (eSocial motivo 44). Recibo 1.1.0000000037643.	2026-02-02	\N	\N	\N	f	\N	\N	\N	ativo	f	\N	f	\N	\N	2026-07-02 16:45:33.470546+00	2026-07-02 16:45:33.470546+00	f	\N	\N	nao_transmitida
\.


--
-- Name: gp_asos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_asos_id_seq', 96, true);


--
-- Name: gp_cats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_cats_id_seq', 2, true);


--
-- Name: gp_epi_deliveries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gp_epi_deliveries_id_seq', 220, true);


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
-- Name: gp_epi_deliveries gp_epi_deliveries_delivery_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_epi_deliveries
    ADD CONSTRAINT gp_epi_deliveries_delivery_id_key UNIQUE (delivery_id);


--
-- Name: gp_epi_deliveries gp_epi_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_epi_deliveries
    ADD CONSTRAINT gp_epi_deliveries_pkey PRIMARY KEY (id);


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
-- Name: ix_gp_epi_employee; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_gp_epi_employee ON public.gp_epi_deliveries USING btree (employee_id);


--
-- Name: gp_asos fk_aso_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_asos
    ADD CONSTRAINT fk_aso_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: gp_epi_deliveries fk_ged_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gp_epi_deliveries
    ADD CONSTRAINT fk_ged_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: sst_afastamentos fk_sa_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sst_afastamentos
    ADD CONSTRAINT fk_sa_employee FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict k0DOCwmLaNKSAO1FQOId41g5abnfmT7XbMtPa2NWKiHVWYCc3t6TFfbZxGC3rtd

