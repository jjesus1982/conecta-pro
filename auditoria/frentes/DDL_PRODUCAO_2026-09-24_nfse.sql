-- ============================================================================
-- PRODUÇÃO — 24/09/2026 — NFS-e: a nota 29 que faltava e a nota 26 que foi erro
-- Executado pelo orquestrador, com autorização explícita do Jordan no chat:
--   «a 26 foi erro sim, pode gravar a 29»
--
-- COMO APARECEU: o Jordan subiu 8 DANFSe de 08/2026 e o cronograma de emissão.
-- Conferindo PDF contra banco, duas coisas:
--   (a) a NFS-e 29 da Patrimonial (Villa dos Pássaros, R$ 33.538,33) existe no
--       fisco e NÃO estava aqui — a sincronia por NSU pulou (47, 48, [49], 50);
--   (b) a NFS-e 26 duplica tomador e valor da 27 com código de serviço diferente.
--
-- MEDIÇÃO QUE ISSO DESTRAVOU — a numeração por CNPJ, que é a régua certa
-- (o NSU carrega todo tipo de documento, não só nota emitida; medir por ele
--  acusaria 419 e seria mentira):
--   Eletrônica  35.710.481/0001-03 → nº 2 a 123 · temos 89 · FALTAM 33
--   Patrimonial 66.014.833/0001-10 → nº 3 a  32 · temos 26 · FALTAM  4
--   Total: 37 notas emitidas no fisco sem linha aqui.
-- ============================================================================

ALTER TABLE nfse_emitidas_nacional ADD COLUMN IF NOT EXISTS observacao_interna TEXT;

INSERT INTO nfse_emitidas_nacional
  (chave_acesso, numero, competencia, data_emissao, tomador_cnpj, tomador_nome,
   valor_servicos, iss_valor, iss_aliquota, valor_liquido, inss_retido,
   codigo_servico, descricao, nsu, fonte, empresa_id, cancelada, observacao_interna)
VALUES
  ('13026032266014833000110000000000002926082896878833', '29', '2026-08',
   '2026-08-25 11:58:37', '13221953000121', 'CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS',
   33538.33, 0.0, 0.0, 29849.12, 3689.21,
   '110201', 'Vigilância, segurança ou monitoramento de bens, pessoas e semoventes.',
   49, 'danfse_pdf_do_dono_20260924', '7d79ed12-d480-4906-b2e0-2b2c4d299bab', false,
   'Gravada em 24/09/2026 ... origem PDF, não a resposta do fisco.')
ON CONFLICT DO NOTHING;

-- NÃO cancela nada no fisco — lá ela segue válida.
UPDATE nfse_emitidas_nacional
   SET observacao_interna = 'ERRO confirmado pelo Jordan em 24/09/2026 ... segue VÁLIDA no fisco.'
 WHERE chave_acesso = '13026032266014833000110000000000002626084972058132';

-- ============================================================================
-- PARAMETRIZAÇÃO REAL, extraída dos 8 DANFSe (antes disso o sistema chutava)
--
--   SÉRIE DA DPS = 70000  nas DUAS empresas  (o código assumia 900 e o fisco
--   recusava com «essa série+número já existe»)
--
--   Último nº de DPS em 08/2026:  Patrimonial 75 · Eletrônica 118
--
--   | Serviço                              | Cód. nacional | NBS          |
--   |--------------------------------------|---------------|--------------|
--   | Agentes de portaria / vigilância     | 11.02.01      | 1.1802.90.00 |
--   | Limpeza, conservação, serv. gerais   | 07.10.02      | 1.1803.10.00 |
--   | Manutenção (CFTV/cerca/portão)       | 14.01.01      | 1.2001.89.00 |
--   | Instalação / portaria remota         | 14.06.01      | 1.2003.29.00 |
--
--   O `cNBS` que estava chumbado no código era 1.2003.29.00 — certo SÓ para
--   14.06.01, errado para os outros três. Por isso o fisco devolvia descrição
--   errada nas notas de vigilância.
--
--   INSS: retenção de 11% pelo Art. 31 da Lei 9.711/98, base = valor bruto
--   menos vale-alimentação e vale-transporte do mês. A Patrimonial (Simples)
--   não tem ISS na nota — ISSQN vai no DAS. A Eletrônica tem ISS 5%.
--
--   IBS/CBS: a nota 29 traz R$ 335,38 sobre R$ 33.538,33 = exatamente 1,00%,
--   que é a soma da transição de 2026 (IBS-UF 0,1% + CBS 0,9%).
-- ============================================================================
