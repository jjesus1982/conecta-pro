-- FORWARD 2 — vinculo users->employees + comentarios de ocorrencia (2026-07-07)
-- users.employee_id: elo canonico user->employee (emails de employees sao pessoais, nao servem de bridge)
ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES employees(id);
UPDATE users SET employee_id='29dae28f-e688-4df0-8879-2704d8351d87' WHERE email='awsilva@conectamais.pro' AND employee_id IS NULL;
UPDATE users SET employee_id='6bf7804a-4976-44d2-aa3e-5bf1f25c3530' WHERE email='epereira@conectamais.pro' AND employee_id IS NULL;
UPDATE users SET employee_id='ebfc72fe-7081-47b8-bce6-88b81cdcb09a' WHERE email='emarques@conectamais.pro' AND employee_id IS NULL;

-- occurrence_comments (model existia sem tabela; DDL espelha o model)
CREATE TABLE IF NOT EXISTS occurrence_comments (
  id UUID PRIMARY KEY,
  occurrence_id UUID NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
  author_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
  author_name VARCHAR(200),
  content TEXT NOT NULL,
  is_internal BOOLEAN NOT NULL DEFAULT false,
  edited_at TIMESTAMP,
  original_content TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  is_active BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_occurrence_comments_occurrence_id ON occurrence_comments (occurrence_id);
CREATE INDEX IF NOT EXISTS ix_occurrence_comments_author_id ON occurrence_comments (author_id);

-- Adendo: ocorrencia sem funcionario especifico e valida (manutencao/incidente de posto)
ALTER TABLE occurrences ALTER COLUMN employee_id DROP NOT NULL;
