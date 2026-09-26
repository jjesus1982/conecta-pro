-- Vigia de postos em tempo real — 26/09/2026
--
-- POR QUE: o Jordan, às 07:07 de um sábado, teve que MARCAR o José Luís para saber quem tinha
-- batido. Palavras dele: "às 07h eu não consigo disparar sozinho aqui. Me marca às 07:05 que eu
-- puxo" — o agente é reativo, e o relatório de cobertura só sai às 08:30, DEPOIS do problema.
-- "precisa saber assim que houver um problema pra eu resolver, e não depois de ele ter acontecido".
--
-- Esta tabela é a MEMÓRIA do vigia: sem ela, um aviso a cada 5 minutos sobre a mesma pessoa
-- vira ruído, e ruído treina o dono a ignorar o grupo — que é o mesmo defeito do sino de
-- "conversas frias" que eu consertei ontem, com a Patrícia ocupando 15 vagas.
CREATE TABLE IF NOT EXISTS wa_vigia_avisos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dia         date NOT NULL,
    employee_id uuid,
    posto       varchar(200),
    hora_turno  time,
    veredito    varchar(40) NOT NULL,
    avisado_em  timestamptz NOT NULL DEFAULT now(),
    -- idempotência pela chave natural: mesma pessoa + mesmo dia + mesmo turno + mesmo veredito
    -- avisa UMA vez. Mudou de ATRASO para COBERTO? é outro veredito, e a boa notícia sai.
    CONSTRAINT uq_vigia UNIQUE (dia, employee_id, hora_turno, veredito)
);
CREATE INDEX IF NOT EXISTS ix_vigia_dia ON wa_vigia_avisos (dia);
