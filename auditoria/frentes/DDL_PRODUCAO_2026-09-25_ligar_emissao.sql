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
