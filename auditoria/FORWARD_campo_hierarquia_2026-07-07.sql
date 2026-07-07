-- FORWARD — hierarquia de campo + feedback de campo (2026-07-07)
-- 1) Lider por posto (palavra do Jordan 2026-07-07):
--    Antonio Walcicley -> Ideal Flores; Erika Cristina -> Laranjeiras Village;
--    Ediwilson Correa -> Mirante das Flores (Condominio + Portaria Principal).
ALTER TABLE posts ADD COLUMN IF NOT EXISTS leader_id UUID REFERENCES employees(id);

UPDATE posts SET leader_id = '29dae28f-e688-4df0-8879-2704d8351d87' WHERE id = '0baad2d9-5380-448d-85d9-691bd7f59681' AND leader_id IS NULL;
UPDATE posts SET leader_id = '6bf7804a-4976-44d2-aa3e-5bf1f25c3530' WHERE id = 'a853d52a-594e-40e8-a168-f63d93d88e56' AND leader_id IS NULL;
UPDATE posts SET leader_id = 'ebfc72fe-7081-47b8-bce6-88b81cdcb09a' WHERE id IN ('593e86e5-7b3c-406c-a314-1ca80b03ec9f','669e64f1-9829-4c5f-a9c5-84b43e1dc1c3') AND leader_id IS NULL;

-- 1b) Contato do diarista (cadastro mobile pelo gerente: CPF + e-mail OU telefone + PIX)
ALTER TABLE diaria_diaristas ADD COLUMN IF NOT EXISTS telefone VARCHAR(20);
ALTER TABLE diaria_diaristas ADD COLUMN IF NOT EXISTS email VARCHAR(200);

-- 2) Passagem de turno (diario de posto)
CREATE TABLE IF NOT EXISTS operacional_passagens_turno (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID NOT NULL REFERENCES posts(id),
  author_user_id UUID NOT NULL,
  author_nome VARCHAR(200) NOT NULL,
  turno VARCHAR(30) NOT NULL,
  resumo TEXT NOT NULL,
  pendencias TEXT,
  data_turno DATE NOT NULL,
  criada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  lida_por JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_active BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_passagens_post_data ON operacional_passagens_turno (post_id, data_turno DESC);

-- 3) Avaliacao de equipe (nota 1-5 por funcionario do posto)
CREATE TABLE IF NOT EXISTS operacional_avaliacoes_equipe (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id UUID NOT NULL REFERENCES posts(id),
  employee_id UUID NOT NULL REFERENCES employees(id),
  avaliador_user_id UUID NOT NULL,
  avaliador_nome VARCHAR(200) NOT NULL,
  nota SMALLINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
  observacao TEXT,
  competencia DATE NOT NULL,
  criada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_avaliacoes_employee ON operacional_avaliacoes_equipe (employee_id, competencia DESC);
CREATE INDEX IF NOT EXISTS ix_avaliacoes_post ON operacional_avaliacoes_equipe (post_id, competencia DESC);
