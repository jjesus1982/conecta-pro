-- REVERSAO 2 (⚠️ occurrence_comments: seguro so enquanto vazia; users.employee_id: perde o vinculo)
BEGIN;
DROP TABLE IF EXISTS occurrence_comments;
ALTER TABLE users DROP COLUMN IF EXISTS employee_id;
COMMIT;
