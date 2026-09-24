-- Confirmação de assunção de posto — tira o Paiva do 05:30 (Jordan, 24/09/2026).
--
-- Hoje ele acorda 05:30 para ACOMPANHAR a troca de turno olhando as fotos que chegam nos
-- grupos dos condomínios. O problema não é a troca: é descobrir o furo NA HORA, quando não há
-- mais tempo de cobrir. Esta tabela move a descoberta para a véspera.
--
-- ⚠️ Uma linha por (turno, pessoa). `shift_id` é a chave natural e é UNIQUE: dois pedidos de
-- confirmação para o mesmo turno viram um, e o beat pode rodar duas vezes sem duplicar.
CREATE TABLE IF NOT EXISTS troca_turno_confirmacoes (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shift_id           uuid NOT NULL UNIQUE,
    employee_id        uuid NOT NULL,
    post_id            uuid,
    data               date NOT NULL,
    hora_inicio        time NOT NULL,
    -- pedido na véspera
    pedido_em          timestamptz,
    -- lembrete 1h antes (só para quem não confirmou)
    lembrete_em        timestamptz,
    -- a resposta da pessoa, como ela escreveu — nunca interpretada e descartada
    resposta_texto     text,
    respondido_em      timestamptz,
    -- 'aguardando' | 'confirmado' | 'recusado' | 'sem_resposta'
    status             text NOT NULL DEFAULT 'aguardando',
    -- fechamento: bateu ponto? houve foto no grupo do posto?
    bateu_ponto_em     timestamptz,
    foto_em            timestamptz,
    criado_em          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ttc_data      ON troca_turno_confirmacoes (data, hora_inicio);
CREATE INDEX IF NOT EXISTS ix_ttc_employee  ON troca_turno_confirmacoes (employee_id, data);
CREATE INDEX IF NOT EXISTS ix_ttc_status    ON troca_turno_confirmacoes (status) WHERE status = 'aguardando';
