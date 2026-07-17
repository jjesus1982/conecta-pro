# PLANO MASTER — Grupo Conecta Mais Multi-CNPJ

**Data:** 2026-07-17 · **Go-live completo:** 31/07/2026 · **Evento jurídico/trabalhista:** 01/08/2026
**Status:** PLANO APROVADO EM DISCUSSÃO — nenhuma linha de código alterada até autorização de execução.

> Cada workstream (WS) abaixo ganha seu plano de implementação detalhado (TDD, tarefa a tarefa, em
> `docs/superpowers/plans/`) no kickoff da frente. Este documento é o mapa e o cronograma do programa.

---

## 1. Decisões fixadas (Jordan, 17/07)

1. **Segmentação PERMANENTE** — os dois CNPJs operam para sempre, simultaneamente:
   - **Conecta Mais Patrimonial (CNPJ2)**: terceirização de mão de obra (portaria humanizada, serviços). Simples Nacional, CNAE 8111-7/00. Banco **Cora**.
   - **Conectamais Eletrônica (CNPJ1)**: segurança eletrônica + **portaria remota**. Lucro Real (volta ao Simples em 01/2027 — já representável em `empresas.regime_futuro`). Banco **Inter** (inalterado).
2. **Todos os 56 funcionários CLT migram para a Patrimonial.** A Eletrônica mantém apenas PJ (fica sem vínculo CLT ativo após a sucessão).
3. **Contratos já são instrumentos separados** (mão de obra × eletrônica) — não há desmembramento, só transferência com aditivo.
4. **Corte único** na competência 01/08. **Tudo rodando, testado e sem erro até 31/07.**
5. Arquitetura: **empresa como dimensão legal** (`empresa_id` nas entidades com dono jurídico, backfill = CNPJ1, serviços parametrizados por empresa). NÃO é multi-tenant total, NÃO é segunda instância.
6. **E-mail formal à Portte enviado em 17/07** solicitando a migração de toda a folha/funcionários,
   "vigor imediato, visando fechamento de kits, emissões de notas e aditivos do mês de agosto
   RELATIVO A JULHO" → **a competência de corte efetiva tende a ser 07/2026** (documentos de julho,
   processados em agosto, já saem pela Patrimonial). **CONFIRMAR com a Portte a data exata da
   sucessão eSocial** (retroativa à competência 07?) — essa resposta fixa a data dos S-2299/S-2200.

### Fatos operacionais (Jordan, 17/07 — mudam o dimensionamento)
- **O CNPJ2 já opera**: NFS-e emitidas pela Patrimonial para o Mirante das Flores (fora do sistema) e
  **pagamento já recebido na conta Cora** — a conta está ativa. Consequências: (i) há dinheiro real no
  Cora invisível ao Conecta PRO até a WS5 entrar (regra da casa: exibir "aguardando dado", nunca
  fabricar); (ii) a WS4/WS5 incluem **importar as NFS-e já emitidas** do CNPJ2 (pull pela credencial
  própria) e o extrato Cora retroativo, para o histórico nascer completo.
- **A transição trabalhista (funcionários/folha/eSocial de sucessão) é executada pela PORTTE** — o
  Conecta PRO não transmite a sucessão; ele **reflete**: `empresa_id` nos funcionários conforme as
  datas da Portte, fronteira de competência do holerite, e eventos SST (S-2210/2220/2240) passando ao
  empregador CNPJ2 a partir da data que a Portte cravar. WS3 reescopada: espelhamento + SST + cálculo
  paralelo, sem transmissão de sucessão própria.
- **Kits híbridos em agosto e setembro**: por datas retroativas e CNDs do mês da competência, o
  GEDEON montará kits com documentos DAS DUAS empresas por ~2 meses; previsão de kit 100%
  Patrimonial só em ~outubro. Requisito de design (WS-GED): a composição resolve a empresa POR
  DOCUMENTO/COMPETÊNCIA — nunca um switch binário condomínio→empresa — e mantém os dois conjuntos de
  certidões disponíveis no período de transição.

