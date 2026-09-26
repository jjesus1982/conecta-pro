-- Preenchimento automático de `data_fato` a partir da batida vinculada.
--
-- POR QUE TRIGGER e não mexer nos 14 INSERTs: são 14 sítios em 5 módulos (dashboard_service,
-- atendimento_funcionario, time_record_service, webhook do Sólides, tools_ponto do agente).
-- Alterar os 14 é onde se esquece um — e o esquecido fica MUDO, que é o defeito que esta casa
-- mais paga. Uma guarda no ponto por onde todos passam cobre os 14 de hoje e os que vierem.
--
-- ⚠️ Só preenche quando está NULO e quando a batida existe. Nunca sobrescreve o que o humano
-- declarou: se o DP disser que a falta foi dia 18, é dia 18, mesmo que a batida diga outra coisa.
CREATE OR REPLACE FUNCTION gp_justificativa_data_fato() RETURNS trigger AS $$
BEGIN
  IF NEW.data_fato IS NULL AND NEW.punch_id IS NOT NULL THEN
    SELECT date(p.punch_timestamp) INTO NEW.data_fato
    FROM gp_clock_punches p WHERE p.punch_id = NEW.punch_id LIMIT 1;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_gp_justificativa_data_fato ON gp_justifications;
CREATE TRIGGER trg_gp_justificativa_data_fato
  BEFORE INSERT OR UPDATE ON gp_justifications
  FOR EACH ROW EXECUTE FUNCTION gp_justificativa_data_fato();
