-- ============================================================================
-- MIGRATION FORWARD — Missão 1 SST/MB Consultoria (PDFs reais → dado estruturado)
-- Data: 2026-07-08
-- Fontes REAIS (uploads/sst_mb/, extração pdfplumber-equivalente/OCR em 2026-07-08):
--   * PCMSO_CONECTA.pdf  (escaneado; OCR tesseract): médico coordenador,
--     vigência 05/2026–04/2027, planilha II de exames por função (pág. 13-20)
--   * LTCAT_CONECTA.pdf  (escaneado; OCR): parecer conclusivo pág. 34-37 com
--     códigos Tabela 24 POR FUNÇÃO (02.01.001 ruído, 02.01.014 calor,
--     02.01.002 VMB, 03.01.999* biológico ASG) e medições
--   * PGR_CONECTA.pdf    (texto nativo): GES por função, APRO, atividades
--   * Avaliacao_de_ruido.pdf (dosimetria FOR-2000 29/05/2026, operador
--     GEILSON RODRIGUES DE ANDRADE, roçadeira): Lavg(NR-15) 89,0 dB(A),
--     NEN 90,5 dB(A), máx 102,6 dB, dose proj. 8h 174,67%
--   * Avaliacao_vibracao_jardineiro.pdf (VIBRATE 02/06/2026, VMB roçadeira):
--     aren = A(8) = 3,85 m/s² (limite NR-15 Anexo 8: 5,0; nível de ação: 2,5)
-- PRINCÍPIO: nada fabricado — só o que os laudos PROVAM. Divergências do
--   laudo com a Tabela 24 vigente ficam REGISTRADAS (ver risco biológico).
-- Reversão: 2026-07-08_sst_missao1_pcmso_tabela24_REVERSAO.sql
-- Backup lógico prévio: backup_pre_missao1_2026-07-08_gp_risks_gp_asos.sql
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. sst_pcmso — registro do PCMSO real (destrava respMonit do S-2220)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sst_pcmso (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    medico_coordenador VARCHAR(120) NOT NULL,
    crm                VARCHAR(20)  NOT NULL,
    uf                 VARCHAR(2)   NOT NULL,
    nit                VARCHAR(20),
    vigencia_inicio    DATE NOT NULL,
    vigencia_fim       DATE NOT NULL,
    arquivo            VARCHAR(500),
    elaborador         VARCHAR(255),
    exames_por_funcao  JSONB,
    observacoes        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ
);
COMMENT ON TABLE sst_pcmso IS
    'PCMSO real (MB/MBS Consultoria) — médico coordenador usado no respMonit do S-2220; nunca fabricado';
COMMENT ON COLUMN sst_pcmso.exames_por_funcao IS
    'Planilha II do PCMSO (exames por função) com códigos Tabela 27 eSocial quando verificados; cod_tabela27=null onde não confirmado';

