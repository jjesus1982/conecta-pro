-- REVERSÃO (⚠️ tabelas novas: seguro só enquanto vazias; colunas: perde o seed de líderes)
BEGIN;
DROP TABLE IF EXISTS operacional_avaliacoes_equipe;
DROP TABLE IF EXISTS operacional_passagens_turno;
ALTER TABLE posts DROP COLUMN IF EXISTS leader_id;
ALTER TABLE diaria_diaristas DROP COLUMN IF EXISTS telefone;
ALTER TABLE diaria_diaristas DROP COLUMN IF EXISTS email;
COMMIT;
