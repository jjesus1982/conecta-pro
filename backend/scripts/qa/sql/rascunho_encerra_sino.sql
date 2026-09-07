-- Rascunho que sai de 'rascunho' (executado, descartado, rejeitado, falha) ou é APAGADO
-- encerra o aviso dele no sino. Medido em 07/09/2026: 585 avisos ativos apontando para
-- rascunho descartado e 390 "PEDIR COTAÇÃO" de oráculos (item "ORACULO x") — os oráculos
-- descartam/apagam o rascunho por SQL e a notificação ficava viva para o dono, 36 por dia.
-- Gatilho, não código: cobre controller, agente e limpeza de oráculo pelo mesmo caminho.
-- Idempotente. Instalado por `checar_sino_surdo.py --instalar` (junto do sino_corte.sql).
CREATE OR REPLACE FUNCTION rascunho_encerra_sino() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid := COALESCE(NEW.id, OLD.id);
BEGIN
    IF TG_OP = 'DELETE' OR NEW.status IS DISTINCT FROM 'rascunho' THEN
        UPDATE communication_notifications
           SET is_active = false, read_at = COALESCE(read_at, now())
         WHERE reference_type = 'agent_draft' AND reference_id = v_id
           AND COALESCE(is_active, true) = true;
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$;

DROP TRIGGER IF EXISTS trg_rascunho_encerra_sino_upd ON agent_drafts;
CREATE TRIGGER trg_rascunho_encerra_sino_upd
    AFTER UPDATE OF status ON agent_drafts
    FOR EACH ROW EXECUTE FUNCTION rascunho_encerra_sino();

DROP TRIGGER IF EXISTS trg_rascunho_encerra_sino_del ON agent_drafts;
CREATE TRIGGER trg_rascunho_encerra_sino_del
    AFTER DELETE ON agent_drafts
    FOR EACH ROW EXECUTE FUNCTION rascunho_encerra_sino();
