-- Corte de origem SURDA no sino — instalado em 06/09/2026 por checar_sino_surdo --instalar.
-- A lista mora em system_configs (chave 'sino.origens_cortadas', JSON array em texto).
-- Origem na lista NÃO entra em communication_notifications (o produtor continua logando).
-- Reversível: DROP TRIGGER sino_corte_bi ON communication_notifications; ou --religar <origem>.
CREATE OR REPLACE FUNCTION sino_corte_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE cortadas text;
BEGIN
  SELECT valor INTO cortadas FROM system_configs WHERE chave = 'sino.origens_cortadas';
  IF cortadas IS NOT NULL AND NEW.extra_data IS NOT NULL
     AND (cortadas::jsonb) ? coalesce(NEW.extra_data->>'origem', '') THEN
    RETURN NULL;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sino_corte_bi ON communication_notifications;
CREATE TRIGGER sino_corte_bi BEFORE INSERT ON communication_notifications
  FOR EACH ROW EXECUTE FUNCTION sino_corte_bi();
