-- Grupos do José Luís — observação, absorção e apoio ao Orlailson (23/09/2026)
-- ADITIVO e IDEMPOTENTE. Só CREATE TABLE / ADD COLUMN / CREATE INDEX.
-- ⚠️ Dívida de alembic declarada: nasce por SQL direto porque alembic/versions é zona
-- proibida para sessão autônoma. Vira migration pela mão do Jordan.
BEGIN;

-- ══════════════ Configuração POR GRUPO ══════════════
-- ⭐ O modo é DADO, não julgamento do modelo. O José Luís escreveu a frase certa na conversa
-- de 23/09: "silêncio tem que ser regra técnica, não minha boa vontade". Uma linha aqui com
-- modo='observar' impede o enfileiramento do agente ANTES de ele existir no turno — não há
-- prompt que possa desobedecer, porque o prompt nem roda.
CREATE TABLE IF NOT EXISTS wa_grupos (
    jid            varchar(80) PRIMARY KEY,      -- 120363285473431324@g.us
    nome           varchar(160),
    modo           varchar(20)  NOT NULL DEFAULT 'off',   -- observar | falar | off
    foco           text,                                   -- o que aprender/vigiar neste grupo
    -- ⚠️ mídia DESLIGADA por padrão: grupo tem terceiro falando, e processar áudio/foto de
    -- quem não sabe que há um assistente lendo é decisão do dono, não default de código.
    midia_ok       boolean      NOT NULL DEFAULT false,
    observar_desde timestamp    NOT NULL DEFAULT now(),
    -- teto de fala por dia, para o agente não virar spam de grupo (ele mesmo previu o risco)
    max_falas_dia  smallint     NOT NULL DEFAULT 1,
    retencao_dias  smallint     NOT NULL DEFAULT 90,
    criado_em      timestamp    NOT NULL DEFAULT now(),
    atualizado_em  timestamp    NOT NULL DEFAULT now()
);

-- ══════════════ O que foi absorvido ══════════════
-- Tabela PRÓPRIA e não leitura do Postgres do Chatwoot: aqui mora a CLASSIFICAÇÃO (tom ×
-- dado comercial), a retenção por grupo e o autor resolvido contra `employees`. Ler o banco
-- do Chatwoot daria a mensagem crua e nada disso.
CREATE TABLE IF NOT EXISTS wa_grupo_mensagens (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_jid            varchar(80) NOT NULL REFERENCES wa_grupos(jid) ON DELETE CASCADE,
    chatwoot_message_id  bigint,
    autor_fone           varchar(30),
    autor_nome           varchar(160),
    -- quem é de dentro: resolvido por `identidade.quem_e`, não pelo nome que o WhatsApp manda
    autor_employee_id    uuid,
    autor_tipo           varchar(20),               -- funcionario | dono | cliente | lead | desconhecido
    conteudo             text,
    -- ⭐ o corte que o item 3 pede: o que é TOM e o que é DADO. Default 'tom' porque a maioria
    -- é conversa; virar dado é decisão explícita de um classificador, nunca o padrão.
    classificacao        varchar(24) NOT NULL DEFAULT 'tom',  -- tom | operacional | comercial | financeiro | pendencia
    relevante            boolean     NOT NULL DEFAULT false,
    quando               timestamp   NOT NULL DEFAULT now(),
    criado_em            timestamp   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_wa_grupo_msg_grupo_quando ON wa_grupo_mensagens (grupo_jid, quando DESC);
CREATE INDEX IF NOT EXISTS ix_wa_grupo_msg_relevante    ON wa_grupo_mensagens (relevante, quando DESC) WHERE relevante;
-- ⚠️ mesma mensagem reentregue pela fila não pode virar duas linhas: a fila é durável e
-- reentrega de propósito quando o worker morre no meio.
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_grupo_msg_chatwoot ON wa_grupo_mensagens (chatwoot_message_id)
    WHERE chatwoot_message_id IS NOT NULL;

-- ══════════════ Quando o agente FALOU num grupo ══════════════
-- Existe para o teto de `max_falas_dia` ser medido por FATO, não por contador em memória que
-- zera a cada deploy.
CREATE TABLE IF NOT EXISTS wa_grupo_falas (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_jid  varchar(80) NOT NULL,
    motivo     varchar(40),               -- dado_faltando | pergunta_sem_resposta | decisao_sem_dono
    texto      text,
    quando     timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_wa_grupo_falas_dia ON wa_grupo_falas (grupo_jid, quando DESC);

COMMIT;
