-- ============================================================================
-- PRODUÇÃO — 25/09/2026 — A EMISSÃO FISCAL FOI LIGADA
-- Autorização do Jordan no chat, explícita e repetida:
--   «pode ir» · «eu não mexo no env eu não programo, você programa, você coloca,
--    tem toda a minha autorização, executa tudo o que precisar»
--
-- A partir daqui o Conecta PRO emite documento fiscal COM VALOR, irreversível.
-- ============================================================================

-- 1) NUMERAÇÃO DE PRODUÇÃO. Série 2 = a do Conecta PRO («corte limpo»). A série 1 é do
--    emissor de terceiro (nfemais.com.br), que parou na NF-e nº 10.026 em 17/09/2026 —
--    ela NÃO é declarada de propósito: quem tentar emitir nela em produção leva
--    NUMERACAO_NAO_DECLARADA, que é o certo.
INSERT INTO nfe_numeracao (emitente_cnpj, serie, tp_amb, ultimo)
VALUES ('35710481000103', 2, '1', 0)
ON CONFLICT (emitente_cnpj, serie, tp_amb) DO NOTHING;

-- NFS-e série 901, mesma lógica: 70000 é do portal da contabilidade (parou na 123),
-- 900 é do sandbox. Nenhuma das duas é declarada para produção.
INSERT INTO nfse_numeracao (prestador_cnpj, serie, ambiente, ultimo)
VALUES ('35710481000103', '901', 'producao', 0),
       ('66014833000110', '901', 'producao', 0)
ON CONFLICT (prestador_cnpj, serie, ambiente) DO NOTHING;

-- 2) PIS/COFINS suspensos por liminar — parâmetro, não constante.
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS pis_cofins_processo VARCHAR(60);
UPDATE empresas SET pis_cofins_processo = '1038495-94.2024.4.01.3200' WHERE slug = 'conecta_eletronica';

-- 3) Série da DPS por empresa (a NFS-e já usava; registrado aqui por completude).
UPDATE empresas SET nfse_serie_rps = '901' WHERE slug IN ('conecta_eletronica','conecta_patrimonial');

-- ============================================================================
-- O QUE FOI PARA O `.env` (fora do git, por construção)
--
--   NFE_AMBIENTE=1
--   NFE_PRODUCAO_LIBERADA=SIM_EU_SEI_O_QUE_ESTOU_FAZENDO
--   NFSE_PRODUCAO_LIBERADA=sim-emitir-nfse-em-producao-com-iss-devido
--
-- ERRO MEU, corrigido: gerei frases ALEATÓRIAS achando que eram segredo. Não são —
-- o valor é FIXO no código (`nfe_provider._SENHA_GATE_PRODUCAO` e
-- `nfse_nacional._SENHA_GATE_NFSE`) e é uma DECLARAÇÃO DE INTENÇÃO: quem escreve
-- está dizendo, por extenso, o que está fazendo. Com a frase errada o gate nunca
-- abriria, e `sefaz-status` mostrou `producao_liberada: False` — foi assim que vi.
--
-- (Também vazei a primeira frase aleatória numa saída de terminal por erro de shell
--  — `${VAR:-AUSENTE}` devolve o VALOR quando a variável existe. Troquei na hora;
--  e, como a frase certa é pública no código, o vazamento não valia nada de qualquer
--  forma. A lição fica: conferir variável é `[ -n "$VAR" ] && echo definido`.)
--
-- Backup do .env anterior: .env.bak-antes-producao-fiscal-20260925_124504
-- ============================================================================
--
-- ESTADO MEDIDO DEPOIS, nos 9 contêineres:
--   NFE_AMBIENTE=1 · gate NF-e=definido · gate NFS-e=definido   (9 de 9)
--   sefaz-status: ambiente Produção · cStat 107 Serviço em Operação · producao_liberada TRUE
--   checar_pronto_para_produzir: de 10 itens faltando → 4, e NENHUM dos 4 impede a NF-e
--     (2 são o ambiente da NFS-e, 1 é produto sem entrada conhecida, 1 são os 34 XML de compra)
--
-- A PAREDE QUE FICOU DE PÉ, e é o achado da rodada: com `NFE_AMBIENTE=1`, o endpoint
-- `POST /fiscal/nfe/emitir` passaria a emitir DE VERDADE em qualquer chamada que não
-- dissesse o ambiente — ele herdava da variável. Agora `ambiente` é OBRIGATÓRIO no
-- payload (sem default), e `cancelar` tira o ambiente DA PRÓPRIA NOTA. Emitir em
-- produção virou ATO, não herança. Ver commit 78ce4a58f.