### Segmentação canônica dos condomínios (e-mail Jordan 17/07 — seed do condominio→empresa)
| Empresa | Condomínios |
|---|---|
| **CNPJ2 Patrimonial** (mão de obra locada) | Villa dos Pássaros · Mirante das Flores · Ideal Flores · Laranjeiras Village · Michellangelo · Villa Dei Fiore · Prime Arena (+ futuros contratos de terceirização) |
| **CNPJ1 Eletrônica** (sem locação de mão de obra) | Parise Village · Residencial Gelain · Green Hills (+ futuros contratos de segurança eletrônica) |

## 2. Diagnóstico-base (QA de 17/07, 6 agentes, read-only)

Veredito: **"multi-tenant de fachada"** — o esqueleto multi-CNPJ existe (tabela `empresas` com os 2
registros, contabilidade por empresa, geradores eSocial paramétricos), mas nenhuma tabela central de
negócio tem `empresa_id`, e a identidade operacional (branding, fiscal, banco, folha) está travada no
CNPJ1 por env vars, constantes e hardcodes (~30 pontos).

Registro do CNPJ2 no banco: `empresas.id = 7d79ed12-d480-4906-b2e0-2b2c4d299bab` (`conecta_patrimonial`,
status `em_abertura`, **CNPJ ainda não preenchido**). CNPJ1: `619a3df1-8bce-49ce-b77a-04f80a0e8491`.

---

## 3. MAPA: aproveitar × adaptar × criar do zero

### 3.1 APROVEITAR DIRETO (já existe, praticamente pronto)

| Peça | Onde | Uso no programa |
|---|---|---|
| Tabela/módulo `empresas` (regime, anexo, liminares, cert A1 POR empresa, `regime_futuro`) | `backend/modules/empresas/` | Fonte única de identidade. Só completar cadastro do CNPJ2 |
| Contabilidade por empresa (`accounting_entries`, apuração LR, relatórios trimestrais) | `financial/services/ledger_auto_service.py`, `apuracao_lucro_real_service.py`, `relatorios_controller.py` | Já aceita `empresa_id`; comentário no código já cita o CNPJ2 |
| Geradores eSocial paramétricos (`empregador_cnpj` em S-2200/2230/2299/2220/2240; dataclass `Empregador` com `classTrib`) | `people_management/hr/services/esocial_service.py`, `government_integrations/core/esocial_manager.py` | Base da sucessão trabalhista |
| DCTFWeb por empresa (recebe objeto empresa) | `government_integrations/services/dctfweb_service.py` | Modelo a replicar nos demais serviços fiscais |
| `CertificateStore` multi-cert (chaveado por CNPJ) | `government_integrations/core/certificate_manager.py:495` | Carregar o 2º certificado — pronto, só ligar |
| Calculadora tributária dual (Simples×LR, `comparar_regimes`, liminares) | `financial/agents/tax_calculator.py` | Cálculo do CNPJ2 no Simples |
| `ContractMigratorAgent` + classificador serviço→empresa + gerador de aditivo de transferência | `empresas/agents/contract_migrator.py` | Motor da fase de contratos (após conserto) |
| Certidões de licitação por CNPJ | `bidding/schemas/certificate.py` | Certidões do CNPJ2 entram sem mudança |
| Modelo genérico `bank_accounts` (N contas, `integration_config` JSONB) | `financial/models/bank_account.py` | Registrar a conta Cora como conta de 1ª classe |
| Padrão adapter bancário (`BankCredentials`/`InterAdapter`) | `integrations/banking/adapters/inter.py` | Contrato que o `CoraAdapter` implementa |
| Gate OTP + auditoria de pagamento; padrão "pago pelo app + conciliação" | `integrations/inter/services/payment_service.py`; fluxo diaristas | Reuso no Cora (e fallback se API não pagar) |

### 3.2 ADAPTAR (existe, precisa parametrizar/ligar — o grosso do trabalho)

