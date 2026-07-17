# PRD — Conecta PRO Multi-CNPJ (Grupo Conecta Mais)

**Versão:** 1.0 · **Data:** 2026-07-17 · **Dono do produto:** Jordan Jesus
**Docs-irmãos:** `PREMORTEM_MULTI_CNPJ_2026-07-17.md` (riscos → regras) · `PLANO_EXECUCAO_MULTI_CNPJ_2026-07-17.md` (como/quando) · `PLANO_MULTI_CNPJ_GRUPO_CONECTA_2026-07-17.md` (diagnóstico técnico, arquivo:linha)

## 1. Visão

O Conecta PRO deixa de ser o ERP de UMA empresa e passa a ser o ERP do **Grupo Conecta Mais**: duas
pessoas jurídicas permanentes, operando simultaneamente, cada documento/transação/obrigação sabendo a
qual empresa pertence — com visão consolidada do Grupo e regressão zero na operação atual.

| | CNPJ1 — CONECTAMAIS ELETRONICA LTDA | CNPJ2 — CONECTAMAIS PATRIMONIAL LTDA |
|---|---|---|
| CNPJ | 35.710.481/0001-03 (abertura 05/12/2019) | **66.014.833/0001-10** (abertura 31/03/2026) |
| Fantasia | CONECTA MAIS - REDES E SEGURANÇA | CONECTAMAIS PATRIMONIAL |
| Atividade (negócio) | Segurança eletrônica + portaria remota | Terceirização de mão de obra |
| CNAE principal | 8011-1/01 (vigilância e segurança privada) | 8111-7/00 (apoio a edifícios) |
| IM Manaus | 45177801 | **721042001** |
| Endereço | R. Nova Palestina, 51, Crespo, Manaus | R. Victor Hughes, 19, Cj. Castelo Branco I, Parque 10, Manaus, CEP 69.055-630 |
| Regime | Lucro Real (→ Simples em 01/2027, já representável) | Simples Nacional (ME; comprovante de opção pendente de anexar) |
| Banco | Inter (integração atual, intocada) | **Cora** (integração nova; cert produção já gerado) |
| Funcionários | Somente PJ | **Todos os CLT (56)** |
| Sócio/administrador | Jordan Santos de Jesus | Jordan Santos de Jesus (sócio único, capital R$100.000) |
| Condomínios | Parise Village · Residencial Gelain · Green Hills | Villa dos Pássaros · Mirante das Flores · Ideal Flores · Laranjeiras Village · Michellangelo · Villa Dei Fiore · Prime Arena |

⚠️ **Regra confirmada pelos documentos oficiais (17/07): os CNAEs das duas empresas se SOBREPÕEM**
(ambas têm monitoramento eletrônico 8020-0/01, apoio a edifícios 8111-7/00 e limpeza 8121-4/00 no
cartão CNPJ). Portanto o roteador serviço→empresa é **regra de negócio declarada pelo Jordan**
(tabela acima), NUNCA inferência por CNAE. **Regra de grafia (Jordan, 17/07):** a razão social emendada ("CONECTAMAIS") foi erro de grafia da
contadora no registro. **Exibição no sistema e documentos = "Conecta Mais Patrimonial" / "Conecta
Mais Eletrônica" (nome_fantasia da tabela `empresas`)**; a razão social EXATA da Receita aparece
apenas onde a lei exige (qualificação em contratos/aditivos, campos fiscais — a NFS-e usa o cadastro
da Receita automaticamente). Corrigido na E1: seed atualizado com razão oficial + fantasia de exibição.

**Datas:** competência de corte **07/2026** (documentos de julho processados em agosto já saem pela
Patrimonial — e-mail formal à Portte em 17/07); **sistema 100% pronto em 31/07/2026**; kits híbridos
em ago+set; kit 100% Patrimonial ~out/2026.

## 2. Princípios (inegociáveis — derivados do pré-mortem e das regras da casa)

1. **Imutabilidade histórica** — documento de competência fechada re-renderiza IDÊNTICO para sempre; identidade do emitente resolvida por competência+vínculo, nunca por constante global.
2. **Espelhar, não assumir** — datas trabalhistas = Portte (que é **permanente e inegociável**, executora da transição; o sistema reflete); dinheiro = API do banco; vazio real = "aguardando dado", nunca número fabricado.
3. **Diff-zero no CNPJ1** — toda mudança prova (XML, PDF, suítes release) que a operação atual segue idêntica até a virada explícita.
4. **Dinheiro que sai = gate humano** — no Inter, OTP interno; no Cora, aprovação nativa no app + webhook fechando o loop.
5. **Ritual de migration** — drift-check → snapshot rotulado → staging → migration aditiva com backfill=CNPJ1 → blue-green.
6. **Operacional intocado** — postos/alocações/escalas/presença não ganham dimensão de empresa (são agnósticos; curadoria manual do Jordan preservada).
7. **Prioridade é lei** — P0 fecha antes de P1, que fecha antes de P2; cada item adiável tem modo-manual documentado.

