-- gp_justifications ganha a DATA DO FATO — 25/09/2026
--
-- POR QUE: medido hoje, 75 faltas em 14 dias e ZERO justificadas. Não é indisciplina: a tabela
-- não tem onde dizer "faltei no dia 18". As 16 linhas existentes são 15 `atraso` (13 amarradas
-- a um `punch_id` que EXISTE) e 1 `atestado_medico` de 21/07 sem batida — esse é exatamente o
-- caso que não tinha onde declarar o dia.
--
-- `created_at` não serve: é quando a justificativa foi DIGITADA, não quando o fato ocorreu.
-- Justificar hoje uma falta da semana passada é o caso normal, não a exceção.
--
-- ⚠️ Coluna NULA por default: nenhuma query existente muda de resultado. O backfill abaixo dá
-- sentido às linhas antigas usando a data da PRÓPRIA batida vinculada — a única fonte honesta
-- que existe para elas.
ALTER TABLE gp_justifications ADD COLUMN IF NOT EXISTS data_fato date;
COMMENT ON COLUMN gp_justifications.data_fato IS
  'Dia a que a justificativa se refere. Para ausencia e o unico elo com a escala: sem ele nao ha '
  'como saber que dia foi justificado. created_at e quando foi digitada, nao quando ocorreu.';

CREATE INDEX IF NOT EXISTS ix_gp_justifications_data_fato ON gp_justifications (data_fato);
CREATE INDEX IF NOT EXISTS ix_gp_justifications_emp_data  ON gp_justifications (employee_id, data_fato);

-- backfill: quem tem batida vinculada herda a data dela (fonte honesta, não inferência)
UPDATE gp_justifications j SET data_fato = date(p.punch_timestamp)
FROM gp_clock_punches p
WHERE p.id::text = j.punch_id AND j.data_fato IS NULL AND j.punch_id IS NOT NULL;