| Item | Hoje | Vira |
|---|---|---|
| `contracts`, `employees`, `hr_payslips`, `nfse`, `nfe`/`nfe_entradas`, `sped_files` | sem `empresa_id` | migration + backfill CNPJ1 + FK `empresas` |
| Tabelas `inter_*`, `inter_payments`/OTP/audit, `financial_beneficiarios`, `financial_fornecedores` | sem conta/empresa | coluna `bank_account_id`/`empresa_id` + partição |
| `pdf_branding.EMPRESA` (dict fixo → 28 geradores) | constante CNPJ1 | função `branding(empresa)`; documento pergunta ao contrato/funcionário quem assina |
| `empresa_context.get_empresa_fiscal()` | `LIMIT 1` + `lru_cache(1)` → só CNPJ1 | por `empresa_id` (SPED Fiscal/Contábil, DCTFWeb, EFD-Reinf) |
| Serviços NFS-e Manaus/Nacional | env single-value; `optante_simples=True` default; ISS 5% fixo | config lida da tabela `empresas` (core já recebe parâmetros); regime/alíquota da empresa |
| `esocial_controller` | `EMPRESA_CNPJ`/`EMPRESA_RAZAO` hardcoded | empregador vem do `employee.empresa_id` |
| Custo patronal | 28% fixo (Lucro Real) | por `regime_tributario` (Simples: patronal no DAS) |
| Teto diário R$100k, saldo mínimo, cache Redis (`inter:token`, `inter:saldo:cache`), OTP | globais de processo | particionados por conta/banco (namespace com sufixo) |
| Conciliação Inter | `bank_name ILIKE '%inter%' LIMIT 1` + `condominio_id` hardcoded | resolve `bank_account_id` real; loop por conta ativa |
| DRE clássico + fluxo de caixa | agregam tudo | filtro `empresa_id` + visão consolidada do Grupo |
| Migrador de contratos | id `int` (bug — contratos são UUID); não persiste (TODO) | UUID + `UPDATE contracts SET empresa_id` + grava `ContractAddendum` tipo novo `transferencia_titularidade` |
| Frontend | 7 telas com CNPJ1 chumbado; módulo `empresas` = calculadora hardcoded sem API | telas lendo da API; módulo empresas real |
| `financial_mcp_server.py:80` | CNPJ1 no payload | dado da empresa consultada |
| ~30 hardcodes CNPJ1 + `EMPRESA_PRINCIPAL_ID` triplicado | espalhados | helper único `empresas` (varredura com gate de lint) |
| Tabela `tenants` (legado 05/2026) paralela à `empresas` | duas fontes | unificar/aposentar (decisão na WS1) |

### 3.3 CRIAR DO ZERO

| Item | Tamanho | Observação |
|---|---|---|
| **`CoraAdapter`** (auth, saldo/extrato, cobrança boleto/PIX, comprovante, webhook se houver) | **GRANDE — única peça realmente nova** | Escopo real da API Cora a confirmar no credenciamento; fallback de pagamento = fila OTP + execução no app + conciliação |
| Sucessão trabalhista eSocial (S-2299 por transferência + S-2200 com `tpAdmissao=2`/`sucessaoVinc`) | Médio | Campos novos em geradores que já são paramétricos; validar com Portte |
| Checkpoint de NSU DistribuiçãoDFe por empresa | Pequeno | Tabelinha + leitura/gravação no sync |
| Seletor/filtro de empresa no frontend | Médio | Filtro de visão (não é tenancy de login) |
| Relatório consolidado do Grupo (2 empresas lado a lado + soma) | Pequeno/médio | Sobre a base contábil que já é por empresa |
| Scripts de virada + runbook (marcação de contratos em lote, batch sucessão, checklist D-day) | Pequeno | Executados no ensaio e no dia 31 |

---

## 4. WORKSTREAMS por prioridade e cronograma (18–31/07)

### P0 — sem isso não existe virada

**WS1 · Fundação da identidade (18–19/07)**
Completar cadastro do CNPJ2 em `empresas` (CNPJ, IM, cert A1 path+senha, ambiente NFS-e); carregar 2º
certificado no `CertificateStore`; decidir/aposentar `tenants`; helper único de empresa (mata
`EMPRESA_PRINCIPAL_ID` triplicado).
*Gate:* `SELECT` mostra as 2 empresas completas; os 2 certificados carregam e assinam um XML de teste.

**WS2 · Contratos + branding (19–22/07)**
`empresa_id` em `contracts` (backfill CNPJ1); migrador consertado (UUID, persiste, grava aditivo);
classificação dos contratos ativos (mão de obra → CNPJ2); geração dos aditivos p/ assinatura;
`pdf_branding` paramétrico.
*Gate:* todo contrato ativo tem empresa; aditivo PDF sai com as duas razões sociais corretas; contrato
da Eletrônica continua imprimindo CNPJ1 idêntico ao de hoje (regressão zero).

