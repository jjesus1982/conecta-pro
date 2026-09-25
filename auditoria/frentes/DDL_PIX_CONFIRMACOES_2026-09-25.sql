-- Coleta de confirmação de chave PIX pelo José Luís — 25/09/2026
--
-- POR QUE EXISTE: chave CPF liquida em banco DORMENTE. Provado no histórico do José Luís,
-- 18/09: "o pix foi direcionado pra conta do next, que a anos também não usava". O e2e existe,
-- o dinheiro liquidou, a pessoa nunca viu. Logo "liquidou" NÃO prova que chegou, e 32 pessoas
-- ativas só têm chave CPF.
--
-- ⚠️ A RESPOSTA NUNCA É APLICADA AUTOMATICAMENTE. Chave PIX é destino de dinheiro: aplicar o
-- que chega por WhatsApp deixaria qualquer um que acesse um telefone redirecionar salário.
-- Esta tabela GUARDA a resposta; quem aplica é humano com papel de financeiro.
CREATE TABLE IF NOT EXISTS pix_confirmacoes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     uuid NOT NULL UNIQUE,      -- UNIQUE = idempotência: não pergunta 2x
    nome            varchar(200) NOT NULL,
    telefone        varchar(30),
    chave_atual     varchar(200),              -- o que estava cadastrado quando perguntei
    tipo_atual      varchar(20),
    pedido_em       timestamptz,
    respondido_em   timestamptz,
    texto_resposta  text,                      -- o que a pessoa escreveu, cru
    chave_informada varchar(200),              -- o que eu extraí do texto (pode ser NULL)
    tipo_informado  varchar(20),
    status          varchar(20) NOT NULL DEFAULT 'aguardando',
                    -- aguardando · respondido · confirmou_atual · nao_avisado · aplicado · rejeitado
    aplicado_em     timestamptz,
    aplicado_por    varchar(100),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pix_conf_status ON pix_confirmacoes (status);
CREATE INDEX IF NOT EXISTS ix_pix_conf_tel ON pix_confirmacoes (telefone);
