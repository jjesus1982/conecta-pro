"""Fase -1 (Task 4): baseline Alembic das tabelas criadas por DDL em runtime.

Pre-mortem F1: *_consultas (8), consultor_memorias, gedeon_intercorrencias,
juridico_conhecimento, juridico_playbook nasciam de CREATE TABLE IF NOT EXISTS no
1o request (sem versao -> drift entre ambientes). Esta migration versiona o schema.

GUARDA POR EXISTENCIA: em producao as tabelas ja existem -> no-op total. Em ambiente
limpo (staging/DR) roda o dump completo (extraido de pg_dump -s da prod 2026-07-21).

Revision ID: fase_menos1_consultas_baseline
Revises: fase_menos1_empresa_id
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "fase_menos1_consultas_baseline"
down_revision = "fase_menos1_empresa_id"
branch_labels = None
depends_on = None

_TBLS = ['ceo_consultas', 'financial_cfo_consultas', 'juridico_consultas', 'gedeon_consultas', 'comercial_consultas', 'operacional_consultas', 'rh_consultas', 'fiscal_consultas', 'consultor_memorias', 'gedeon_intercorrencias', 'juridico_conhecimento', 'juridico_playbook']

_STMTS = [
        r'''CREATE TABLE public.ceo_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.ceo_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.ceo_consultas_id_seq OWNED BY public.ceo_consultas.id''',
        r'''CREATE TABLE public.comercial_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.comercial_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.comercial_consultas_id_seq OWNED BY public.comercial_consultas.id''',
        r'''CREATE TABLE public.consultor_memorias (
    id bigint NOT NULL,
    origem character varying(20) NOT NULL,
    conteudo text NOT NULL,
    fonte text,
    ativo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.consultor_memorias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.consultor_memorias_id_seq OWNED BY public.consultor_memorias.id''',
        r'''CREATE TABLE public.financial_cfo_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.financial_cfo_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.financial_cfo_consultas_id_seq OWNED BY public.financial_cfo_consultas.id''',
        r'''CREATE TABLE public.fiscal_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    competencia character varying(7),
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.fiscal_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.fiscal_consultas_id_seq OWNED BY public.fiscal_consultas.id''',
        r'''CREATE TABLE public.gedeon_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    condominio character varying(200),
    competencia character varying(7),
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.gedeon_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.gedeon_consultas_id_seq OWNED BY public.gedeon_consultas.id''',
        r'''CREATE TABLE public.gedeon_intercorrencias (
    id bigint NOT NULL,
    condominio character varying(200) NOT NULL,
    competencia character varying(7) NOT NULL,
    tipo character varying(30) NOT NULL,
    funcionario character varying(200),
    data_evento date,
    descricao text NOT NULL,
    impacto_folha boolean DEFAULT true NOT NULL,
    status character varying(15) DEFAULT 'aberta'::character varying NOT NULL,
    tratada_em timestamp with time zone,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.gedeon_intercorrencias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.gedeon_intercorrencias_id_seq OWNED BY public.gedeon_intercorrencias.id''',
        r'''CREATE TABLE public.juridico_conhecimento (
    id integer NOT NULL,
    tipo character varying(20) DEFAULT 'precedente'::character varying NOT NULL,
    area character varying(20) NOT NULL,
    titulo text NOT NULL,
    palavras_chave text,
    resumo text,
    fundamentacao text,
    desfecho text,
    fonte text,
    ativo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.juridico_conhecimento_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.juridico_conhecimento_id_seq OWNED BY public.juridico_conhecimento.id''',
        r'''CREATE TABLE public.juridico_consultas (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    area character varying(20) NOT NULL,
    pergunta text NOT NULL,
    resposta text,
    fontes jsonb DEFAULT '[]'::jsonb,
    escalonar boolean DEFAULT false,
    disclaimer text,
    contexto_usado jsonb DEFAULT '{}'::jsonb,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now()
)''',
        r'''CREATE TABLE public.juridico_playbook (
    id integer NOT NULL,
    situacao text NOT NULL,
    area character varying(20) NOT NULL,
    gatilho text,
    passos jsonb,
    base_legal text,
    documentos jsonb,
    ativo boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.juridico_playbook_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.juridico_playbook_id_seq OWNED BY public.juridico_playbook.id''',
        r'''CREATE TABLE public.operacional_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    posto character varying(200),
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.operacional_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.operacional_consultas_id_seq OWNED BY public.operacional_consultas.id''',
        r'''CREATE TABLE public.rh_consultas (
    id bigint NOT NULL,
    area character varying(20) NOT NULL,
    competencia character varying(7),
    pergunta text NOT NULL,
    resposta text NOT NULL,
    escalonar boolean DEFAULT false NOT NULL,
    disclaimer text NOT NULL,
    contexto_usado jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)''',
        r'''CREATE SEQUENCE public.rh_consultas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1''',
        r'''ALTER SEQUENCE public.rh_consultas_id_seq OWNED BY public.rh_consultas.id''',
        r'''ALTER TABLE ONLY public.ceo_consultas ALTER COLUMN id SET DEFAULT nextval('public.ceo_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.comercial_consultas ALTER COLUMN id SET DEFAULT nextval('public.comercial_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.consultor_memorias ALTER COLUMN id SET DEFAULT nextval('public.consultor_memorias_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.financial_cfo_consultas ALTER COLUMN id SET DEFAULT nextval('public.financial_cfo_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.fiscal_consultas ALTER COLUMN id SET DEFAULT nextval('public.fiscal_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.gedeon_consultas ALTER COLUMN id SET DEFAULT nextval('public.gedeon_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.gedeon_intercorrencias ALTER COLUMN id SET DEFAULT nextval('public.gedeon_intercorrencias_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.juridico_conhecimento ALTER COLUMN id SET DEFAULT nextval('public.juridico_conhecimento_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.juridico_playbook ALTER COLUMN id SET DEFAULT nextval('public.juridico_playbook_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.operacional_consultas ALTER COLUMN id SET DEFAULT nextval('public.operacional_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.rh_consultas ALTER COLUMN id SET DEFAULT nextval('public.rh_consultas_id_seq'::regclass)''',
        r'''ALTER TABLE ONLY public.ceo_consultas
    ADD CONSTRAINT ceo_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.comercial_consultas
    ADD CONSTRAINT comercial_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.consultor_memorias
    ADD CONSTRAINT consultor_memorias_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.financial_cfo_consultas
    ADD CONSTRAINT financial_cfo_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.fiscal_consultas
    ADD CONSTRAINT fiscal_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.gedeon_consultas
    ADD CONSTRAINT gedeon_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.gedeon_intercorrencias
    ADD CONSTRAINT gedeon_intercorrencias_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.juridico_conhecimento
    ADD CONSTRAINT juridico_conhecimento_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.juridico_consultas
    ADD CONSTRAINT juridico_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.juridico_playbook
    ADD CONSTRAINT juridico_playbook_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.operacional_consultas
    ADD CONSTRAINT operacional_consultas_pkey PRIMARY KEY (id)''',
        r'''ALTER TABLE ONLY public.rh_consultas
    ADD CONSTRAINT rh_consultas_pkey PRIMARY KEY (id)''',
        r'''CREATE INDEX ix_consultor_memorias_origem ON public.consultor_memorias USING btree (origem, ativo)''',
        r'''CREATE INDEX ix_gedeon_interc_cond_comp ON public.gedeon_intercorrencias USING btree (condominio, competencia)'''
    ]


def upgrade():
    conn = op.get_bind()
    # Producao: tabelas ja existem (runtime DDL) -> nada a fazer.
    if conn.execute(sa.text("SELECT to_regclass('public.consultor_memorias')")).scalar():
        return
    for stmt in _STMTS:
        op.execute(stmt)


def downgrade():
    for t in _TBLS:
        op.execute("DROP TABLE IF EXISTS %s CASCADE;" % t)