**WS3 · Folha + sucessão eSocial (20–26/07)** — a frente mais crítica
`empresa_id` em `employees`/`hr_payslips` (backfill CNPJ1); fluxo de sucessão (S-2299 CNPJ1 + S-2200
sucessão CNPJ2, lote dos 56); patronal por regime; holerite/recibos com empregador do funcionário;
ensaio completo em produção-restrita; validação Portte.
*Gate:* XMLs de sucessão aceitos em produção-restrita para os 56; folha simulada de agosto no Simples
bate com conferência da Portte; holerite de teste imprime CNPJ2.

### P1 — dinheiro entrando e saindo

**WS4 · Fiscal por empresa (22–27/07)**
`empresa_context` por empresa; serviços NFS-e lendo da tabela `empresas`; regime/ISS corretos;
`empresa_id` em `nfse`/`nfe` + NSU por empresa; emissão de homologação do CNPJ2 → produção.
*Gate:* NFS-e de homologação do CNPJ2 aceita pela prefeitura/ADN; emissão do CNPJ1 segue idêntica
(diff de XML antes/depois = zero).

**WS5 · Banco Cora + partição financeira (18/07 credenciamento externo; 21–29/07 código)**
Conta Cora em `bank_accounts`; `CoraAdapter`; recebimentos (boleto/PIX) do CNPJ2; partição de tabelas,
tetos, OTP, caches e conciliação por conta; roteamento CNPJ2→Cora / CNPJ1→Inter.
*Gate:* extrato real do Cora sincronizado no banco; cobrança de R$0,01 emitida e conciliada; pagamento
de R$0,01 com OTP (ou fallback app+conciliação provado); extrato Inter do CNPJ1 sem NENHUMA mudança.

### P2 — operação diária e visão do Grupo

**WS6 · Frontend (24–29/07):** seletor/filtro de empresa; 7 telas hardcoded corrigidas; módulo
`empresas` ligado à API. *Gate:* Playwright E2E pelo domínio público nas telas afetadas.

**WS7 · Relatórios do Grupo (26–29/07):** DRE/fluxo por empresa + consolidado.
*Gate:* oráculo veracidade — valor exibido == query no banco, por empresa e consolidado.

**WS8 · Higiene (contínuo, gate 29/07):** varredura dos ~30 hardcodes; MCP tool; guard-rail de lint
contra CNPJ chumbado novo.

### Fechamento

- **29–30/07 · ENSAIO GERAL:** virada completa em staging + produção-restrita; QA E2E por módulo
  (padrão veracity-sweep); correções.
- **31/07 · GO-LIVE:** deploy blue-green final; execução do runbook técnico; sistema 100% operando
  nos dois CNPJs.
- **01/08 · Evento jurídico:** vigência dos aditivos; transmissão da sucessão eSocial em produção;
  contratos humanizados ativos na Patrimonial.

## 4-B. MATRIZ de portais gov / robôs / bancos por CNPJ

Regra do desenho: **robôs e serviços são motores; identidade (cert+credencial+CNPJ) é parâmetro.**
Nenhum robô é clonado — cada um roda por empresa ativa que tenha aquela obrigação, resolvendo
certificado/credenciais pela tabela `empresas`. Três padrões: (1) duplicar identidade no mesmo motor;
(2) rotear pela empresa dona do contrato/vínculo; (3) obrigação não-aplicável fica explícita.