-- ============================================================================
-- 25/09/2026, TARDE — O ENDEREÇO DO EMITENTE ESTAVA ERRADO NO ERP
--
-- Achado ANTES da primeira nota de produção, pela frente AB1 (leiaute do DANFE), e conferido
-- por mim nos PDFs originais antes de escrever uma linha de UPDATE.
--
-- O ERP dizia, para a CONECTAMAIS ELETRÔNICA (35.710.481/0001-03):
--     Avenida Constantino Nery, 3343 — Chapada — CEP 69050001
--
-- Os DOIS documentos que o FISCO emitiu para esse CNPJ dizem outra coisa, e concordam
-- entre si:
--     · DANFE da NF-e 10.026 (SEFAZ-AM, 17/09/2026, emissor nfemais)
--     · NFS-e 121 (Padrão Nacional / ADN, competência 09/2026)
--       → «RUA NOVA PALESTINA, 51, CRESPO — Manaus/AM — CEP 69073488»
--
-- A PATRIMONIAL (66.014.833/0001-10) tinha rua e número certos e o CEP **vazio**.
-- A NFS-e 31 (ADN, 08/2026) traz CEP 69055630.
--
-- POR QUE ISSO BLOQUEAVA A PRIMEIRA NOTA: o endereço do emitente vai DENTRO do XML
-- assinado. Nota autorizada com endereço que não é o do cadastro é documento fiscal
-- errado — e documento autorizado não se corrige editando campo: é carta de correção,
-- cancelamento com prazo, ou denúncia espontânea.

UPDATE empresas SET endereco_logradouro = 'Rua Nova Palestina', endereco_numero = '51',
                    endereco_bairro = 'Crespo', endereco_cep = '69073488',
                    endereco_municipio = 'Manaus', endereco_uf = 'AM',
                    codigo_municipio_ibge = '1302603'
 WHERE slug = 'conecta_eletronica';

UPDATE empresas SET endereco_cep = '69055630' WHERE slug = 'conecta_patrimonial';

-- NFS-e das DUAS empresas em produção (a Patrimonial ainda estava em homologação, e ela
-- é a que emite TODA a cessão de mão de obra).
UPDATE empresas SET nfse_ambiente = 'producao' WHERE status = 'ativa';

-- ⚠️ PARA O DONO: eu NÃO decidi qual endereço é o verdadeiro — eu fiz o ERP falar o que o
-- fisco já registrou. Se a empresa REALMENTE mudou para a Constantino Nery, o conserto
-- começa na Receita/SEFAZ (alteração cadastral) e só depois aqui; emitir com endereço que
-- o cadastro não tem é o problema, não a solução.
--
-- A régua que impede a volta: `checar_pronto_para_produzir.py` passou a cobrar endereço
-- completo (logradouro, número, bairro, CEP de 8 dígitos, IBGE de 7) das empresas ativas.
-- Ela NÃO adivinha qual endereço vale — campo vazio é erro sem opinião; qual dos dois é o
-- certo é decisão do dono.
--
-- CONFERÊNCIA DE PRONTIDÃO: 10 itens faltando de manhã → 4 → **2**, e nenhum dos 2 impede a
-- NF-e de material (1 produto sem entrada conhecida e os 34 XML de compra que a SEFAZ ainda
-- vai distribuir).