INSERT INTO sst_pcmso (
    medico_coordenador, crm, uf, nit, vigencia_inicio, vigencia_fim,
    arquivo, elaborador, exames_por_funcao, observacoes
) VALUES (
    'DR. POJUCAN MANOEL MORAES',
    '467',
    'AM',
    '100.817.307-29',
    DATE '2026-05-01',
    DATE '2027-04-30',
    '/app/uploads/sst_mb/PCMSO_CONECTA.pdf',
    'MBS ENGENHARIA AMBIENTAL E SEGURANÇA DO TRABALHO (CNPJ 41.339.889/0001-13)',
    '{
      "PORTARIA": {
        "funcoes": ["AGP", "LIDER"],
        "exames": [
          {"nome": "Exame clinico (ASO)", "cod_tabela27": "0295"},
          {"nome": "Audiometria", "cod_tabela27": "0281"},
          {"nome": "Hemograma completo", "cod_tabela27": "0693"},
          {"nome": "Grupo sanguineo + Fator RH (admissional)", "cod_tabela27": "0673"},
          {"nome": "Acuidade visual", "cod_tabela27": "0296"},
          {"nome": "Avaliacao psicologica", "cod_tabela27": "0300"}
        ]
      },
      "CONSERVACAO_E_LIMPEZA": {
        "funcoes": ["ASG", "JARDINEIRO"],
        "exames": [
          {"nome": "Exame clinico (ASO)", "cod_tabela27": "0295"},
          {"nome": "Hemograma completo", "cod_tabela27": "0693"},
          {"nome": "Grupo sanguineo + Fator RH (admissional)", "cod_tabela27": "0673"},
          {"nome": "Rx de coluna lombo-sacra", "cod_tabela27": "1075"},
          {"nome": "Acuidade visual", "cod_tabela27": "0296"},
          {"nome": "Avaliacao psicologica", "cod_tabela27": "0300"}
        ]
      },
      "MANUTENCAO": {
        "funcoes": ["ARTIFICE"],
        "exames": [
          {"nome": "Exame clinico (ASO)", "cod_tabela27": "0295"},
          {"nome": "Audiometria", "cod_tabela27": "0281"},
          {"nome": "Hemograma completo", "cod_tabela27": "0693"},
          {"nome": "Grupo sanguineo + Fator RH (admissional)", "cod_tabela27": "0673"},
          {"nome": "Espirometria", "cod_tabela27": null},
          {"nome": "Raio X do torax", "cod_tabela27": null},
          {"nome": "Rx de coluna lombo-sacra", "cod_tabela27": "1075"},
          {"nome": "Eletrocardiograma", "cod_tabela27": null},
          {"nome": "Eletroencefalograma", "cod_tabela27": null},
          {"nome": "Avaliacao psicologica", "cod_tabela27": "0300"}
        ]
      }
    }'::jsonb,
    'Extraído por OCR (tesseract 5.5, 2026-07-08) do PCMSO escaneado. Tipo: ELABORAÇÃO, '
    'Revisão 01, "MAIO DE 2026 A ABRIL DE 2027" (pág. 1). Médico: "DR. POJUCAN MANOEL '
    'MORAES. MÉDICO DO TRABALHO. CRM/AM. 467." (pág. 3); NIT/REGISTRO 100.817.307-29 '
    '(capa). Empresa: CNPJ 35.710.481/0001-03. Códigos Tabela 27 dos exames de '
    'espirometria/RX tórax/ECG/EEG NÃO verificados — preencher antes de declarar esses '
    'procedimentos no S-2220 (exame clínico 0295 verificado).'
);

-- ---------------------------------------------------------------------------
-- 2. gp_risks — colunas eSocial S-2240 (Tabela 24 + EPC/EPI + medição real)
-- ---------------------------------------------------------------------------
ALTER TABLE gp_risks
    ADD COLUMN IF NOT EXISTS cod_agente_nocivo  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS utiliz_epc         VARCHAR(1),
    ADD COLUMN IF NOT EXISTS utiliz_epi         VARCHAR(1),
    ADD COLUMN IF NOT EXISTS medicao            TEXT,
    ADD COLUMN IF NOT EXISTS funcoes_aplicaveis JSONB;

COMMENT ON COLUMN gp_risks.cod_agente_nocivo IS
    'Tabela 24 eSocial (S-2240 codAgNoc) — SÓ preenchido quando o LTCAT/laudo enquadra; NULL = risco não declarável na Tabela 24 (ergonômico/acidente) ou sem enquadramento provado';
COMMENT ON COLUMN gp_risks.utiliz_epc IS
    'S-2240 utilizEPC: 0=não se aplica, 1=não implementa, 2=implementa (leiaute S-1.2)';
COMMENT ON COLUMN gp_risks.utiliz_epi IS
    'S-2240 utilizEPI: 0=não se aplica, 1=não utilizado, 2=utilizado (leiaute S-1.2)';
COMMENT ON COLUMN gp_risks.medicao IS
    'Medição/conclusão REAL dos laudos MB (dosimetria, VMB, LTCAT) com fonte e data — nunca fabricada';
