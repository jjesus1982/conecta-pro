-- Fila de mensagem agendada do José Luís — 25/09/2026
--
-- POR QUE: o Jordan pediu "manda o José Luís falar com o Malaquias às 08:00 deste sábado" e não
-- existia mecanismo nenhum. A alternativa era um beat semanal (que mandaria TODO sábado) ou
-- depender da minha sessão estar viva no horário — as duas erradas.
--
-- ⭐ Fila SEMPRE com consumidor: o beat que a drena nasce junto, nesta mesma frente. Fila sem
-- consumidor é a dívida que esta casa mais paga (a de `ged`, a de skills do Hermes, o espelho).
CREATE TABLE IF NOT EXISTS wa_mensagens_agendadas (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telefone      varchar(30) NOT NULL,
    nome          varchar(200),
    texto         text NOT NULL,
    quando        timestamptz NOT NULL,        -- quando deve sair (UTC)
    motivo        varchar(200),                -- por que existe, para quem ler depois
    criado_por    varchar(100),
    status        varchar(20) NOT NULL DEFAULT 'agendada',
                  -- agendada · enviada · falhou · cancelada
    enviada_em    timestamptz,
    erro          text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_wa_agendada_pendente ON wa_mensagens_agendadas (quando)
  WHERE status = 'agendada';
