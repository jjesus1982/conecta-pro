-- ============================================================================
-- Conecta PRO — Folha em lote via Efí (PIX cash-out)
-- Schema PostgreSQL
--
-- Princípios:
--  * Dinheiro sempre em CENTAVOS (BIGINT). Nunca float.
--  * idEnvio é DETERMINÍSTICO por (lote, favorecido) => trava dupla-pagamento.
--  * Máquina de estados explícita. Nenhum item é re-enviado fora dos estados
--    retryáveis. Folha paga duas vezes não volta fácil — a idempotência aqui
--    é requisito de negócio, não firula técnica.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS folha_efi;
SET search_path TO folha_efi;

-- Favorecido = funcionário/beneficiário. A chave PIX é validada UMA VEZ no
-- cadastro (ver nota sobre DICT no DESIGN.md) e o nome/documento esperado
-- fica congelado aqui para conferência antes de cada pagamento.
CREATE TABLE favorecido (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    funcionario_id    BIGINT NOT NULL,               -- FK p/ seu cadastro de RH
    nome              TEXT   NOT NULL,
    documento         VARCHAR(14) NOT NULL,          -- CPF/CNPJ só dígitos
    chave_pix         TEXT   NOT NULL,
    chave_validada_em TIMESTAMPTZ,                    -- quando conferimos a chave
    chave_nome_bacen  TEXT,                           -- nome retornado na validação
    ativo             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (funcionario_id, chave_pix)
);

-- Lote de folha. total_esperado_centavos é o guard: a soma dos itens tem que
-- bater com esse valor ANTES de qualquer disparo.
CREATE TABLE lote_pagamento (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    referencia            TEXT NOT NULL,              -- ex.: "FOLHA-2026-08"
    competencia           DATE NOT NULL,
    empresa_cnpj          VARCHAR(14) NOT NULL,       -- garante mesmo CNPJ (Patrimonial)
    chave_pix_origem      TEXT NOT NULL,              -- chave da conta Efí pagadora
    total_esperado_centavos BIGINT NOT NULL CHECK (total_esperado_centavos > 0),
    status                TEXT NOT NULL DEFAULT 'RASCUNHO'
        CHECK (status IN ('RASCUNHO','AUTORIZADO','EM_EXECUCAO','CONCLUIDO','CONCLUIDO_COM_FALHAS','CANCELADO')),
    autorizado_por        TEXT,                       -- usuário que passou o OTP interno
    autorizado_em         TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (empresa_cnpj, referencia)
);

-- Um pagamento por favorecido dentro do lote.
-- id_envio: idempotency key enviada à Efí no PATH (PUT /v3/gn/pix/:idEnvio).
--   Determinístico => reprocessar o mesmo item reusa o id_envio e a Efí NÃO
--   duplica. É a trava central contra pagar de novo.
CREATE TABLE pagamento (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id           BIGINT NOT NULL REFERENCES lote_pagamento(id),
    favorecido_id     BIGINT NOT NULL REFERENCES favorecido(id),
    id_envio          VARCHAR(35) NOT NULL,           -- [A-Za-z0-9], <=35 (confirmar limite)
    valor_centavos    BIGINT NOT NULL CHECK (valor_centavos > 0),
    chave_pix_destino TEXT NOT NULL,                  -- snapshot no momento do lote
    info_pagador      TEXT,                           -- aparece no extrato do favorecido

    -- Máquina de estados:
    --  PENDENTE      -> ainda não disparado
    --  ENVIANDO      -> requisição em voo (lock otimista)
    --  PROCESSANDO   -> Efí aceitou (EM_PROCESSAMENTO), aguardando webhook
    --  LIQUIDADO     -> REALIZADO (dinheiro saiu) [terminal]
    --  FALHOU        -> NAO_REALIZADO / rejeição [terminal, mas re-emitível c/ novo lote]
    --  ERRO_ENVIO    -> falha de rede/5xx antes de confirmar [RETRYÁVEL c/ mesmo id_envio]
    status            TEXT NOT NULL DEFAULT 'PENDENTE'
        CHECK (status IN ('PENDENTE','ENVIANDO','PROCESSANDO','LIQUIDADO','FALHOU','ERRO_ENVIO')),

    e2e_id            TEXT,                            -- devolvido pela Efí; casa com extrato
    tentativas        INT NOT NULL DEFAULT 0,
    ultimo_erro       TEXT,
    enviado_em        TIMESTAMPTZ,
    liquidado_em      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- trava de dupla-pagamento no nível do banco:
    UNIQUE (lote_id, favorecido_id),
    UNIQUE (id_envio)
);

CREATE INDEX idx_pagamento_status ON pagamento(status)
    WHERE status IN ('PENDENTE','ENVIANDO','PROCESSANDO','ERRO_ENVIO');
CREATE INDEX idx_pagamento_e2e ON pagamento(e2e_id);

-- Webhook: processamento idempotente. Guardamos o corpo cru e um hash para
-- descartar reentregas (a Efí re-tenta). Nunca reprocessa o mesmo evento.
CREATE TABLE webhook_event (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dedup_key     TEXT NOT NULL UNIQUE,               -- ex.: e2e_id + status
    e2e_id        TEXT,
    id_envio      VARCHAR(35),
    payload       JSONB NOT NULL,
    processado_em TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trilha de auditoria de toda transição de estado (compliance / RH).
CREATE TABLE pagamento_evento (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pagamento_id  BIGINT NOT NULL REFERENCES pagamento(id),
    de_status     TEXT,
    para_status   TEXT NOT NULL,
    origem        TEXT NOT NULL,                       -- 'api','webhook','reconciliacao'
    detalhe       JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
