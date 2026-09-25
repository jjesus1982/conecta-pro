-- DDL da ponte Hermes <-> José Luís — 25/09/2026
-- NÃO EXECUTADO. Nada aqui é necessário para a frente funcionar.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- POR QUE NÃO HÁ TABELA NOVA
-- ─────────────────────────────────────────────────────────────────────────────
-- Os casos do José Luís (pergunta -> resposta -> desfecho) moram em
-- `cwi_message_log` com `direction='cas'` e `status=<desfecho>`. Esta casa já usa
-- esse molde DE PROPÓSITO para estado de agente: `mem` (memória do contato),
-- `drf` (rascunho), `gld` (conversa nota >= 8), `trf` (transferido ao humano) —
-- o comentário original em agent_service.py diz "zero migration; sempre INSERT
-- -> histórico auditável".
--
-- Tabela nova deixaria o aprendizado DESLIGADO esperando um `alembic upgrade
-- heads` manual, e capacidade que nasce desligada é a dívida que mais custou
-- aqui. Reusar o molde faz o aprendizado começar no instante em que alguém
-- puser JOSE_LUIS_VIA_HERMES=aprender — sem DDL, sem bake, sem migration.
--
-- Conferido antes de reusar (a lição de que valor novo em coluna de status muda
-- todo filtro literal — feedback_status_compartilhado_tem_consumidor):
--   · não existe um único `direction !=` / `direction NOT IN` em SQL no backend
--     (oráculo mediu: 11 filtros, todos lista BRANCA, 0 por negação);
--   · o caminho do prompt filtra `direction IN ('in','out')`;
--   · a detecção de eco compara `direcao != "in"` em Python e pula;
--   · `direction` é varchar(3) e 'cas' tem 3 caracteres — cabe EXATAMENTE;
--   · `status` é varchar(20) e o desfecho mais longo é 'humano_assumiu' (14).
-- As duas últimas linhas são asseridas pelo oráculo
-- `backend/scripts/orq/test_oraculo_hermes_jose_luis.py`, porque coluna curta
-- mataria TODA gravação em silêncio.


-- ─────────────────────────────────────────────────────────────────────────────
-- (1) OPCIONAL — índice parcial para a leitura das lições
-- ─────────────────────────────────────────────────────────────────────────────
-- A leitura por turno é: os 60 casos `resolveu` mais recentes, excluindo a
-- conversa atual. Hoje isso vai por `ix_cwi_conversation` + filtro; com poucos
-- milhares de linhas é irrelevante. Rodar SÓ se a leitura aparecer no
-- pg_stat_statements do José Luís.
--
-- CONCURRENTLY: a tabela é escrita pelo webhook do WhatsApp em horário
-- comercial, e um índice comum tomaria lock de escrita na conversa de gente
-- real. NÃO roda dentro de transação (nem dentro de migration alembic comum).

-- CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cwi_casos_resolvidos
--     ON cwi_message_log (created_at DESC)
--     WHERE direction = 'cas' AND status = 'resolveu';


-- ─────────────────────────────────────────────────────────────────────────────
-- (2) LEITURA — o que perguntar ao banco para saber se a frente está aprendendo
-- ─────────────────────────────────────────────────────────────────────────────
-- Nenhuma destas escreve. A primeira é a que responde "isto está vivo ou é
-- casca?": sem linhas `cas`, o interruptor nunca saiu de `off`.

-- -- quantos casos, e em que desfecho (a medida honesta da frente)
-- SELECT status AS desfecho, count(*), min(created_at)::date AS desde
--   FROM cwi_message_log WHERE direction = 'cas'
--  GROUP BY 1 ORDER BY 2 DESC;

-- -- o que já está servindo de lição (só `resolveu` alimenta few-shot)
-- SELECT created_at, content::json->>'p' AS pergunta, content::json->>'r' AS resposta
--   FROM cwi_message_log WHERE direction = 'cas' AND status = 'resolveu'
--  ORDER BY created_at DESC LIMIT 20;

-- -- quantos turnos o Hermes SOCORREU (via='hermes-socorro' no JSON do caso)
-- SELECT count(*) FROM cwi_message_log
--  WHERE direction = 'cas' AND content LIKE '%hermes-socorro%';

-- -- fila de casos ainda sem veredito: alta e crescente = pessoas parando de
-- -- responder depois da resposta do agente, que é sinal ruim por si só
-- SELECT count(*) FROM cwi_message_log
--  WHERE direction = 'cas' AND status = 'indefinido'
--    AND created_at < now() - interval '2 days';


-- ─────────────────────────────────────────────────────────────────────────────
-- (3) O QUE NÃO É DDL E É A PENDÊNCIA MAIS BARATA DESTA FRENTE
-- ─────────────────────────────────────────────────────────────────────────────
-- O Hermes JÁ aprendeu duas coisas e elas estão presas. `memory.write_approval`
-- e `skills.write_approval` = true no config dele (decisão certa: agente que
-- reescreve a própria premissa vira regra sozinho) jogam toda escrita numa fila
-- que ninguém lê:
--
--     docker exec conecta-pro-hermes ls -la /data/pending/skills/
--       0fac2562.json   14/09/2026
--       19804712.json   23/09/2026  -> 3 patches na skill `triagem-de-ponto`,
--                                      registrando que a importação do
--                                      Tangerino foi desligada em 13/09 e
--                                      deixou de ser causa possível de
--                                      "não bateu". Lição boa, de dado real.
--
-- Aprovar essas duas é a única coisa nesta frente que faz o Hermes ficar mais
-- inteligente HOJE, e não custa linha de código nenhuma. Enquanto a fila não
-- tiver consumidor, ele aprende e esquece — o padrão de dívida desta casa:
-- não falta código, falta consumidor.
