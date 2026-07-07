-- REVERSÃO (⚠️ seguro apenas enquanto as tabelas estiverem VAZIAS)
BEGIN;
DROP TABLE IF EXISTS retencoes_fiscais_diaristas;
DROP TABLE IF EXISTS eventos_esocial_diaristas;
DROP TABLE IF EXISTS documentos_fiscais_diaristas;
DROP TYPE IF EXISTS tiporetencao;
DROP TYPE IF EXISTS statuseventoesocial;
DROP TYPE IF EXISTS tipoeventoesocial;
DROP TYPE IF EXISTS statusdocumentofiscal;
DROP TYPE IF EXISTS tipodocumentofiscal;
COMMIT;