| Integração | CNPJ1 Eletrônica | CNPJ2 Patrimonial | Ação no sistema |
|---|---|---|---|
| eSocial SST/gov | Esvazia (sem CLT, só PJ) | Recebe tudo (sucessão + SST dos 56) | Transmissor resolve cert pela empresa do funcionário (geradores já paramétricos) |
| NFS-e Nacional/Manaus | Continua: monitoramento, portaria remota, eletrônica | Passa a emitir: mão de obra (Simples/Anexo III) | ÚNICO espelhamento real: 2 credenciais, 2 IMs, mesmo motor; pull por CNPJ |
| SEFAZ NF-e | Só entrada (DistribuiçãoDFe), como hoje | NÃO emite venda; pull de entrada opcional (P2) c/ NSU próprio | Checkpoint NSU por empresa quando ativar |
| e-CAC | DCTFWeb, Lucro Real | Caixa postal + DAS Simples | Robô em loop por empresa; exige procuração p/ CNPJ2 |
| DET/gov.br (robô) | Mantém monitoramento | 2ª identidade (e-CNPJ do CNPJ2); FGTS Digital dos 56 cai aqui | 2º cert no container do robô + 2ª rotina; alertas no mesmo sino |
| FGTS Digital | Zera pós-sucessão | Guias dos 56 | Consequência automática da sucessão eSocial |
| SUFRAMA | Mantém | N/A (serviços) | Nada |
| SPED/EFD-Reinf/LR | Mantém até 01/2027 | N/A (Simples→DAS/PGDAS) | `empresa_context` por empresa + matriz obrigação×regime explícita |
| Banco | Inter (INTOCADO) | Cora (adapter novo) | Roteamento por empresa dona do contrato; OTP/teto/conciliação por conta |
| Sólides/Tangerino | — | Segue funcionários (ponto segue a pessoa) | Código não muda; EXTERNO: atualizar cadastro da empresa na plataforma Sólides |
| Domínio/Portte | Transitório | Transitório | META: reduzir Portte a consultoria (WS9 — folha orgânica). Competências 08–09/2026: Portte permanece como rede de segurança da folha oficial enquanto o WS9 internaliza (ver 4-C) |
| Portal cliente/funcionário | — | — | Login/telas iguais; DOCUMENTOS imprimem a empresa do vínculo/contrato (branding paramétrico) |
| CRM/WhatsApp/licitações | Compartilhado (Grupo) | Compartilhado | Licitação escolhe proponente por edital; certidões já são por CNPJ |

## 4-C. QA PROFUNDA — RODADA 2 (17/07, 8 investigações, read-only)

### Achados que MUDAM o plano

**1. RISCO Nº1 — REESCRITA DO PASSADO (novo inegociável).** Holerite, espelho de ponto, kits e
comprovantes são **re-renderizados on-the-fly** a partir do dict de branding ATUAL — não há PDF
imutável nem identidade de empregador por competência (`payslip_pdf_service.py` recalcula a cada
request; `espelho_ponto_pdf.py:154-156`). Trocar o branding reescreveria holerites ≤07/2026 com
CNPJ2 (falso); não trocar deixa os novos com CNPJ1 (falso). **Regra da WS2: identidade do
emitente/empregador é resolvida POR COMPETÊNCIA/documento** (≤07/2026 → CNPJ1 sempre; ≥08/2026 →
empresa do vínculo/contrato). Gate: holerite de 06/2026 re-renderizado byte-a-byte igual ao de hoje.

**2. FOLHA ORGÂNICA (saída da Portte) É UM PROGRAMA PRÓPRIO — WS9, pós-virada.** Raio-X de prontidão:
cálculo **6/10** (motor mensal forte: piso CCT, adicionais por pessoa, DSR, INSS/IRRF/FGTS de ponto
real; rescisão completa em `clt_calculator.py`), eSocial-folha **2/10** (S-1200 esqueleto sem
dmDev/rubricas nas 3 stacks; S-1210/S-1299 vazios; sem S-1005/S-1010/S-1020; transmissão simulada;
zero ponte folha→evento), guias **3/10**. O transporte gov (SOAP/mTLS/assinatura A1,
`esocial_transmitter.py`) é REAL — falta o conteúdo. **Decisão de engenharia: NÃO internalizar a
folha oficial na mesma data da virada.** REGRA DO PROJETO (Jordan, 17/07): **a Portte é PERMANENTE e
inegociável** — o objetivo é reduzir DEPENDÊNCIA, não eliminá-la. O modelo atual com a Portte é
mantido até haver segurança comprovada de que todo o processo roda pelo Conecta PRO (quem declara
esse ponto é o Jordan); a partir daí a Portte atua como consultoria/validação permanente.
WS9 (ago–out) constrói a CAPACIDADE interna: ponte folha→S-1200, S-1005/1010/1020, S-1210/1299
reais, médias de variáveis em férias/13º/rescisão, afastamentos INSS na folha, pensão na base IRRF,
ciclos de férias/13º, Fator R alimentado pela folha, DAS/DCTFWeb/FGTS Digital integrados —
automatizado com skills+agentes, sempre em paralelo com a Portte e conciliado 100% contra ela.