## 3. Escopo

### DENTRO
- **Fundação**: cadastro completo do CNPJ2 na tabela `empresas` (que já existe com os 2 registros); 2º certificado A1 no `CertificateStore`; reconciliação `tenants`×`empresas`; reconciliação `.env` raiz × backend; helper único de empresa.
- **Contratos**: `empresa_id` em `contracts` (backfill CNPJ1); classificação canônica dos 10 condomínios (tabela §1); migrador consertado (UUID, persiste, grava aditivo tipo "transferência de titularidade"); geração dos aditivos.
- **Identidade documental**: `pdf_branding` paramétrico por empresa **e por competência**; 28 geradores corrigidos pela fonte única; fronteira histórica (definida pela resposta da Portte) em config versionada.
- **Trabalhista (espelhamento)**: `empresa_id` em `employees`/`hr_payslips` com datas oficiais da Portte; eventos SST (que seguem sendo nossos) transmitidos pelo empregador vigente com o certificado da empresa; holerite/espelho com empregador por competência.
- **Fiscal**: emissão NFS-e por empresa (config da tabela `empresas`; regime/ISS derivados, sem defaults); `empresa_context` por `empresa_id`; NSU DFe por empresa; `empresa_id` em `nfse`/`nfe`; importação das NFS-e já emitidas pela Patrimonial; matriz de obrigações × regime explícita.
- **Bancário**: integração **Cora** (OAuth2+mTLS, saldo, extrato + carga retroativa, boleto/PIX-cobrança, DARF/GPS, webhooks, sandbox stage); partição por conta de tabelas, tetos, caches e conciliação; roteamento por empresa dona; correção dos pontos de cobrança com Inter/CNPJ1 chumbado (régua IA, kit de fatura, telas); portal do cliente exibindo cobranças de ambos os bancos.
- **GED/GEDEON (P1 — kit de 28/07!)**: certidões por CNPJ (2 conjuntos, sync em loop); kit híbrido com resolução POR DOCUMENTO/competência; classificador reconhecendo as 2 matrizes; segregação no Drive; comprovantes com banco/empresa corretos.
- **Frontend/consultores (P2)**: filtro/seletor de empresa; 7 telas com CNPJ chumbado; bloco `estrutura_grupo()` nos 8 consultores + rótulo "Grupo consolidado"; ~40 tools MCP com parâmetro empresa.
- **Rede de proteção**: parametrização das 22 fixtures (viram gate diff-zero); testes novos (kit híbrido, roteamento bancário, identidade por competência); guard-lint anti-CNPJ-hardcode; specs Playwright multi-CNPJ.
- **WS9 — Capacidade de folha orgânica (pós-virada, ago→out)**: motor próprio em paralelo, conciliado 100% contra a Portte; ponte folha→S-1200 + tabelas S-1005/1010/1020; médias de variáveis, afastamentos, pensão-IRRF; guias integradas. **Oficializa só quando o Jordan declarar o ponto de confiança.**

### FORA (explícito)
- Eliminar a Portte (NUNCA — papel evolui para consultoria/validação, permanência garantida).
- Multi-tenancy total (empresa_id em todas as ~91 tabelas) e segunda instância do sistema.
- NF-e de produto para a Patrimonial (não emite; CNPJ1 também nunca emitiu).
- SPED/EFD-Reinf para o CNPJ2 (Simples → DAS/PGDAS).
- Transmissão de sucessão eSocial pelo sistema (executada pela Portte).
- Mudanças no núcleo operacional (postos/alocações/escalas/ponto).
- Polo passivo de processos e titularidade de atestados de licitação — adiados com gatilho definido (1º processo citando CNPJ2 / 1ª licitação de mão de obra pelo CNPJ2).

## 4. Requisitos funcionais (com critério de aceite/oráculo)