COMMENT ON COLUMN gp_risks.funcoes_aplicaveis IS
    'Funções (tokens AGP|LIDER|ASG|ARTIFICE|JARDINEIRO) a que o risco se aplica — fonte: PGR 28/05/2026 (GES 1-4) e LTCAT parecer conclusivo';

-- 2a. posto_id órfão → NULL honesto (os 15 riscos apontavam para UUIDs
--     inexistentes em posts; PGR/LTCAT mapeiam por FUNÇÃO/GES, não por posto).
--     Valores originais preservados no backup e na REVERSAO.
--     A coluna deixa de ser NOT NULL: risco mapeado por função pode não ter posto.
ALTER TABLE gp_risks ALTER COLUMN posto_id DROP NOT NULL;
UPDATE gp_risks r SET posto_id = NULL
WHERE r.posto_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.id::text = r.posto_id);

-- 2b. funcoes_aplicaveis por GES do PGR (28/05/2026):
--     grupo 15b03ff6* (ids 1-5)  = APRO GES 2 (portaria)      → AGP, LIDER
--     grupo ed872365* (ids 6-9)  = APRO GES 3 (limpeza/ASG)   → ASG
--     grupo 5858e622* (ids 10-13)= manutenção (artífice)      → ARTIFICE
--     grupo e4909c49* (ids 14-15)= liderança de portaria      → LIDER
UPDATE gp_risks SET funcoes_aplicaveis = '["AGP","LIDER"]'::jsonb  WHERE id IN (1,2,3,4,5);
UPDATE gp_risks SET funcoes_aplicaveis = '["ASG"]'::jsonb          WHERE id IN (6,7,9);
UPDATE gp_risks SET funcoes_aplicaveis = '["ASG","ARTIFICE","JARDINEIRO"]'::jsonb WHERE id = 8;
UPDATE gp_risks SET funcoes_aplicaveis = '["ARTIFICE"]'::jsonb     WHERE id IN (10,11,12,13);
UPDATE gp_risks SET funcoes_aplicaveis = '["LIDER"]'::jsonb        WHERE id IN (14,15);

-- 2c. Enquadramentos PROVADOS pelos laudos nos riscos existentes
-- id 12 — ruído de ferramentas (manutenção/artífice): LTCAT GES 3
UPDATE gp_risks SET
    cod_agente_nocivo = '02.01.001',
    utiliz_epc = '0',
    utiliz_epi = '2',
    medicao = 'LTCAT 28/05/2026 (pág. 36, função ARTÍFICE/JARDINEIRO/ASG): ruído contínuo '
              'ou intermitente mín 78,0 – máx 89,0 dB(A); conclusão: abaixo dos Limites de '
              'Tolerância NR-15 Anexo 1 → aposentadoria especial DESCARACTERIZADA. '
              'EPI: protetor auditivo CA 25.382 (utilizEPI=2). EPC específico para ruído '
              'não indicado no laudo (utilizEPC=0).',
    updated_at = now()
WHERE id = 12;

-- id 2 — calor (portaria): documentação SEM codAgNoc (portaria declara 09.01.001)
UPDATE gp_risks SET
    medicao = 'LTCAT 28/05/2026 (pág. 35, função AGP/Líder): calor abaixo dos Limites de '
              'Exposição NR-15 Anexo 3 (PGR: 24–26,5 °C amb.); aposentadoria especial '
              'DESCARACTERIZADA (ref. Tabela 24 do laudo: 02.01.014). Não codificado aqui '
              'porque a declaração S-2240 da portaria é 09.01.001 (ausência).',
    updated_at = now()
WHERE id = 2;

-- id 8 — calor (ASG/artífice/jardineiro): idem, documentação sem codAgNoc
UPDATE gp_risks SET
    medicao = 'LTCAT 28/05/2026 (pág. 36, função ARTÍFICE/JARDINEIRO/ASG): calor abaixo '
              'dos Limites de Exposição NR-15 Anexo 3 (PGR GES 3: 29,5 °C); aposentadoria '
              'especial DESCARACTERIZADA (ref. Tabela 24 do laudo: 02.01.014). Não '
              'codificado: agente abaixo dos limites não é declarado no S-2240 deste GES.',
    updated_at = now()