**3. Certidões por CNPJ (risco jurídico alto).** `ged_certidoes` não tem coluna de CNPJ; um "FGTS
regular" verde do CNPJ1 mascararia irregularidade do CNPJ2 (o empregador real). Entra na WS-GED:
coluna cnpj + sync CND/CRF/CNDT em loop pelas 2 empresas (`cnd_sync_task`, `cnd_watcher`), kit
escolhe o conjunto pelo CNPJ do condomínio. Padrão a copiar: `bidding/schemas/certificate.py` (já
tem cnpj).

**4. Kits GEDEON**: escopo `empresa_matriz` = CNPJ1 fixo (`kit_builder_service.py:252-270`); âncora
natural = condomínio→empresa; classificador `is_matriz` só reconhece CNPJ1 (regex); Drive com raiz
única precisa de nível por empresa; comprovantes assumem "tudo sai pelo Inter".

**5. Diaristas/VT-VR e cobrança recorrente**: `executar_lote` instancia `InterAdapter` hardcoded
(`pagamentos_diaristas_service.py:508-516`); `recurring_billing_service.py:37-48` idem; portal do
cliente lê boletos SÓ de `inter_cobrancas` (cobranças Cora ficariam invisíveis ao condomínio);
`collection_negotiator.py:93` tem a chave PIX do Inter chumbada no prompt da régua de cobrança.
Custos/pricing de posto: `ENCARGOS_PCT=0.6124` (premissa Lucro Real) duplicada em
`precificacao_controller.py:22` e `custeio_controller.py:22` — recalcular para o regime do CNPJ2.

**6. Consultores IA**: 5 de 8 (CFO/CEO/CMO/CHRO/Fiscal) agregam global e responderiam
misturado/errado; CHRO se apresenta como "Eletrônica" (folha será da Patrimonial); jurídico é o único
já multi-CNPJ (`context_engine.panorama_empresa` lê da tabela `empresas`) = modelo a copiar. Padrão
mínimo: bloco único `estrutura_grupo()` injetado nos 8 + rótulo honesto "Grupo (consolidado)" até a
segmentação real. MCP: tools `*_grupo` e `listar_empresas` já existem; ~40 tools financeiras/folha/
fiscal/banco precisam de parâmetro `empresa` (P2); `financial_mcp_server.py` é single-CNPJ inteiro.

**7. Infra**: ~15 celery beats precisam de loop por empresa (extrato, NFS-e entrada/nacional, eSocial
espelho/recibos, CNDs, certificados); operacional/Sólides/CRM = por condomínio, não afetados;
`conecta-pro-det-robot` monta 1 .pfx (2ª identidade); webhook Inter single-tenant (Cora terá o
próprio); **camada HTTP `nfse_multi` JÁ multi-empresa registrada em produção** — as tasks é que
precisam consumi-la; GOTCHA: `.env` raiz e `backend/.env` divergem (INTER_CERT/KEY só no backend/) —
alinhar os dois ao criar `CORA_*`/cert2; limite gov de 10 acessos/dia eSocial é POR CNPJ (dobra o
orçamento de pull).

**8. Rede de proteção (boa notícia)**: staging completo isolado (`docker-compose.staging.yml`);
blue/green sólido; backup diário íntegro (03:00); Alembic 1 head em sync; specs Playwright multi-CNPJ
de scaffold já criados (`empresas-multi-cnpj.spec.ts` etc.); molde de guard-lint pronto
(`test_money_guardrail.py`) para o guard anti-CNPJ-hardcoded. Lacunas a criar: teste de sucessão
eSocial (hoje ZERO), NFS-e multi-empresa (22 fixtures travam CNPJ1 — parametrizar mantendo gate
diff-zero do CNPJ1), conciliação por conta. Antes de QUALQUER migration: detecção de schema drift
(houve DDL ad-hoc no operacional) + snapshot rotulado do banco.

**9. Jurídico (pode esperar, monitorar)**: processos sem polo passivo modelado (urgente só no 1º
processo citando CNPJ2); atestados de licitação sem titularidade (urgente na 1ª licitação de mão de
obra pelo CNPJ2 — risco de falso positivo de habilitação usando acervo do CNPJ1); Central de
Contratos soma carteiras sem segmentar (filtro incremental).