| ID | Requisito | Critério de aceite (oráculo externo) |
|---|---|---|
| RF-01 | Cadastro CNPJ2 completo em `empresas` | SELECT mostra CNPJ, IM, cert path/senha, regime, anexo; cert carrega e assina XML de teste |
| RF-02 | Todo contrato ativo tem `empresa_id` conforme tabela canônica §1 | Query de conferência 10/10 condomínios; aditivo PDF com as duas razões corretas |
| RF-03 | Documento resolve emitente por competência+vínculo | Holerite 06/2026 re-renderiza byte-idêntico (CNPJ1); holerite 07/2026 pós-fronteira sai CNPJ2 |
| RF-04 | Funcionários espelham datas oficiais da Portte | Conciliação CPF×empregador×data = 100% contra planilha/retorno Portte |
| RF-05 | SST transmite pelo empregador vigente com cert da empresa | Evento de teste em produção-restrita aceito com empregador CNPJ2; trava bloqueia empregador≠vínculo |
| RF-06 | NFS-e emitida pela empresa do contrato, regime correto | XML CNPJ1 diff-zero; 1ª nota CNPJ2 idêntica campo-a-campo à emitida manualmente (Mirante) |
| RF-07 | NFS-e já emitidas da Patrimonial importadas | Notas do Mirante visíveis no sistema com prestador CNPJ2 |
| RF-08 | Integração Cora: saldo/extrato/cobrança/webhook + carga retroativa | Saldo exibido == API; extrato desde a abertura da conta; cobrança de R$0,01 emitida e conciliada via webhook |
| RF-09 | Saída de dinheiro roteada por empresa; tetos/caches por conta | Pagamento-teste Patrimonial inicia no Cora (aprovação no app) e NUNCA aparece em `inter_payments`; teto exibido por conta |
| RF-10 | Cobrança ao condomínio com banco/CNPJ da empresa do contrato | E2E: 10 faturas (uma por condomínio) exibem o recebedor correto |
| RF-11 | Certidões por CNPJ, painel com os 2 conjuntos | CND/CRF/CNDT das duas empresas com status independente; "aguardando dado" onde faltar |
| RF-12 | Kit híbrido: cada doc resolve empresa por competência/natureza | Kit de teste do Ideal Flores (comp. 07) contém NFS-e Patrimonial + guias retroativas Eletrônica + CNDs dos 2 |
| RF-13 | Portal cliente/funcionário íntegros | Boletos de ambos os bancos visíveis; telas históricas inalteradas (Playwright) |
| RF-14 | Consultores honestos | Pergunta "saldo da Patrimonial?" → responde com dado real ou "aguardando integração", nunca inventa |
| RF-15 | DRE/fluxo por empresa + consolidado | Valor exibido == query por `empresa_id` e soma |
| RF-16 | (WS9) Motor de folha paralelo conciliado com a Portte | Relatório de convergência por rubrica/funcionário; meta 100% por 3 competências antes de qualquer oficialização |

## 5. Requisitos não-funcionais

- **RNF-01 Regressão zero**: suítes release (16 fin + 7 ged + 4 ponto) verdes após cada deploy; contagem de verdes nunca regride.
- **RNF-02 Zero-downtime**: todo deploy backend via blue-green; frontend via container :3001 com purge de estáticos.
- **RNF-03 Reversibilidade**: cada migration precedida de snapshot rotulado; rollback documentado por frente.
- **RNF-04 Auditabilidade**: mudanças de `empresa_id` em contratos/funcionários com trilha (quem/quando/base — e-mail Jordan ou retorno Portte).
- **RNF-05 Segurança**: nenhum segredo novo em código; credenciais Cora só em env/credentials com 0600; senha de cert nunca em default de código (corrigir a existente).
- **RNF-06 Coordenação**: território por módulo entre terminais t1/t2/t3; deploy só com working tree limpa da frente.

## 6. Métricas de sucesso

1. **31/07**: todos os RF-01→RF-15 com oráculo verde (RF-16 é trajetória WS9).
2. **Agosto**: primeira NFS-e automática da Patrimonial aceita; kit híbrido de julho entregue sem retrabalho; zero regressão reportada nos condomínios da Eletrônica; recebimentos Cora conciliados automaticamente.
3. **Set–Out**: kits convergindo para 100% Patrimonial; convergência folha motor×Portte medida mensalmente; dependência da Portte reduzida a validação (quando Jordan declarar).

## 7. Decisões registradas (log)

| Data | Decisão | Fonte |
|---|---|---|
| 17/07 | Segmentação permanente, 2 CNPJs para sempre | Jordan |
| 17/07 | Corte único; sistema pronto 31/07; competência de corte 07/2026 | Jordan + e-mail Portte |
| 17/07 | Banco CNPJ2 = Cora (Inter rejeitou conta nova) | Jordan |
| 17/07 | Portte permanente e inegociável; executa a transição trabalhista | Jordan |
| 17/07 | Todos os CLT → Patrimonial; Eletrônica só PJ | Jordan |
| 17/07 | Green Hills → Eletrônica (segurança eletrônica) | Jordan |
| 17/07 | Kits híbridos ago+set; 100% Patrimonial ~out | Jordan |
| 17/07 | Arquitetura: empresa como dimensão legal (não multi-tenant total) | Discussão aprovada |
| 17/07 | API Cora verificada: sem PIX-por-chave; aprovação no app; credencial autoatendimento | Pesquisa doc oficial |