WHERE id = 8;

-- 2d. NOVOS riscos provados pelos laudos (posto_id NULL honesto)
INSERT INTO gp_risks (risk_id, posto_id, categoria, descricao, nivel, fonte_geradora,
                      medidas_controle, epi_recomendado, status,
                      cod_agente_nocivo, utiliz_epc, utiliz_epi, medicao,
                      funcoes_aplicaveis, created_at)
VALUES
-- N1: PORTARIA — ausência de agente nocivo (LTCAT pág. 35)
('a1b5f0e1-2026-0708-9001-000000000001', NULL, 'fisico',
 'Ausência de agente nocivo (Tabela 24: 09.01.001) — portaria: ruído e calor avaliados e abaixo dos limites NR-15',
 'baixo',
 'LTCAT MB/MBS 28/05/2026 — parecer conclusivo, função LÍDER DE PORTARIA e AGP',
 '["Protetor auditivo CA 25.382 disponível", "Extintores de incêndio e sinalização (EPC)"]'::jsonb,
 '[]'::jsonb,
 'controlado',
 '09.01.001', NULL, NULL,
 'LTCAT 28/05/2026 (pág. 35): ruído contínuo/intermitente mín 65,0 – máx 70,0 dB(A) '
 '(abaixo do LT NR-15 Anexo 1) e calor abaixo dos Limites de Exposição NR-15 Anexo 3. '
 'Conclusão do laudo: aposentadoria especial DESCARACTERIZADA (Decreto 3.048/1999). '
 '⇒ Declaração S-2240 da função: 09.01.001 — ausência de agente nocivo.',
 '["AGP","LIDER"]'::jsonb, now()),

-- N2: JARDINEIRO — ruído roçadeira (dosimetria real 29/05/2026)
('a1b5f0e1-2026-0708-9002-000000000002', NULL, 'fisico',
 'Exposição a ruído na operação de roçadeira (jardinagem)',
 'alto',
 'Roçadeira — operação de capina (PGR GES 3 / laudo FOR-2000)',
 '["Protetor auditivo CA 25.382", "Operação limitada a ~1h por ciclo (reabastecimento/aquecimento)"]'::jsonb,
 '["Protetor Auricular CA 25.382"]'::jsonb,
 'identificado',
 '02.01.001', '0', '2',
 'Dosimetria FOR-2000 29/05/2026 (operador GEILSON RODRIGUES DE ANDRADE, serviço de '
 'operação com roçadeira, avaliadora Eng. Marcia Batista da Silva/MBS): Lavg(NR-15) '
 '89,0 dB(A); NEN 90,5 dB(A); máximo 102,6 dB; dose projetada 8h 174,67% (critério '
 'NR-15, 85 dB(A)/8h); operação real limitada a ~1h por ciclo. LTCAT 28/05/2026 '
 '(pág. 36): mín 78,0 – máx 89,0 dB(A), conclusão "abaixo dos LT" → aposentadoria '
 'especial DESCARACTERIZADA. Medição ≥ 80 dB(A) ⇒ agente declarável no S-2240. '
 'EPI protetor auditivo CA 25.382 (utilizEPI=2); sem EPC específico (utilizEPC=0).',
 '["JARDINEIRO"]'::jsonb, now()),