### WS9 · Folha Orgânica (programa pós-virada, ago–out/2026)
Fases: (i) ago — competência 08 calculada em paralelo (motor próprio × Portte, conciliação 100%);
médias de variáveis, afastamentos, pensão-IRRF, IRRF certificado; (ii) set — S-1005/1010/1020 do
CNPJ2 + ponte folha→S-1200/S-1210/S-1299 em produção-restrita, paralelo com Portte; (iii) out —
transmissão própria em produção + DAS (Fator R da folha) + FGTS Digital + DCTFWeb, SEMPRE conciliado
100% contra a Portte. A transição da Portte para o papel de consultoria só ocorre quando o Jordan
declarar o ponto de confiança — o paralelo dura o quanto for preciso. Investimento em skills/agentes:
skill "fechar-folha-mensal", agente conferidor (oráculo: XML aceito pelo gov + guia bate com
cálculo + bate com a Portte), skill "obrigações-do-mês" por empresa.

## 5. Dependências EXTERNAS (caminho crítico do Jordan — iniciar 17–18/07)

1. **Credenciamento API do Banco Cora** (credenciais de integração/certificado) — maior lead time
   externo; sem isso a WS5 opera em mock até chegar.
2. **Assinatura dos aditivos** pelos condomínios até 30/07.
3. **Portte:** avisar da sucessão 01/08; definir `classTrib` do Simples; conferência da folha de agosto.
4. **Contador:** enquadramento do CNPJ2, DAS, liminares PIS/COFINS (podem entrar depois — tabela
   `liminares` já suporta).
5. **Acessos gov do CNPJ2:** gov.br PJ, procurações eSocial/e-CAC, credencial NFS-e Nacional/Manaus.
6. Certificado A1 do CNPJ2 em mãos (OK — confirmado 17/07).
7. **Sólides/Tangerino:** atualizar/verificar o cadastro da empresa empregadora na plataforma
   (funcionários migram de empregador em 01/08 — confirmar com o suporte deles como refletir isso).
8. **Domínio/Portte:** confirmar cadastro do CNPJ2 no Domínio e a partir de qual competência a folha
   exporta pelo novo CNPJ.

## 6. Riscos e mitigações

| Risco | Prob. | Mitigação |
|---|---|---|
| ~~API Cora desconhecida~~ **VERIFICADA 17/07 (doc oficial): paridade 5,5/8.** TEM saldo/extrato/boleto+PIX-cobrança/DARF-GPS/webhooks/sandbox; credenciamento é AUTOATENDIMENTO no app (lead time ~zero). **NÃO tem envio de PIX por chave/copia-e-cola** (transferência só por dados bancários) nem comprovante via API; **toda saída exige aprovação no app Cora** | — | WS5 redesenhada: recebimento 100% via API; saída = iniciar por API + aprovação no app (o gate humano vira o app Cora, webhook fecha o loop); folha/diaristas = transferência com dados bancários na agenda OU padrão "pago pelo app"+conciliação; comprovante = gerado por nós do webhook+extrato. Bônus a avaliar: API NFS-e do Cora |
| Erro na sucessão eSocial (duplicidade de vínculo) | Média | Produção-restrita primeiro; validação Portte; transmitir produção só em 01/08 |
| Credencial NFS-e do CNPJ2 não sair a tempo | Média | Homologação desde a WS4; escalar com contador/prefeitura na semana 1 |
| Regressão no CNPJ1 (que segue operando!) | Média | Backfill = CNPJ1 em toda migration (zero mudança até a virada); gates de regressão em todo WS; deploy blue-green |
| Prazo (14 dias, 8 frentes) | Alta | Paralelismo agressivo de agentes por WS; WS0–WS3 primeiro (P0); P2 pode degradar para 01–05/08 sem quebrar a virada — decisão consciente se necessário |

## 7. Princípios de execução (inegociáveis do projeto)

- Backend baked: deploy só via `scripts/deploy_backend_bluegreen.sh`; frontend via container :3001.
- Operacional (postos/alocações) READ-ONLY; divergência = relatório para o Jordan.
- Nunca fabricar dado; oráculo = valor exibido == fato no banco; vazio-real = "aguardando dado".
- Dinheiro que sai = gate OTP humano, sempre — inclusive no Cora.
- eSocial produção só com aval Jordan+Portte; até lá, produção-restrita.
- Verificar pela rota da TELA (payload do form, máscara incluída).
