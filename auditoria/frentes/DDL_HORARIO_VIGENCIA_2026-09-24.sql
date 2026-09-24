-- Horário previsto COM VIGÊNCIA — item 2 da especificação do José Luís (Jordan, 24/09/2026).
--
-- 🔴 O PROBLEMA MEDIDO, com nome e sobrenome. A Celiane bateu 09:00 e o relatório a acusou de
-- 60 min de atraso, porque `shifts.planned_start_time` diz 08:00. O Jordan corrigiu: 09:00–18:00
-- com 1h de intervalo é o horário CERTO dela. Ou seja, não houve atraso — o cadastro está velho,
-- e "do jeito que está ela aparece atrasada pra mim todo dia".
--
-- ⚠️ Por que uma tabela nova em vez de consertar `shifts`: `shifts` guarda UM horário por turno,
-- sem histórico. Corrigir o turno de hoje deixa os de ontem errados, e o de amanhã nasce errado
-- de novo. Horário de pessoa é um FATO COM DATA — muda, e o que passou continua valendo para o
-- que já aconteceu. Sem vigência, todo relatório retroativo mente.
--
-- ⚠️ E esta tabela NÃO substitui o cadastro operacional. Ela é a camada de LEITURA do agente:
-- quando há vigência, ela manda; quando não há, cai no `planned_start_time` do turno. O Jordan
-- segue curando o operacional à mão, e isso não muda.
CREATE TABLE IF NOT EXISTS ponto_horario_vigencia (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id      uuid NOT NULL,
    entrada          time NOT NULL,
    saida            time NOT NULL,
    intervalo_min    integer NOT NULL DEFAULT 0,
    -- Vigência: `fim` nulo = vigente até hoje. Um registro novo FECHA o anterior.
    vigencia_inicio  date NOT NULL,
    vigencia_fim     date,
    motivo           text,
    registrado_por   text,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    -- Duas vigências abertas para a mesma pessoa seriam ambiguidade silenciosa: qual vale?
    CONSTRAINT ck_vigencia CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_horario_vigente_aberta
    ON ponto_horario_vigencia (employee_id) WHERE vigencia_fim IS NULL;
CREATE INDEX IF NOT EXISTS ix_horario_periodo
    ON ponto_horario_vigencia (employee_id, vigencia_inicio, vigencia_fim);