-- N3: JARDINEIRO — vibração mãos e braços (laudo VIBRATE 02/06/2026)
('a1b5f0e1-2026-0708-9003-000000000003', NULL, 'fisico',
 'Vibração localizada mãos e braços (VMB) na operação de roçadeira',
 'medio',
 'Roçadeira — vibração transmitida às mãos/braços (laudo VIBRATE SN 051000806)',
 '["Pausas por ciclo de operação (~1h)", "Manutenção do equipamento"]'::jsonb,
 '[]'::jsonb,
 'identificado',
 '02.01.002', '0', '0',
 'Laudo VIBRATE 02/06/2026 (setor JARDINAGEM, função JARDINEIRO, máquina roçadeira, '
 'tempo de exposição 03:00): aren = 3,85 m/s²; A(8) = 3,85 m/s² (X=1,99; Y=3,16; '
 'Z=0,94); VDVR = 74,75 m/s^1,75. Limite NR-15 Anexo 8 (5,0 m/s²): NÃO excedido; '
 'nível de ação NR-09/NHO-10 (2,5 m/s²): EXCEDIDO ⇒ declarável no S-2240. LTCAT '
 '28/05/2026 (pág. 36, cód. 02.01.002): aposentadoria especial DESCARACTERIZADA. '
 'LTCAT não indica EPI eficaz para VMB (lista protetor auditivo, que não mitiga '
 'vibração) ⇒ utilizEPC=0 e utilizEPI=0 (não se aplica). Calibração do medidor: '
 'certificado CRS2464/2025 (válido, Criffer).',
 '["JARDINEIRO"]'::jsonb, now()),

-- N4: ASG — risco biológico CARACTERIZADO (LTCAT pág. 37)
('a1b5f0e1-2026-0708-9004-000000000004', NULL, 'biologico',
 'Exposição a agentes biológicos — limpeza de lixeiras e banheiros (ASG)',
 'alto',
 'Limpeza de lixeiras e banheiros dos condomínios (LTCAT NR-15 Anexo 14)',
 '["Ficha de EPI", "Calçado de segurança PVC tipo botina CA 32.807"]'::jsonb,
 '["Botina PVC CA 32.807", "Luvas de Latex"]'::jsonb,
 'identificado',
 '03.01.999', '0', '2',
 'LTCAT 28/05/2026 (pág. 37): "A avaliação Biológica possui Exposição. Portanto, '
 'CARACTERIZADO o direito à Aposentadoria Especial decreto 3.048/99, para a função '
 'ASG - Aux. De Serviços Gerais, que trabalha em contato com limpeza de lixeira e '
 'banheiros" (NR-15 Anexo 14). EPI: botina PVC CA 32.807 (utilizEPI=2). ATENÇÃO: o '
 'laudo usa o código 03.01.999, que NÃO consta na Tabela 24 vigente (S-1.2); a '
 'atividade descrita corresponde a 03.01.007 (coleta/industrialização de lixo, '
 'limpeza de banheiros). CONFIRMAR código com a MB Consultoria antes de transmitir. '
 'IMPACTO: risco caracterizado ⇒ GFIP/aposentadoria especial p/ ASG.',
 '["ASG"]'::jsonb, now());

-- ---------------------------------------------------------------------------
-- 3. gp_asos.exames — procedimentos Tabela 27 por ASO (S-2220 procRealizado)
-- ---------------------------------------------------------------------------
ALTER TABLE gp_asos ADD COLUMN IF NOT EXISTS exames JSONB;
COMMENT ON COLUMN gp_asos.exames IS
    'Procedimentos Tabela 27 do ASO: [{dt_exame, cod_procedimento, nome, fonte}]. '
    'O exame clínico (0295) é derivação determinística de data_realizacao (todo ASO '
    'realizado inclui avaliação clínica ocupacional — NR-7/PCMSO); exames '
    'complementares só entram com evidência documental.';

UPDATE gp_asos SET
    exames = jsonb_build_array(jsonb_build_object(
        'dt_exame', to_char(data_realizacao, 'YYYY-MM-DD'),
        'cod_procedimento', '0295',
        'nome', 'Avaliação clínica ocupacional (anamnese e exame físico)',
        'fonte', 'Derivado de gp_asos.data_realizacao (ASO realizado = exame clínico, NR-7) + PCMSO 05/2026 planilha II'
    )),
    updated_at = now()
WHERE data_realizacao IS NOT NULL
  AND (exames IS NULL OR exames = '[]'::jsonb);

COMMIT;
