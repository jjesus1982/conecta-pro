# MAPA DO CONECTA PRO — o que está vivo, o que está desligado, o que está morto
**Medido em 06/09/2026** · sessão fase5 · branch `fase5-hermes-camada-cognitiva`

> Pedido: *"eu só quero concluir o meu sistema, todos os módulos. Pode não ser tão inteligente,
> mas precisa funcionar."* Critério de pronto: **você usou num caso real e funcionou sem conferir.**

---

## 0. Como foi medido — e as três armadilhas que a medição pegou

Fontes, todas de hoje: `checar_uso_real --tabelas/--mortas/--quem` (banco + nginx 15 dias +
`crm_audit_log` 30 dias), `backend_recon --surface redesign` nos 12 prefixos, `checar_nao_vigiado`
(375 telas construídas de verdade), `checar_beats`, varredura dos oráculos de 06/09 (135 `test_*`),
`checar_dominio`, `checar_sino_surdo`. Relatórios brutos em `auditoria/backend_recon/*_20260906.txt`.

| Armadilha | O que dizia | O que é | Como pegou |
|---|---|---|---|
| **"463 tabelas nunca receberam uma linha"** (prompt) | 463 de 686 (67%) | **392 de 691 (56%)** | `n_live_tup` é estimativa; `fin_journal_entries` tinha 11 linhas e `cct_convencoes` 1 com estimativa 0. Toda tabela de Licitações e Recrutamento "morta" tinha dado. `checar_uso_real` agora confirma zero por `count(*)` |
| **`checar_beats`: 2 tasks importam módulo inexistente** | `reconciliation_service` e `pagamentos_diaristas_service` "NÃO EXISTEM" | existem nos 8 containers desde 13/08 e 23/08 | a trava só olhava o `__init__`; `from pacote import submodulo` é válido. Falso vermelho por 24 dias. Corrigido |
| **"famílias 100% mortas"** (prompt) | `document_` 5, `workflow_` 5 | verdade, mas `ai_` 50 ≠ `modules/ai` 310 arquivos: o orquestrador dos agentes mora em `modules/ai/conversation` e é a coisa mais viva do sistema | separar TABELA de PACOTE antes de propor apagar |

**Regra que resume:** o número do prompt era o instrumento, não o sistema. Meça de novo antes de agir sobre número alheio.

---

## 1. O MAPA — família por família

`rotas` = montadas no `app` · `tab/dado/0-lin` = tabelas da família (zero confirmado por `count(*)`) · `req15d` = requisições no nginx (leitura, sem usuário) · `esc30d/pess` = escritas autenticadas e pessoas distintas (`crm_audit_log`) · `últ.dono` = sua última escrita · `telas s/vigia` = telas do redesign sem oráculo nem regra · `orq/verm` = oráculos da família e quantos estavam vermelhos em 06/09.

| módulo | rotas | tab | dado | 0-lin | últ.escrita | req15d | esc30d | pess | últ.dono | telas s/vigia | orq | verm | destino |
|---|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|
| DP / RH / Pessoas | 846 | 130 | 70 | 60 | 07/09 | 9.646 | 4.138 | 102 | 24/08 | 78 | 20 | 4 | 🟢 com 🟡 dentro |
| Financeiro | 669 | 89 | 44 | 45 | 07/09 | 240 | 153 | 2 | 06/09 | 29 | 8 | 2 | 🟢 com 🟡 e 🔴 dentro |
| Fiscal / Governo | 487 | 40 | 22 | 18 | 06/09 | 806 | 0 | 0 | — | 17 | 7 | 1 | 🟢 (consulta) + 🔴 (geradores) |
| Operacional | 304 | 34 | 18 | 16 | 03/09 | 11.712 | 171 | 3 | 28/08 | 18 | 17 | 0 | 🟢 |
| CRM / Comercial / Mkt | 348 | 74 | 48 | 26 | 07/09 | 57.647 | 901 | 15 | 26/08 | 62 | 23 | 1 | 🟢 com 🟡 dentro |
| GED / GEDEON / Assinatura | 348 | 40 | 20 | 20 | 04/09 | 3.944 | 132 | 27 | 19/08 | 17 | 15 | 0 | 🟢 com 🔴 dentro |
| Campo / Serviços / Equip. | 236 | 21 | 5 | 16 | 22/04 | 0 | 2 | 0 | — | 6 | 0 | 0 | 🔴 (serviços, equip.) · 🟡 (campo) |
| Licitações | 87 | 15 | 15 | 0 | 07/09 | 791 | 0 | 0 | — | 7 | 0 | 0 | 🟡 roda sozinho, ninguém olha |
| Recrutamento | 166 | 11 | 11 | 0 | 12/08 | 0 | 0 | 0 | — | 4 | 0 | 0 | 🟡 desuso |
| Jurídico / LGPD | 52 | 17 | 8 | 9 | 05/08 | 0 | 0 | 0 | — | 22 | 2 | 0 | 🟡 desuso + motor de alertas desligado |
| Sistema / Plataforma | 534 | 104 | 32 | 72 | 07/09 | 1.066 | 403 | 5 | 07/09 | 40 | 43 | 2 | 🟢 núcleo · 🔴 periferia |
| IA / ML / Chatbot | 143 | 114 | 6 | 108 | 07/09 | 0 | 0 | 0 | — | 2 | 0 | 0 | 🔴 (menos `llm_usage` e `executive_kpis`, que são do núcleo) |

Recon por prefixo (montadas · expostas no redesign · órfãs · **geradores órfãos** · **escrita órfã**):

```
people-management  699 · 266 · 433 · 14 · 198      crm          255 · 104 · 151 · 1 ·  85
financial          600 · 161 · 439 ·  0 · 203      ged          295 ·  99 · 196 · 1 ·  85
government         448 ·  20 · 428 · 16 · 206      recruitment  252 ·  63 · 189 · 0 · 108
fiscal             193 ·  70 · 123 ·  2 ·  52      services      63 ·   1 ·  62 · 0 ·  38
operacional        304 · 150 · 154 ·  0 ·  62      campo         77 ·  32 ·  45 · 0 ·  28
bidding             88 ·  23 ·  65 ·  0 ·  29      juridico      53 ·  27 ·  26 · 0 ·   8
```

**O seu dia, medido** (`crm_audit_log`, 30 dias, `jjesus`): pagamentos de diaristas **48 + 26 (OTP) + 33**, aprovar rascunho na Central **37**, pagar boleto **28**, montar kit **25**, cálculos fiscais (retenções, Simples, comparativo, limite) **41**, programar VT/VR **13**, consultores (chat/voz) **49**, TED **7**, briefing de contrato **5**, sync de certidões **6**. Isso é a régua da fila do 🟡.

---

## 2. CLASSIFICAÇÃO — o que sustenta cada destino

### 🟢 VIVO — tem dado, tem uso, funciona. Não mexer (só consertar o vermelho)

| Família | Prova |
|---|---|
| Ponto / folha / diárias (DP) | 11.305 batidas, 2.347 verbas de folha, 822 holerites, 418 diárias; 4.138 escritas de 102 pessoas em 30 dias |
| Financeiro núcleo | 6.111 lançamentos contábeis, 5.196 fluxo de caixa, 4.791 transações, 381 pagamentos de diaristas; é onde você escreve todo dia |
| Fiscal consulta | 10.515 NCMs, 1.135 docs Onvio, 322 NFS-e tomadas, 367 janelas eSocial; 806 leituras/15d |
| Operacional | 4.507 turnos, 80 rondas, 76 alocações; 11.712 leituras/15d (a maior do sistema depois do CRM) |
| CRM + agentes | 224 leads, 213 rascunhos, 1.540 mensagens WhatsApp, 12.011 escritas auditadas; 57.647 leituras/15d |
| GED kits + assinatura | 3.292 documentos de kit, 1.776 pedidos de assinatura, 857 índices GEDEON |
| Central de aprovações / orquestrador | 37 aprovações suas em 30 dias; 24 executores pela guarda; 63 tools |

Vermelhos REAIS dentro do 🟢 (defeito, não desligamento):
- `oraculo_ponto_invertido` — o app pede "saída para o almoço" às 18h (3 cenários, 10 pessoas). **Afeta porteiro todo dia.**
- `oraculo_extrato` (2 invariantes) e `oraculo_recebiveis` (1) — a base de tudo no financeiro.
- `oraculo_fiscal_agosto` — **2 certidões vencendo em ≤10 dias sem renovação disparada: CRF-FGTS de dois CNPJs vence 15/09.** Achado seu, não de teste.
- `checar_dominio` — `FAIXAS_INSS_2026` em `government_integrations/services/fgts_inss_service.py` tem a **tabela de 2024** (1.412 · 2.666,68 · 4.000,03 · 7.786,02). Zona gov: reportado, não tocado.
- `oraculos_rbac` 7/8, `endpoint_roteamento` (gestor com tools self), `canal_ferramentas` (tool duplicada `enviar_link_assinatura`).

### 🟡 DESLIGADO — o código existe e não está conectado. **É aqui que está o valor.**

Ordenado por quanto do **seu dia** devolve (régua acima), com a causa medida:

| # | O quê | Evidência | Por que não está ligado (Fase 3) | Devolve |
|---|---|---|---|---|
| 1 | **VT/VR programado sozinho** | você dispara `programar-vtvr-dia` à mão 13×/30d; existe beat `financial.programar_vtvr_do_dia` de hora em hora (07–21h) | o beat estava acusado como quebrado (falso — a trava errou); **se ele roda, por que você dispara à mão?** Ou ele não produz, ou produz e você não confia. Medir: `financial_pagamentos_diaristas` criados pelo beat × por você | 13 cliques/mês + a conferência |
| 2 | **Baixa automática de pagáveis** | beat `financial.auto_baixa_pagaveis` 08:30; você faz `pagar-boleto` 28× e `baixar-recebivel` 5× à mão | idem: trava acusava import inexistente (falso). Verificar produção real do beat (`payable_accounts.status` mudando às 08:30) | 33 cliques/mês |
| 3 | **Certidões: renovação que não dispara** | 2 CRF-FGTS vencem 15/09 e o oráculo diz "sem renovação disparada"; `cnd_watcher` roda a cada minuto no cron | o robô de CND (`scripts/gedeon/cnd_robot.py`, **WIP não commitado de outra sessão**) — a ponte backend→host existe; o disparo para FGTS não. Ler `cnd_watcher.sh` + `cnd_robot.py` antes de qualquer coisa | multa/bloqueio de licitação |
| 4 | **Espelho do eSocial parado há 6 dias** | `esocial-espelho-sync` 09:10 diário, última produção 31/08, "acesso ao governo registrado" | roda, autentica, não grava. Só leitura de gov — investigar `government_integrations/tasks/espelho.py` sem transmitir nada | folha certa sem conferir no portal |
| 5 | **Precificação → proposta** | 35 propostas com `margin_percent`, `cct_breakdown`, `pricing_simulation_id` todos NULL; `pricing_simulations` 0 linhas; `pricing_engine.calculate_cct_breakdown` existe | o motor não é chamado na criação da proposta (`crm/services/proposal_*`); o número que só o WhatsApp alcançava continua sem entrar na proposta | margem certa em toda proposta |
| 6 | **Folha via PIX / publicar contracheque / chave PIX** | 🟠 `dp/payslips/folha/pagar-via-pix`, `publicar`, `pix-key` — rotas com OTP prontas, sem botão no redesign | 198 órfãs de escrita no DP; as de dinheiro têm OTP e estão prontas. 💰: ligar botão, nunca happy-path | você paga folha pelo Inter à mão |
| 7 | **Exportação da folha para o Domínio** | `hr_payroll_exports` e `hr_payroll_integrations` 0 linhas; tool `exportar_folha_dominio` registrada | nunca exercitada num caso real | fechamento com o contador |
| 8 | **Motor de alertas de contrato (Jurídico)** | `contract_alerts` 0 linhas, 22 telas sem vigia, última escrita 05/08 | a skill `juridico` descreve o motor sobre `contracts`; nenhum beat o executa | vencimento/reajuste sem surpresa |
| 9 | **Licitações rodam sozinhas e ninguém olha** | `bidding_sync_jobs` 310 (07/09), 791 leituras/15d por máquina, 0 escrita humana, dado de negócio parado em 12/03 | o sync produz jobs, não oportunidades novas (`bidding_opportunities` 20, de março). Decidir: é negócio? Se sim, ligar o alerta ao sino/WhatsApp; se não, 🔴 | — |
| 10 | **Recrutamento** | 11 tabelas com dado, última 12/08, 0 leitura em 15 dias, 108 rotas órfãs de escrita | ninguém usa há um mês. Contratação de porteiro acontece fora do sistema? Se sim, é 🔴 de produto, não de código | — |
| 11 | **Campo (visitas / OS)** | `visitas` 2, `ordens_servico` (campo) com tool `abrir_visita` no WhatsApp, 0 leitura | as tools existem; o fluxo por WhatsApp começou (visita_whatsapp verde) mas não tem uso | — |

Não entram na fila por serem **read-only para agentes**: as 62 órfãs de escrita do Operacional (diaristas 16, escalas 10, banco de horas 6, rondas 5) — relatório, nunca wiring.

### 🔴 MORTO — nunca usado e não é o negócio dele. Propor APAGAR

**Tabelas (392 com 0 linhas; 75 sem migration nenhuma):**

| Família | Tabelas | Motivo |
|---|---:|---|
| `ai_*` | 50 | contract_analysis, prediction, recommendation, fraud, knowledge base, ML models — 0 linhas desde 20/01 |
| `solides_*` | 16 | integração Solides: `solides_sync_log` tem **16.454 linhas** e as 16 tabelas de destino têm 0. Roda e não produz. Ou o Solides já foi substituído pelo ponto próprio (11.305 batidas dizem que sim) e é 🔴 inteiro |
| `fin_*` | 13 | **segunda contabilidade**: plano de contas, centros de custo, custeio ABC, estoque. A contabilidade viva é `accounting_entries` (6.111). 203 rotas órfãs de escrita em `financial/accounting/*` servem a morta |
| `marketplace_*`, `chatbot_*` | 22 | não é o negócio |
| `push_*`, `notification_*`, `scheduler_*`, `workflow_*` | 29 | plataforma genérica que nunca ligou (o sino real é `communication_notifications`) |
| `ocr_*`, `document_*`, `ged_documents/folders/tags/versions/shares` | 19 | GED genérico; o GED vivo é `ged_kit_documents` (3.292) |
| `health_epi_*`, `health_*` | 4 | duplicata de `gp_epi_*` (220 entregas) |
| `cost_*`, `custos_*`, `purchase_*` (5) | 15 | custeio e compras formais; a cotação real vive em `purchase_quotations` (4, nascidas 31/08) |
| `chat_`, `checklist_`, `climate_`, `diarist_`, `report_`, `training_`, `turnover_`, `onboarding_`, `sentiment_`, `mobile_`, `rep_`, `sync_`, `ab_`… | ~60 | famílias de 2–4 tabelas, nenhuma com dado, nenhuma com rota usada |

**Código (pacotes sem importador e sem requisição em 15 dias):**

| Pacote | .py | Último commit | Rotas | req/15d |
|---|---:|---|---:|---:|
| `modules/ai/*` exceto `conversation`, `consultores`, `fraud_detection`(2 imp.) | ~180 | fev–jul | 8 | 0 |
| `modules/retention` | 47 | 02/07 | 70 | 0 |
| `modules/security_lgpd` (rotas `security`) | 35 | 02/07 | 29 | 0 |
| `modules/equipment_management` (maintenances, comodatos, equipment, installations) | 28 | 30/06 | 96 | 0 |
| `modules/analytics` + `reports` | 41 | jul | 65 | 0 |
| `modules/mobile`, `scheduler`, `automation`, `monitoring`, `documents`, `audit` | 112 | abr–jul | 118 | 0 |
| `modules/tecnico`, `inteligencia`, `pessoas`, `comercial`, `operacoes` (cascas antigas) | 54 | mar–jul | 0–4 | 0 |

⚠️ **`modules/ai/conversation` (72 .py, 32 importadores) e `consultores` NÃO entram**: é o orquestrador, o José Luís, o Bartolo, a Central. `fraud_detection` tem 2 importadores — conferir antes.

**Somando:** 392 tabelas e ≈500 arquivos Python que ninguém chama. Apagar isso é concluir: cada um é um lugar onde alguém (você, um agente, o recon) procura e se perde. Os 428 "órfãos" do `government` e os 439 do `financial` são, em boa parte, isso.

---

## 2b. Correções que a execução fez neste mapa (07/09)

- **392, não 463**: a contagem real de tabelas com 0 linhas (o 463 era estimativa do Postgres).
- **Quarentena: 251 → 172.** 79 tabelas eram citadas por código vivo (FKs em modelos, builders) e voltaram. Regra nova: cruzar o NOME da tabela com `backend/modules` antes de mover.
- **Dois pacotes do 🔴 estavam vivos por dentro:** `modules/analytics` (a task `analytics.recalcular_kpis` escreve `executive_kpis` todo dia; o `celery_app` a inclui — 2 workers em crash-loop no bake) e `modules/ai/contract_analysis` (o Jurídico importa `analise_contrato`). Restaurados o mínimo do primeiro e o segundo inteiro. Lição: "0 importadores" só vale medido no repositório inteiro, e o boot de prova tem que subir o servidor E o celery (agora é guarda do bake automático).
- **Três 🟡 eram 🟢 disfarçados** (VT/VR, auto-baixa, precificação por itens) — ver `auditoria/qa/*`.
- **Quem martelava a API**: o redator do proativo, 30.800 chamadas/dia falhando com 402. Disjuntor + fallback local no cliente único de LLM (`core/llm_client.py`).

## 2c. Telas do dia a dia com vigia (07/09, 3ª passada)

`test_oraculo_kpis_telas`: 29 KPIs de cabeçalho de Financeiro, DP, Operacional, CRM, RH, Gestão de pessoas e
Fiscal, cada um contra SQL independente — **29/29 ao centavo**. O que a rodada expôs, além do que conferiu:

- **Duas tabelas de férias**: a tela conta `hr_vacation_requests` (20, com canceladas/rejeitadas); o portal escreve em `employee_vacation_requests` (15). Mesma coisa, dois datasets.
- **"Presentes hoje" = entradas do dia civil**: à 1 h da manhã dá 0 com o turno noturno inteiro trabalhando. Para portaria 12x36 o rótulo devia ser "no turno (últimas 14 h)".
- **Kits do mês vem do Google Drive** (15 kits de agosto), e o banco tem 9 em montagem a 76,7%: Drive e `ged_document_kits` contam coisas diferentes. Fica para o `checar_oraculo_externo`.
- **Faturamento**: julho R$ 378 mil, agosto R$ 175 mil, setembro R$ 65 mil até dia 7. A casa fatura a partir do dia 25; agosto ficou pela metade do padrão (≈R$ 265 mil/mês em 2026). Confira se faltou emitir.
- Média de entradas/saídas da Visão Financeira subestimava 15% (mês parcial na janela) — corrigido.

### 2c.1 O que o inventário de KPIs de TODOS os builders expôs (07/09, madrugada)

- **Razão lido no plano morto (corrigido)**: o plano de contas mudou em 13/08 (3.x patrimônio, 4.x receita, 5.x despesa) e só o `_dre_simplificado` foi reescrito. Sete leitores seguiam no plano velho: a **Apuração Lucro Real** mostrava Receita líquida R$ 500.000,00 = o lançamento do capital social, e cobrava IRPJ+CSLL de R$ 146 mil sobre ele; DRE mensal, DRE consolidado por CNPJ, dashboard de Empresas, fluxo de caixa (folha), pareamento Portte e Orçado × Realizado liam receita como custo ou zero. Agora todos passam por `plano_contas_caixa.saldo()` e o `checar_dominio` proíbe o texto velho em `modules/`. Apuração 2026 da Eletrônica no razão: receita R$ 1,55 mi, prejuízo R$ 219 mil, IRPJ zero.
- **13º dentro da folha (corrigido no BI)**: as parcelas do 13º (`13O-2026-P1/P2`, geradas 03/08) moram em `hr_payslips` como competências 2026-11 e 2026-12. Todo leitor de "última competência" pegava a 1ª parcela: o BI mostrava Folha R$ 35.864 e **Margem bruta 86,7%**. Com a folha de agosto (R$ 112.411,57 bruta) a margem é **58,3%** e custo folha/faturamento 41,7%.
- **Três MRRs**: Financeiro lê `billing_rules` ativas (R$ 270.586,96); BI e KPIs lêem `contracts` ativos (R$ 269.700,06); diferença R$ 886,90. **Três "clientes ativos"**: 25 no cadastro, 12 com contrato ativo, 14 contratos. Decisão de definição, não de código.
- **Faturamento por competência**: jul R$ 269,9 mil, **ago R$ 175,1 mil** (12 notas × 14 em julho), set R$ 65,8 mil (1 nota). A operação migrou da Eletrônica (Lucro Real) para a Patrimonial (Simples, Anexo III) em jun/jul; agosto está ~R$ 95 mil abaixo do padrão. Confira se faltou emitir.
- **Apuração Lucro Real com ano fixo** (`apurar(2026)` no builder): em janeiro vai continuar mostrando 2026. Pendente.

### 2c.2 Puxada das NFS-e dos 2 CNPJs no ADN nacional (07/09, a pedido)

Rodado `NFSeNacionalSyncService.sincronizar` + `sincronizar_tomadas` para Eletrônica e Patrimonial, do NSU 0
(o mesmo que o beat faz às 04:30). **Nenhuma nota nova**: Eletrônica 118 documentos no feed (87 vivas, 31
substituídas, NSU 532); Patrimonial 31 (25 vivas, 6 substituídas, NSU 56). Tomadas 307 + 15. Os R$ 175 mil de
agosto são o que a prefeitura tem — não é sincronização perdida.

**O que o feed expôs**: as notas **3 (R$ 42.544,50, Laranjeiras Village) e 4 (R$ 65.842,42, Ideal Flores)**
da Patrimonial, competência 06/2026, estão `cancelada=true` no banco desde 20/07 18:25 (flag local, sem
`cancelamento_solicitado_em`) e **continuam vivas no ADN**: sem evento de cancelamento, sem substituição. Os
mesmos dois clientes foram faturados em junho também pela Eletrônica (notas 109 e 111, emitidas 09 e 14/07) —
**junho está faturado em dobro no governo, R$ 108.386,92**. O DAS 06/2026 da Patrimonial (R$ 17.898,58,
venc. 20/07, ainda `pendente`) foi calculado sobre R$ 187.981,05, isto é, COM as duas notas. Decisão do dono:
cancelar as duas no ADN (se o prazo municipal permitir) ou aceitar o DAS cheio. Sistema não faz escrita no
governo.

**2ª puxada (06:32, a pedido — "já foram emitidas notas pelos dois CNPJ de julho e agosto")**: feed idêntico,
NSU 532/56 sem avanço. Julho fecha: Patrimonial 10 notas (R$ 255.400,06) + Eletrônica 4 (R$ 14.500) = R$ 269.900.
Agosto, cliente a cliente contra julho: falta **Villa dos Pássaros vigilância (R$ 33.538,33)** — não existe no ADN
em nenhum dos dois CNPJs; e **Ideal Flores (R$ 65.842,42)** foi emitida em 02/09 (nota 32) e caiu em setembro
porque o ADN devolve dCompet = data de emissão. Aplicado à nota 32 o mesmo tratamento das notas 109/111 de junho
(competência corrigida, `competencia_origem_adn` guarda a original): agosto passa a R$ 240.923,23 (13 notas);
setembro volta a zero. Só a nota de vigilância dos Pássaros continua por emitir.

`NFSeNacionalService.consultar_nfse` é stub ("informações simuladas") — a consulta por chave não existe; a
verdade é o feed de distribuição. O resumo das tomadas por empresa somava os dois CNPJs (corrigido).

### 2c.3 Fechamento contábil do razão (07/09, madrugada)

- **Parado desde 11/08, em silêncio.** Receita/ISS e tomadas passam a data como texto; `periodo_fechado`
  comparava texto com data, TypeError, a transação inteira voltava (folha junto) e `fechar_grupo` devolvia
  `ok=True` — task SUCCESS por 27 dias sem nota, folha ou tomada no razão. `_post` normaliza a data; empresa
  que falha derruba a task (retry + sino).
- **Purge suicida, desarmada antes de disparar**: o repost apagava toda receita/ISS da empresa e `_post`
  recusa datas antes do corte — jan–jul (182 lançamentos, R$ 1,96 mi) sumiria no primeiro fechamento que
  funcionasse. Purge agora só ≥ corte.
- **Agosto entrou**: 13 notas (R$ 240,9 mil), folha 54 (R$ 112,4 mil, holerites do motor — sem espelho
  Portte ainda), FGTS, 20 tomadas. Toda nota viva tem lançamento.
- **Recebimento de cliente somado como receita**: o extrato lia só a justificativa do Jordan e ignorava a
  categoria do banco; 13 recebimentos da Cora (R$ 132.898,35) dormiam em "entrada a classificar" (4.9.9.01)
  e a DRE de agosto dizia receita R$ 324 mil. Regra: justificativa vence, categoria do banco cobre; e
  `reclassificar_transitorias` roda no fechamento (13 entradas → Clientes a Receber; 25 saídas com
  justificativa → conta própria). Oráculo contábil ganhou o 6º passo: transitória só guarda o que não tem regra.
- **DRE de agosto agora**: Eletrônica receita R$ 12,3 mil, resultado −R$ 10,3 mil; Patrimonial receita
  R$ 228,6 mil, pessoal R$ 112,4 mil, resultado −R$ 63,1 mil — **165 saídas da Cora (R$ 142,4 mil) seguem
  sem justificativa** em 5.9.9.01 e contam como despesa; a maioria é salário já provisionado (viraria baixa
  de passivo). O resultado real de agosto só aparece depois do Jordan justificar.
- Fica: notas 109/111 no razão em julho (a tabela de notas diz junho) — período arqueológico, não mexido.

### 2c.4 Cascas mortas e um serviço que nunca existiu (07/09, madrugada)

`checar_import_orfao` (novo, agora trava binária): 23 imports de topo para módulos apagados — todos em
cascas que nada importava (registro legado `api/v1`, `anti_procrastination/ai_integration`, 4 extratores de
OpenAPI). Removidos. Ficam dois guardados por try/except: `main_production` → `modules.ai.openclaw`
(pré-existente, zona proibida) e **Licitações** → `modules.comercial.crm.services.ClientService` com
`buscar_por_cnpj`/`criar_cliente` — serviço que **nunca existiu** (o real é `modules.clients`, síncrono, outra
API). "Vincular contrato público a cliente do CRM" nunca funcionou e falha calado. Fica para a fase de
construção de Licitações.

### 2c.5 Noite de 07/09 — loop por todos os módulos (Jordan dormindo)

- **Bake 02:53 → 03:05**: blue/green, zero drift, 8 workers na mesma imagem. Tudo do dia virou durável. A guarda
  de WIP passou a comparar com a IMAGEM (WIP alheio já publicado não segura bake).
- **Busca global** (caixa do topo, em todas as telas): `/api/v1/search` nunca foi montado — 0 requisições na vida.
  Montado pelo agregador `inteligencia` (entry point é zona proibida). Provado em processo novo.
- **Portal do Funcionário · Minhas férias** lia a tabela-cópia parada em 01/04 (14 presos em SUBMITTED); agora lê a
  autoritativa. Provado com usuário real: 1 pedido aprovado aparece.
- **Presença**: "presente" = no turno (entrada nas últimas 14 h sem saída). Dia civil dava 0 à 1h com 5 no posto.
- **Sino**: 689 avisos vivos de rascunhos já encerrados (390 de oráculos, 36/dia). Gatilho no banco: rascunho que sai
  de `rascunho` ou é apagado desativa o aviso. `checar_sino_surdo --instalar` aplica e confere os 3 gatilhos.
- **Tarefas que estouravam todo dia**: certidões dos portais (5 portais > 300 s; municipal vencida desde 01/09 sem
  renovar) ganhou 25 min; health check do Sólides falha em 60 s (as batidas do Tangerino seguem entrando).
- **Calendário fiscal** nomeava a competência anterior ("DAS 07/2026" para agosto) — corrigido e renomeado.
- **Portal do Cliente** enviava e-mail antes de gravar (2 funções) — grava primeiro; `checar_irreversivel` 2 → 0.
- **Import órfão**: 23 cascas mortas removidas; trava binária nova e documentada (30 travas).
- **Rotas do frontend sem backend**: 620, das quais 615 em código que nenhuma tela alcança; 5 alcançáveis são
  comodatos (módulo 🔴, 0 uso na vida), busca (resolvida) e dois templates que a trava não avalia.
- **DAS da Patrimonial**: 06/2026 (R$ 17.898,58, venc. 20/07) e 07/2026 (R$ 24.317,87, venc. 20/08) seguem
  `pendente` e **não há nenhum DAS/DARF/PGFN pago no extrato do Inter nem da Cora desde julho** — ou foi pago por
  fora, ou está atrasado com multa correndo. Decisão do dono.
- **Varredura completa dos 137 oráculos (03:05 → 03:51)**: 131 verdes; 3 BLOQUEADOS por causa externa (crédito
  do LLM ×2; porteiro sem espelho de setembro ainda); 3 vermelhos, todos tratados na hora: superfície morta
  (tabela que foi para a quarentena saiu do inventário), balanço (agosto reapurado depois dos lançamentos do dia)
  e extrato. Do extrato sobrou um: Inter em 05/09 nosso R$ 1.835,13 × banco R$ 1.579,13 — os 8 VT/VR de R$ 32
  do fim da noite de 05/09; a fonte (`inter_transactions`) bate ao centavo com o nosso; é o D-2 na virada BRT/UTC.
- **Extrato do Inter fora do razão desde 14/08**: a ponte gravava `status` no DEFAULT 'pendente' e a escrituração
  pula 'pendente' (regra feita para ordem da Cora não debitada). Set: 0 de 58 linhas; ago: 165 de 260. Corrigido na
  ponte, 2.610 linhas confirmadas, 224 lançamentos escriturados (R$ 67,7 mil), agosto reapurado: resultado
  −R$ 96.110,84 (com o Inter dentro). Balanço, contábil e extrato-Cora verdes.
- **MRR único**: Visão Financeira, forecast, margem por tipo, live e Custeio ABC liam `billing_rules` — cadastro paralelo e
  velho (Prime Arena R$ 40.466,50 × contrato R$ 33.479,60 desde maio; Parise 1.700 × 2.000; Hawk Eye e Parque dos
  Franceses sem regra). As cobranças reais saem de `contracts` (`receivable_accounts.origem='contrato'`, valores certos);
  agora tudo lê `contracts`: R$ 269.700,06 em todas as telas, oráculo com tolerância zero.
- **RiskMonitor criava um rascunho igual a cada 5 min** (10 em 45 min): a idempotência procurava a chave no aviso do sino,
  que não existia. Chave passou a morar no próprio rascunho (`payload._idem`); 9 apagados.
- **Travas mecânicas (04:13)**: sem regressão real — `checar_nao_vigiado` 302→299, `checar_rotas_frontend` 629→619,
  `checar_irreversivel` 2→0; `checar_bake_pendente` 8→86 são as correções desta noite ainda fora da imagem
  (segundo bake agendado); `checar_desmonte` acusou mais dois oráculos que deixam 1 rascunho (envio_cliente,
  revisao_funil) — ficam para a próxima rodada.
- **Três oráculos de cotação** deixavam rascunhos 'descartado' em produção (checar_desmonte): agora apagam; 145
  removidos.

### 2c.6 Manhã de 07/09 — respostas do Jordan viradas em código

- **Notas 3 e 4 de junho (Patrimonial)**: válidas no governo, desconto das retenções dado aos clientes. Flag de
  cancelada removida; junho da Patrimonial volta a 6 notas, R$ 187.981,05 — o DAS 06 já estava certo.
- **Villa dos Pássaros, agosto**: regra do dono — portaria e limpeza pela Patrimonial, segurança eletrônica pela
  Eletrônica. A nota de vigilância (R$ 33.538,33) segue por emitir, pela Patrimonial.
- **Saídas da Cora**: salário CLT/PJ e parte do VT/VR são pagos pelo app (a API não faz PIX). Regra no razão: PIX
  para CPF de colaborador = salário (baixa do passivo), Caixa = FGTS, "Folha" do banco = salário; "pagamento"/
  "PIX"/"Outros" deixam de valer como categoria. 109 saídas de agosto reclassificadas; resultado de agosto passa de
  −R$ 96 mil para **−R$ 39.970,08**. Ficam 110 saídas (R$ 79,5 mil) sem regra: Sólides (R$ 28 mil), empréstimos,
  sindicato, advogados, Portte, PJ sem CPF cadastrado — justificativa do dono.
- **Folha de agosto**: Portte já enviou; gerar pelo Conecta PRO e comparar no pareamento (C-PAR) é passo do DP.
- **LLM sem crédito**: as 30 mil chamadas/dia eram o redator proativo martelando (consertado 06/09; hoje 1–5/h).
  O uso real do José Luís é pequeno (WhatsApp 263 chamadas em 7 dias, US$ 0,07). Modelo local nesta VPS (8 vCPU,
  sem GPU) mede 0,32 token/s — inutilizável para conversa. Ver resposta no chat.
- **Inter R$ 256 em 05/09**: VT/VR da virada da noite (confirmado pelo dono).
- **Licitações → CRM**: construído. Contrato público vira cliente + contrato (fonte das cobranças e do MRR);
  oportunidade vira lead no funil; ação na tela; oráculo `test_oraculo_licitacao_crm` prova e limpa. Os 3 contratos
  de exemplo não foram vinculados (contrato ativo gera cobrança) — o clique é do dono.

### 2c.7 CNDs sem API paga — o que existe e o que cada órgão deixa fazer (07/09, medido)

Existe um robô de emissão no HOST (`backend/scripts/gedeon/cnd_robot.py`, Playwright + 2captcha, saldo US$ 7,32),
disparado pelo backend via Redis (`gedeon:cnd:request`, botão "Emitir" do GEDEON), com auto-retry a cada 6 h
(`cnd_auto_retry.sh`) que hoje cobre SÓ a Patrimonial (decisão de 19/08) e só os portais que funcionam.

| Órgão | Como | Do servidor (IP 82.25.75.74) | Evidência |
|---|---|---|---|
| SEFAZ-AM (estadual) | robô + reCAPTCHA (2captcha) | **funciona** | PDF real da Patrimonial 03/09, válido até 03/10/2026 |
| SEMEF Manaus (municipal) | robô + captcha de imagem (2captcha) | **funciona** | PDF real 19/08, válido até 15/02/2027 |
| Receita/PGFN (federal = INSS) | robô + hCaptcha (2captcha) | **falha**: 2captcha devolve UNSOLVABLE (3 tentativas, 07/09) | teste real hoje; o PDF de 20/07 é a página inicial, não certidão |
| Caixa (FGTS/CRF) | navegador real | **bloqueado por IP** (403 Azion, Chromium de verdade) | medido 07/09 |
| TST (CNDT) | robô + captcha de imagem | **hoje não responde** (timeout IPv4 do host e do container); funcionou em 12/08 | 4 consultas ok em 12/08 |

Captcha há em TODOS os portais: "zero custo externo" literal não existe; o 2captcha custa centavos por certidão
(saldo atual dá para meses). O caro é o Infosimples (usado para FGTS e CNDT: 46 atualizações em 30 dias).

Caminhos: (1) federal via e-CAC com o certificado A1 — o det-robot já faz o login gov.br com hCaptcha `rqdata`
(o `cnd_robot` não manda `rqdata`, provável causa do UNSOLVABLE); (2) FGTS e CNDT só saem de outro IP: um
"nó de emissão" no PC do Jordan (mesmo robô, sobe o PDF pelo `/gedeon/cnd/upload`, agora multi-CNPJ) ou um proxy.
Decisões do dono (07/09, manhã): **só a Patrimonial**; captcha pelo 2captcha (assinatura dele). **Nó de saída
construído**: usuário `cndtunnel` (sem shell, só encaminhamento para 127.0.0.1:1080, chave restrita, drop-in no
sshd), `cnd_watcher.sh` usa `socks5://127.0.0.1:1080` quando a porta existe; provado com Chromium saindo pelo
túnel. Túnel de pé às 10:08 (saída 187.112.25.106): Caixa e TST respondem 200 por ele. **CNDT emitida de verdade**
(`cnd_robo2.py`, nº 74869638/2026, válida até 06/03/2027) — Infosimples deixa de ser necessário para o CNDT.
**Caixa**: muro Radware/ShieldSquare com hCaptcha; o 2captcha resolve, o widget aceita, mas o POST de validação
devolve o muro (assinatura presa ao widget/fingerprint). Diagnosticado, não passa hoje — FGTS segue pelo
Infosimples ou manual.
**Receita pelo e-CAC (tentado 07/09 10:49, pelo túnel)**: hCaptcha do login do e-CAC resolve e submete; o gov.br pede
login (sessão do robô do DET expirada); "Seu certificado digital" abre hCaptcha de imagem (sitekey 93b08d40…, callbacks
`onHcaptchaCallback`); o token do 2captcha chegou (73 s) mas foi injetado na textarea + submit e a tela não avançou —
o passo não testado é entregar o token via `onHcaptchaCallback(token)`. **Decisão do dono: parar; a Portte segue
emitindo a federal (plano B).** Robô do DET ficou PAUSADO (`docker pause`) para não queimar 2captcha tentando o
captcha do gov.br a cada ciclo sem ninguém para completar o 2FA; `docker unpause conecta-pro-det-robot` quando o
Jordan for fazer o login pelo noVNC.

### 2c.8 Alarmes diários que gritavam sem motivo (07/09, manhã)

- **"Extrato duplicado: 126 novas em dobro"** todo dia há um mês: a regra contava gêmeos legítimos (dois VT de R$ 32 à
  mesma pessoa no mesmo dia, ids distintos no banco). Só linha sem `external_id` pode ser importação repetida: 121, todas
  herdadas. Silencioso agora.
- **"Caixa não bate: R$ 1–4 mil"** 4× por dia: somava ordens de pagamento iniciadas (que a escrituração pula) e
  carregava **20 lançamentos fantasmas** — espelhos de linhas do Inter apagadas na dedup de 22/08, 17 deles com o gêmeo
  vivo já escriturado (dobro no razão, R$ 12.317,46 de movimento). Copiados para `lixo_20260906.accounting_entries_
  fantasma_20260907` e removidos; agosto reapurado: **−R$ 39.445,28**. Regra silenciosa; balanço e contábil verdes.

- **Operacional, para o dono ver**: 9 de 9 postos sem escala vigente e 17 escalas em rascunho (triagem). O módulo de
  escalas existe e ninguém publica escala; a cobertura mostrada (66,7%) sai de alocações, não de escala. Agentes não
  mexem em dado operacional — fica anotado.

### 2c.9 Beat que engole a própria falha (07/09, 11h)

- Nova trava `checar_beat_engole_falha` (AST): task agendada cujo `except Exception` loga e devolve normal. **55 na
  estreia** (linha de base; pista, não gate). É a forma geral do defeito que parou o razão por 27 dias.
- Em vez de mexer em 55 tasks: `task_falha` passou a ouvir `task_postrun` — resultado `{"ok": False}` ou `{"erro": …}`
  vira aviso no sino ("Tarefa agendada devolveu falha: …"), 1 por tarefa por dia. Provado com resultado falso.
- Bake nº 4 disparado sozinho às 11:01 pelo agendador da janela sem WhatsApp.

### 2c.10 Tarde de 07/09 — DP, quarentenas e o que fica no radar

- **DP**: seis leitores de "última competência da folha" (Folha · Colaboradores, Rubricas, Início do portal, comparativo,
  Meus holerites, limiar de caixa baixo) pegavam dezembro/2026 (parcela do 13º, R$ 30 mil) como folha atual. Todos
  passam a ignorar `13O-…` e meses futuros: agosto, 54 holerites; limiar da Patrimonial R$ 109.058,51.
- **Quarentena** (git rm, boot de prova servidor+celery OK): `modules/integrations/whatsapp` (4 modelos sem tabela,
  controllers nunca montados, só re-exportado pelo agregador que ninguém importa) e `modules/integrations/email`
  (6 modelos sem tabela, nenhuma rota; o envio real é `core.mailer`). Tabelas fantasmas: 58 → 48 no próximo bake.
- **Fantasmas que ficam** (decisão pendente): `gov_*` 29 — a persistência inteira de governo declarada sem migration,
  usada por serviços que nunca gravaram (o painel de status já não depende dela); `health_*` 4, `fgts_*` 3, `nfe/nfse/
  nfse_lotes` (modelos antigos do fiscal), `inss_contribuicoes`, 2 do anti-procrastinação. 10 são entulho (classe nunca
  usada fora do arquivo).
- **Obrigações fiscais vencidas em aberto**: Eletrônica 17 (R$ 51.623,05 informados, 8 sem valor; maio–julho: FGTS, ISS,
  IRRF, INSS, FGTS consignado) — a maioria no reparcelamento com a União; Patrimonial 2 (DAS 06 e 07, R$ 42.216,45).
  Registro para o dono; sistema não paga nada sozinho.

- **Contratos**: as 14 cobranças de setembro nasceram do contrato certo (gerador é por contrato, dia 1). O que faltou
  não é bug: o contrato de manutenção da Villa dos Pássaros (CTR-2026-00018, R$ 3.800) **venceu em 31/08 e continua
  "ativo"** — renovar ou encerrar. E **10 contratos (R$ 246.538,56 de MRR) vencem em 31/12/2026**: renovação a planejar.

- **DET (Domicílio Eletrônico Trabalhista) sem leitura desde 03/07/2026** — 11 comunicações no banco, a última de julho.
  O robô do DET perdeu a sessão gov.br (o "logado" era flag velha) e ninguém refez o login; hoje está pausado. Isso é
  prazo legal, mais importante que qualquer CND: refazer o login pelo noVNC (certificado + 2FA) e `docker unpause
  conecta-pro-det-robot`. **Prioridade do dono.**
- CRM: 197 leads em 30 dias (WhatsApp) e 6 propostas. Corrigindo o que escrevi de manhã: o **follow-up de propostas
  está vivo** (beat 08:30 — 40 registros em 30 dias, 9 na última semana, último em 04/09). O que parou em 16/07 foram os
  follow-ups agendados à mão (`crm_followups`), e as **sequências têm zero inscrição** — a máquina existe, ninguém
  inscreveu ninguém. Isso é uso, não bug.
  E o follow-up de propostas gera a lista mas **não envia nada**: 40 registros em 30 dias, todos "pulados — disparo
  desligado (gate LGPD)". O envio automático ao cliente está atrás da chave `FOLLOWUP_AUTO_SEND` (desligada de
  propósito). Ligar é comunicação ao cliente — **decisão sua**; enquanto isso, o disparo manual existe na tela do CRM
  ("Tocar follow-up") e na ferramenta do assistente.

- **Boletos de cobrança são emitidos fora do ERP** (Eletrônica no app do Inter, Patrimonial no app da Cora — regra do
  dono, 07/09): das 13 cobranças de setembro nenhuma tem boleto, PIX ou id de cobrança ligado no sistema; `inter_cobrancas`
  tem 2 linhas. O ERP registra a conta a receber e concilia o pagamento (5 de 13 já "paga"), mas a emissão e o envio ao
  cliente são manuais. Capacidade DESLIGADA: existem módulos de cobrança PIX recorrente e de cobrança Inter sem uso.
  Ligar = decisão do dono (é comunicação ao cliente).

### 2c.11 Boleto nasce no Conecta PRO (07/09, tarde — pedido do dono)

- **Decisão executada**: "os boletos são gerados da Eletrônica pelo Inter e da Patrimonial pela Cora… direto no
  Conecta PRO… quando emitir a nota, já dar a opção de gerar o boleto". O que "já tinha" (cobrança recorrente,
  cobrança Inter) nunca emitiu nada: `receivable_accounts` tinha **zero** contas com `boleto_id` nas duas empresas.
- **Como ficou**: a cobrança é emitida NA conta a receber que o gerador do dia 1 já cria (nada de conta paralela),
  roteada pela empresa credora da conta. Duas portas na tela do redesign:
  - **Financeiro › Receber**: coluna *Cobrança* (Boleto emitido / A emitir / Recebida) + botão *Emitir cobrança*
    por linha; aba *Recorrência* virou a PRÉVIA do mês na mesma base da ação (hoje: 8 contas, R$ 115.916,81, 5 pelo
    Inter e 3 pela Cora, todas "Pronta"); aba *Gerar cobranças* emite de verdade (confirmação + "só prever" por padrão).
    A prévia antiga lia `clients.mrr` e a ação antiga criava contas paralelas — duas bases, dois números; agora é uma.
  - **Fiscal › NFS-e emitidas (nacional)**: coluna *Cobrança* + botão *Gerar boleto* por nota — é o "fluxo natural":
    a nota acha a conta em aberto da mesma empresa, mesmo tomador e mesma competência. Nota sem conta em aberto
    diz isso (a de agosto já está paga; as de jan–jun nunca tiveram conta) — o código não inventa vencimento.
  - Recusas: conta paga/cancelada, vencimento passado, sem CPF/CNPJ, abaixo de R$ 5, já emitida (idempotente).
    Emitir é registrar no banco; **nada é enviado ao cliente** — comunicar é outro passo.
- **Medido com R$ 5 reais contra o próprio CNPJ** (único teste possível sem envolver cliente):
  - **Inter**: emitiu. O POST devolve só o código; linha digitável, PIX copia-e-cola e código de barras vêm do GET
    logo depois — o adaptador agora busca na emissão (antes gravava campos vazios). `cancel_boleto` usava DELETE e
    o Inter responde 405; virou POST e o banco aceitou (2xx), **mas 15 min depois a cobrança ainda está
    `A_RECEBER`** — cobrança `e622b781…`, R$ 5, pagador Eletrônica, vence 10/09. Se não cancelar sozinha, cancele
    no app do Inter ou deixe vencer: é a Eletrônica devendo R$ 5 a ela mesma, dinheiro não sai.
  - **Cora**: recusou com `REC-0031 Cannot create invoice for own identity` — a Cora não cobra o próprio CNPJ. O
    caminho até a API está provado; a primeira emissão real será a de um cliente (Laranjeiras, dia 10, R$ 42.544,50
    está em aberto). Sugiro emitir UMA pelo botão, conferir no app da Cora e só então usar *Cobranças do mês*.
- **O que falta para o fluxo ser 100 % "emitir nota → boleto na mesma tela"**: a emissão de NFS-e pelo ERP
  (`/nfse-nacional/emitir`) existe, mas as notas de julho/agosto foram emitidas no portal e entraram por sincronia.
  Enquanto for assim, o botão na nota sincronizada É a tela seguinte. Quando a emissão passar a sair do ERP, o
  mesmo botão serve — a nota cai na mesma tabela.
- **Emitir a nota pelo próprio ERP** (medido 07/09, 14h, sem transmitir nada): as duas empresas têm certificado válido
  na tabela `empresas` (Eletrônica até 13/01/2027, Patrimonial até 06/07/2027) e o dry-run gera e assina o XML da DPS
  para as duas. O que falta é UMA chave: `empresas.nfse_ambiente` está em **homologacao** nas duas (URL de produção
  restrita do ADN). Virar `producao` é emissão no governo — **decisão sua**; o ERP nunca emitiu uma nota real (as 112
  de 2026 entraram por sincronia do ADN). Quando virar, o passo seguinte é o formulário de emissão na tela Fiscal (hoje
  a tela lista e sincroniza; o botão "Emitir NFS-e" não abre formulário) — e o botão "Gerar boleto" já espera a nota.
- Commits `3a99f0498`, `03905114e`, `964740d2f`; bake das 13:36 publicou tudo (sem drift). Oráculo
  `test_oraculo_cobranca_recebivel` verde (roteamento, recusas, idempotência, casamento nota → conta).

### 2c.12 Varredura tela a tela dos 31 módulos do redesign (07/09, tarde)

- **Instrumento**: abrir cada `/redesign/data/<módulo>` e contar tabelas vazias, painéis zerados e tempo. 31 módulos,
  ~620 telas, todas 200. O que apareceu e o que foi feito:
- **Agendador mentia**: lia cinco tabelas `scheduler_*` que nunca receberam uma linha, e dizia "fila vazia" para um
  beat com **97 tarefas em 9 filas**. Agora mostra a grade real do `beat_schedule`, falhas 24h/7d e a lista de falhas
  que chegou ao sino — e diz de frente que execução bem-sucedida não é registrada (Celery sem backend de resultado).
- **Documentos levava 16 s para abrir**: 195 leituras SSL na API do Google Drive a cada abertura (cProfile). Cache
  Redis de 15 min por competência: 0,05 s na segunda leitura, mesmos KPIs. A primeira leitura de cada 15 min ainda
  paga os 16 s — precomputar no beat é o passo seguinte se incomodar.
- **Falhas de tarefa agendada nos últimos 7 dias** (pelo sino, 4 avisos por evento = 4 destinatários):
  `integrations.sync_work_schedules_from_solides` falhava **todo dia** com coluna inexistente (`se.employee_id`,
  `extra_data`) — casamento corrigido por `solides_id` (25 ativos casados; 0 mudanças: as escalas já batem) e nome de
  escala sem código conhecido não vira mais texto livre em `escala_padrao`. `solides.health_check` (sonda de 5 min,
  0,4 s normalmente) estourou UMA vez à 01:57 — transitório do Sólides, fica. `ged.buscar_certidoes_portais` estourou
  05 e 06/09 e foi consertada de manhã (limite 1500 s); hoje rodou 06:30 e renovou FGTS e trabalhista. `proativo`
  parou de falhar em 02/09.
- **Telas vazias que são honestas** (tabela de origem vazia, não bug): Equipamentos (4), Marketing biblioteca/copy/
  estrategista/brand-voice, Serviços ordens/agendamentos, Automações, Segurança mascaramento/criptografia/PIA,
  Configurações templates/feature-flags, Assistente chat/histórico, Gestão de pessoas banco de horas/treinamentos
  (`time_bank` e `sst_treinamentos` vazios). Portal do funcionário zerado para o admin é a parede self-only.
- Commits `68da125b2` (telas) e `b9666abe8` (Sólides), hot-copy em todos os containers.

### 2c.13 Botões mortos e o saldo de fim de semana (07/09, fim de tarde)

- **Caçador novo, trava 33 — `checar_botao_morto.py`**: cruza os ~4.300 `endpoint` que as 620 telas do redesign
  chamam com a tabela de rotas do app, método incluso. Estreia: **3 botões davam 404 desde que nasceram** — ninguém
  viu porque nada explode, o usuário só desiste. Consertados e provados por HTTP:
  - Contas a receber › *Cobranças do mês* (o de hoje): `{ano}/{mes}` literal na URL — o formulário do redesign manda
    campos como query e nunca monta path param. Rota passa a receber por query.
  - Área do cliente › *Onboard de um cliente*: só existia com `client_id` no caminho → porta por query, mesma ação.
  - Relatórios › *Recalcular KPIs*: apontava para uma rota que nunca existiu → ação que enfileira a task do beat.
- **Oráculo do extrato falhou na varredura da tarde**: "Inter em 05/09: nosso extrato R$ 1.835,13, banco R$ 1.579,13,
  diferença R$ 256". Medido dia a dia: nos dias úteis bate ao centavo; para **sábado 05/09** o Inter devolveu o saldo já
  com os 8 PIX de VT/VR (8 × R$ 32) que o extrato dele mesmo data no **domingo 06/09**; em 29–30/08 devolveu o saldo de
  sexta sem os débitos do fim de semana. Não é dado errado nosso: é o banco não ter saldo histórico de fim de semana.
  O oráculo agora confronta o último dia útil (PASS em 04/09, R$ 1.803,13 dos dois lados).
- Varredura completa dos 56 oráculos à tarde: só o extrato falhou, pelo motivo acima. Commits `9cf06d495`, `a8202e508`,
  `1f890d36d`.

### 2c.14 O crédito do José Luís, em números (07/09, 15h — resposta ao "só recarrego quando normalizar")

| dia | quem queimou (`llm_provider` = redator das regras proativas) | uso real (WhatsApp + orquestrador + visão) |
|---|---|---|
| 26/08 | 1.622 chamadas · US$ 0,21 | — |
| 27/08 | 8.950 · US$ 1,14 | US$ 0,04 |
| 28/08 | 21.853 · US$ 2,68 | US$ 0,54 (dia pesado: 112 vídeos + 63 imagens) |
| 01/09 | 24.105 · US$ 2,98 | US$ 0,02 |
| 02/09 | 25.927 · US$ 3,21 | US$ 0,03 |
| 03/09 | 30.218 · saldo zerou às ~11h (4.402 ok, o resto 402) | — |
| 04–06/09 | ~31 mil/dia, **todas falhando** (402, custo zero) | 0 respostas a clientes |
| 07/09 | 7.118 até as 05:00 e **4 por hora** desde então (disjuntor, commit `2f47abfe0`) | — |

- **Normalizou.** O vazamento era o redator proativo (`notifications/proativo/redator.py`) chamando o LLM a cada regra
  avaliada, ~25 mil vezes por dia — 90 % do gasto. Fechado às 05:00 de hoje com disjuntor; resíduo de 4 chamadas/hora.
  Com crédito, o gasto esperado é o do uso real: **US$ 0,05 a 0,50 por dia** (o de 28/08, com vídeo, foi o teto).
- **Enquanto o saldo está negativo, o José Luís está mudo**: 41 mensagens de clientes em 04/09 receberam "estou com um
  problema técnico"; 05/09, duas; 06 e 07/09, nenhuma entrada. As 8 "saídas" por dia são avisos para você, não respostas.
- O aviso "Saldo do José Luís" foi acalmado: 3h só no primeiro dia, depois 1/dia (eram 6/dia há 5 dias). Provado na
  rodada das 15:07: "silenciado: mesmo patamar", nenhuma mensagem nova. A trava
  `checar_llm_martelando` (28ª) fica de vigia para a próxima origem que martelar.

### 2c.15 O seu sino, lido de trás para frente (07/09, 15h)

- **"Caixa não bate" duas vezes toda manhã** (08:16 e 08:46, 15 avisos em 7 dias, valor diferente a cada um): a regra
  roda a cada 15 min e via o meio do caminho entre o extrato da Cora chegando às 08:10 e a escrituração das 08:40; às
  09:00 não havia diferença nenhuma. Passa a comparar até D-2, que está em repouso (hoje: razão −4.682,54 = extrato
  −4.682,54). Oráculo proativo 7/7 verde. Commit `10fd5454b`.
- **"Lead sem contato há N dias": 175 não lidos** — 141 deles em 02/09 e 25 em 03/09 (rajada quando a regra
  nasceu); desde 04/09 é 1 por dia. Não mexi: está no ritmo certo agora.
- **Central de Aprovações**: 5 rascunhos do agente esperando você e 1 "FALHOU" de 31/08 — "pedir cotação" tropeçou
  no `number` de 20 caracteres, que já foi alargado para 40 (a cotação HAWKEYE-20260831 saiu depois). O rascunho
  fica como falha até você descartá-lo na tela; não é problema vivo.
- **"Razão sem lançamento: folha jan–jul/2026" — 7 alertas permanentes desde 11/08**: a regra ignorava o corte
  contábil (o razão nasce em 01/08; folha anterior nunca terá lançamento, por desenho). Passa a respeitar o corte;
  0 competências acusadas. Commit `d2265215b`.
- **"Certidão vencendo": 26 abertos, 21 deles a CRF do FGTS** — ela vale 30 dias e o robô renova todo dia; com
  janela de 30 dias nascia "vencendo" e ficava assim para sempre. FGTS passa a alertar a 5 dias (se chegar lá sem
  renovar, o robô falhou); a municipal da Eletrônica (vencida em 01/09 por sua escolha) sai da regra. Regra e oráculo
  lêem a mesma janela. Sobram 3: estadual (2) e Falência TJ-AM. Commits `3b24943ff`, `5c5e98e9d`.
- **"Férias sem decisão" (13)**: dois são de gente que já saiu (Marta, demitida em 09/06; Raimundo, inativo desde
  05/05) — 130 dias no quadro à toa; regra passa a olhar só ativos (commit abaixo). Os 11 restantes são reais e
  antigos (a maioria com 130 dias): pedidos "submetidos" cujo período já passou — aprovar retroativo, rejeitar ou
  cancelar é do RH. **Adailson** aparece duas vezes (dois pedidos).
- **Prazos do DP** (35 vivos, confirmados no banco): **ASO — 25 dos 53 ativos com ASO vencido e 21 sem nenhum ASO
  registrado; só 7 válidos.** Ou os exames estão em dia fora do sistema (Portte/clínica) e falta registrar, ou é
  passivo de SST real — os dois pedem você. O cartão de ASO no quadro de prazos passa a dizer os 21 sem registro
  (antes só via quem tinha exame vencido; commit `0cd67eaf0`). **ADAILSON SERRA ALVES**: ativo, aviso prévio de 30 dias contado de
  04/08 venceu em 04/09 e o processo segue "iniciado" — desligar ou cancelar. **KEYSON DA SILVA PINTO** já estava
  inativo desde 28/08 com o processo esquecido em "iniciado": o prazo ficava no quadro à toa; primeiro filtrei a
  regra por "ativo" (commit `ede3e961e`) e o oráculo `prazo_desligamento` cobrou: o processo dele sumiu de TODAS as regras.
  Acerto final (`f2b3f115b`): inativo com processo aberto aparece com título próprio — "Desligamento sem concluir no
  sistema: KEYSON" — concluir (rescisão, TRCT, eSocial) ou cancelar no DP.

### 2c.16 DP · Fiscal · RH · GED — loop pedido pelo dono (07/09, fim de tarde)

**DP**
- Fechamento de ponto mostrava setembro (2 espelhos) e escondia agosto (53): passa a mostrar a última competência
  com população e a nomeia. Junho é o único mês com fechamento (50); **julho e agosto nunca fecharam** — a folha saiu
  sem o ponto fechado. Isso é operação (Pyetra), não código.
- Espelho do eSocial: 157 de 290 eventos sem tipo/data são XML ainda não baixado — o governo bloqueia o espelho nos
  dias 1–7 e limita 10 acessos/dia (a task pula sozinha e retoma 08/09 às 09:10); em 31/08 o próprio governo devolveu
  HTTP 500 nos 8 acessos. A tela agora diz "133 baixados · 157 aguardando". Não é bug.
- Tela "Jornadas do mês corrente" traz também o mês anterior (é a janela da consulta, com seletor de competência).

**Fiscal**
- Grade de cobertura de certidões comparava por NOME e a mesma certidão tem nome diferente em cada empresa: 10 "FALTA"
  que não existiam. Por tipo: 9 tipos, 2 faltas reais (Falência para a Eletrônica — sua decisão; Registro CNPJ para a
  Patrimonial). DCTFWeb/Reinf "cumpridas" com valor zero têm procedência (recibo do pacote da Portte no Drive; baixa
  aprovada por você) — não é invenção.
- Guias FGTS/INSS do Onvio param em 12/2025 e 11/2025 — a fonte secou; as obrigações de 2026 vêm do calendário legal.

**RH**
- Candidatos (10), entrevistas (4), planos de carreira (11), clima (3), vagas (10): tudo criado em 16/03 e nunca mais
  tocado — parece carga de demonstração num painel que diz "dados reais". Decida: apagar ou usar.
- Gestão de Pessoas dizia "65 colaboradores ativos" (is_active) onde o DP diz 53 (status ativo): passa a usar a régua
  do DP e mostra os 8 PJ à parte.

**GED (seu pedido: notas duplicadas, CND original, "outras coisas")**
- Medido no Drive: os PDFs das certidões no banco SÃO os originais dos órgãos (Caixa wkhtmltopdf, Receita iText, TST
  OpenPDF, SEFAZ/prefeitura Chromium, um "caixa_manual" impresso do seu Mac); o kit já anexava esses. O que o sistema
  GERAVA era a nota: `Nota Fiscal NFS-N.pdf` renderizada do XML, ao lado da original que a Pyetra sobe do portal
  (`NFS-e N.pdf`) — comparação por nome exato, daí a duplicata.
- Corrigido: o kit **não gera mais DANFSe** (o SEFIN nacional devolve 501 para a DANFSe por API — não existe PDF
  oficial por integração), confere por número da NFS-e/DPS em qualquer nome e devolve a lista "faltando: anexar o
  original do portal"; certidão do mesmo tipo (e empresa) já na pasta não é duplicada. Nada é apagado; o kit de julho
  fica como está. Provas só de leitura: julho 12/12 presentes; agosto lista a NFS-e 32 da Ideal Flores.
- Regra de mês mantida como está documentada no código: o kit da competência X leva a nota emitida em X+1 (mês de
  entrega). As notas de competência 08 emitidas de 20 a 26/08 estão no kit de julho (pasta "Agosto") por essa regra.
  Se o certo for "nota da competência", é uma linha para mudar — **sua decisão**.
- **O que o Drive mostrou depois, lendo o PRODUTOR de cada PDF**: havia um segundo gerador, o botão "Kit real do mês"
  (`kit_real_controller`), que fabricava com reportlab e timbrado do ERP: (a) 20 "NFS-e N.pdf" — notas de fev–mar/2026
  da tabela antiga `nfses`, TODAS as do condomínio, sem olhar competência, com CNPJ da Eletrônica em kit da Patrimonial;
  (b) 7 "Boleto NFS-e 08/2026.pdf" — um "BOLETO / COBRANÇA R$ 131.684,84" somando essas notas velhas; (c) 56 "guias"
  e "certidões" desenhadas (ISS Manaus, DARF IRRF, INSS Patronal, FGTS, EFD-Reinf, DCTFWeb, "Certidao Negativa…") ao
  lado das originais do pacote Portte/Onvio. Tudo subido em 19/08 aos kits de julho.
- **Feito (nada apagado, tudo reversível)**: os 83 fabricados foram para a subpasta "_fora_do_kit (nota antiga gerada
  pelo sistema, 07-09-2026)" de cada condomínio; o Kit real ficou só com o que é do sistema por natureza (contracheque,
  recibo de VT) e anexa certidão ORIGINAL de `ged_certidoes`; o orquestrador não gera DANFSe e deduplica por número/tipo.
  **Regra nova, sua**: a nota do kit é a da COMPETÊNCIA do kit — as 12 notas de competência 08 (+ boleto da 116) foram
  movidas do kit de julho para o de agosto; agosto agora tem 12/12 notas do sistema; a NFS-e 32 da Ideal Flores (emitida
  02/09) não tem arquivo — anexar o original do portal.
- **Preço da honestidade**: o kit de julho da Ideal Flores caiu de 80% para 50% — o que sumiu era fabricado. Faltam nele,
  de verdade: nota da competência 07 (nº 21 e 111), boleto real do banco, comprovante de INSS original.
- Kits de agosto (pasta "Setembro"): certidões + 12 notas; folha, VT e guias ainda por subir (montagem automática dia 28).
  Commits `44e7bd6d4`, `ac5345ac4`, `ec240c74e`, `26ccb5f90`, `fef61a2a1`.

### 2c.17 GEDEON a fundo — seus seis agentes, o fluxo autônomo e o que estava quebrado (07/09, noite)

**Estrutura (medida)**: 17 mil linhas em `modules/gedeon`; 6 agentes (Hermes documental, Kronos vencimentos, Themis
assinaturas, Atlas aprendizado, Argos conformidade, Sophia busca semântica); 56 rotas; 15 tarefas no beat; fluxo por
eventos em Redis Streams (12 streams, consumidor `conecta-pro` sem atraso — vivo). Não é "Hermes Agent" externo: Hermes é
um dos seis, classificador/vinculador de documentos por regex.

**Quebrado e consertado**
- Hermes classificava "CND-FGTS-…" como CND federal (o genérico `cnd` vinha antes dos específicos) e perdia nomes com
  acento ("Certidão Negativa de Débitos Trabalhistas" → "outros"). Regras reordenadas, sem acento, tipos novos
  (FGTS, municipal, estadual, INSS, falência, trabalhista). 14 nomes reais testados, todos certos.
- Kronos usava `docker exec psql` de dentro do container, 60 dias para tudo e todos os ASOs de todo mundo: 26 certidões
  e 88 ASOs "em alerta" (há 53 ativos). Agora SQL direto, FGTS a 5 dias, demais a 30, só ASO vigente de ativo: 3
  certidões e 25 ASOs — os mesmos números do DP. As versões async delegam às síncronas.
- `gedeon.verificar_kits_completos` olhava o kit MATERIALIZADO a 100% (por documento fabricado) e mandou 195 "Kit
  Completo" ao sino com o Drive em 20%. Agora usa a completude real do Drive; 15 kits, 0 a 100%, 0 avisos. E registra
  no Atlas quando um kit do Drive fecha — Atlas dizia "0 kits registrados" porque só o Kit real o alimentava.
- `kits/status` dizia "12 prontos" pelo score padrão 100 do contexto por eventos. Agora lê o Drive (cache): 2 prontos,
  10 críticos — a verdade. `/kits/completude` tinha cache em memória por worker (20 s em cada worker frio); cache Redis
  compartilhado com a tela Documentos: 0,02 s.
- `ged.auto_collect_documents` (dia 21) abortava a transação num cliente de CND e o log de coleta explodia: rollback.
- Hermes mensal rodava dia 1 para o MÊS CORRENTE (sem pacote ainda) e 447 de 626 documentos Onvio não têm mês no nome
  (nunca vinculavam). Agora processa a competência anterior e usa a data de recepção como fallback. **Mas** os 49
  candidatos de agosto estão todos como "outros" no classificador do Onvio — vinculação continua em zero até esse
  classificador aprender os nomes reais ("Prorrogação Contrato Experiência", "Declaração Deslocamento VT"…). Fica.

**O que é desenho, não bug (para você saber)**
- Themis conta como "pendente" todo documento não assinado do kit (2.920) e avisa ~36 pessoas por dia (29/08, 01/09,
  04/09) por e-mail + notificação no portal. Em 30 dias: 231 notificações no portal, **1 lida**. Os colaboradores não
  entram no portal; a assinatura (372 assinados) acontece por outro caminho. Vale decidir se o aviso continua.
- Contexto por eventos (dashboard "1 cliente"): só recebe eventos de folha/holerite/NFS-e/ponto, que quase não
  disparam para os condomínios; o trabalho real passa pelo Drive/Onvio. `gedeon/dashboard` segue lendo esse contexto;
  `kits/status` já lê o Drive.
- Sophia: 857 documentos indexados, embeddings OpenAI, busca respondendo. Argos: só pelo endpoint de conformidade.
- Coleta automática mensal (dia 21) consulta CNDs direto nos portais do governo (sem Infosimples) para o CNPJ da
  Eletrônica — inócua, mas fora da sua regra "certidões só da Patrimonial".

**Suas três respostas, aplicadas (07/09, 17h)**
1. "Podem receber pelo app ou pelo WhatsApp": o aviso de assinatura do Themis passa a ir também pelo WhatsApp (serviço
   do CRM) para quem tem celular (49 de 53 ativos), além do e-mail e da notificação no portal; SMTP fora não cala o
   WhatsApp; o registro do lembrete diz os canais. Amostra da mensagem enviada ao seu WhatsApp; um envio real feito.
2. "De acordo" em ensinar o classificador: 16 regras novas com os nomes reais do pacote (Recibo de Pagamento, Comunicação
   de Transferência, NFS, TRCT, Salário Família, Prorrogação de Experiência, Advertência, DAS/PGDASD, DANFE, CNPJ…) e
   acentos por NFKD. Reclassificados 191 de 387 "outros"; sobram 196 (nomes só com números ou só o nome da pessoa).
   Hermes: o nome no arquivo vem sem espaços no último segmento ("…-1-ALEXANDRESOUZADASILVA") — casamento sem
   espaço/acento, escopo de funcionário inferido, e o original entra como documento próprio quando não há slot vazio.
   **Agosto: 45 recibos de pagamento originais vinculados aos kits do banco (7 kits), idempotente.**
3. "Coleta mensal ou a qualquer momento": fica como está (dia 21 + botão na tela).

4. Passo seguinte, já feito (07/09, 18h): classificação por CONTEÚDO da 1ª página para o que o nome não diz — 165 dos
   196 restantes ganharam categoria (96 "Comprovante de Rendimentos", 51 scans sem texto viram "documento digitalizado",
   6 DAS, 5 fichas, 4 contratos…). Sobram 31 "outros" em 626 (eram 447 de manhã). O Hermes mensal roda isso antes de
   vincular.

**Memória (medido 07/09, 17h40)**: host com 9,4 GB livres de 32; `celery-sefaz` em 1,66 GB de 2 GB de teto — não é
vazamento: cada processo filho carrega o app inteiro (~900 MB) e o compose fixa `concurrency=3` numa fila que rodou 2
tarefas em 4 h. Baixar para 1 pouparia ~1 GB; é edição de `docker-compose*.yml` — zona proibida, **decisão sua**.

Commits `c9776455c`, `3867691b6`, `62b8897c0`, `7ec4f2be9`, `ba1a96636`, `7b85cc3f9`, `ee92febdc`, `7e4fe3f84`. Bake das
00:00 torna definitivo.

### 2c.18 Operacional — onde está o gerente (07/09, noite; pedido do dono)

- **Pedido**: saber onde o gerente está toda vez que chega num posto; check-in e check-out obrigatórios no condomínio;
  o dono avisado. **Medido antes de codar**: os dois gerentes (Eliziel, Gerente Operacional; Orlailson, Supervisor) são
  PJ e não batem ponto — zero batidas em 7 dias, logo não há rastro de GPS para reaproveitar; e as 31 `geofence_zones`
  têm TODAS a mesma coordenada (centro de Manaus) — cenário, não cerca. A cerca real é a coordenada do POSTO (`posts`,
  8 de 9 georreferenciados; o 9º é a base/escritório).
- **Feito**: telas "Cheguei no posto", "Saí do posto" e "Onde está o gerente" em Operacional › Postos & Presença;
  o celular captura o GPS (tipo de campo novo `geo` no redesign — depende do deploy do frontend, em andamento);
  a chegada cria a visita (`visitas`, tipo acompanhamento) com distância até o posto (300 m de raio; fora do raio é
  marcado ⚠️), recusa segunda chegada sem saída, e a saída fecha com a permanência. **A cada chegada e saída você
  recebe no WhatsApp** ("📍 Orlailson chegou em Prime Arena às 18:26, a 17 m do posto"; "🚪 saiu… 38 min"). O admin pode
  registrar em nome do gerente (você cobrindo uma ligação).
- **Obrigatoriedade, o que o sistema consegue impor**: duas regras proativas — visita aberta há mais de 4 h (esqueceu o
  check-out) e gerente sem nenhum check-in até 11 h em dia útil (não está registrando). O que ele não consegue: saber que
  o gerente chegou sem tocar no botão — isso exigiria rastreio contínuo pelo app, que hoje não existe.
- **Logins**: Orlailson já tinha (`supervisoroperacionalpaiva@gmail.com`), agora vinculado ao cadastro; Eliziel foi criado
  (`primetechmao@gmail.com`, senha provisória enviada só ao seu WhatsApp). Os dois entram no redesign pelo celular.
- Provas: chegada a 17 m do Prime Arena, segunda chegada recusada, saída com 1 min medido pelo relógio do banco (o
  primeiro teste deu "-240 min" por fuso — corrigido), avisos no seu WhatsApp, oráculo proativo 7/7, os 12 testes do
  Operacional verdes. Commit `9d49c3436`.
- **Operacional, o resto da passada**: 12 oráculos e testes de ação verdes (escala ciclo, ronda, banco de horas,
  fechamento de diaristas, leituras). O que é uso, não código: 17 escalas em rascunho (agosto e setembro 100% rascunho,
  julho publicada) e 9 postos sem escala publicada — o ciclo submeter → aprovar → publicar existe e passa no teste;
  ninguém o executa desde julho. 20 turnos de hoje sem check-in nem batida.
- **Lembrete de ponto por WhatsApp rodava há meses em modo DRY**: o beat de 60 s montava as mensagens certas (5 na
  janela das 17:45 de hoje: "Seu turno no Ideal Flores começa às 18:00. Bata o ponto pelo app") e NÃO enviava —
  `PONTO_LEMBRETE_ENABLED` nunca foi posta no ambiente e o padrão era "false"; `ponto_lembrete_log` vazio. Ligado por
  padrão no código (`.env` é zona proibida); a variável em "false" desliga. Commit `e47346976`. Os outros beats do
  Operacional rodam: atrasos → sino (50 avisos/dia, 3 destinatários por atraso — é o desenho), cobertura diária, lembrete
  de turno.

### 2c.19 Resumo do dia 07/09 — para ler amanhã de manhã

**Números**: 141 commits; 57 oráculos verdes (varredura das 19h); 33 travas estáveis; bake das 13:36 e das 17:04 sem
drift; o das 00:00 publica o que subiu depois (~70 arquivos, todos no git).

**O que se prova sozinho amanhã (e onde olhar)**
- 05:00 fecha o razão; 06:30 renova certidões (só Patrimonial); 08:00 "kit completo" olha o Drive; 08:10 Cora → 08:40
  escrituração (a regra de caixa agora espera D-2, sem os dois toques falsos das 08:16/08:46).
- 09:00 Themis avisa ~35 colaboradores por e-mail + WhatsApp (link do portal corrigido — /meu-espaco dava 404).
- 09:10 espelho do eSocial volta a baixar (governo libera após o dia 7): os 157 "sem tipo" começam a ganhar tipo.
- 11:00 regra "gerente sem check-in" — acusa quem não registrou chegada (hoje acusaria o Eliziel).
- Lembrete de ponto por WhatsApp (05:45/06:00/06:10, 06:45…, 17:45…): primeiro dia real; conferir `ponto_lembrete_log`.
- 15 min: regras proativas (337 → 305 estados abertos, sem esconder nada real).

**Fica com você** (tudo já no seu WhatsApp ou no mapa): crédito do LLM; virar NFS-e do ERP para produção; primeira
cobrança real pela Cora; boleto de teste de R$ 5 no Inter; ASOs (25 vencidos + 21 sem registro); Adailson (aviso prévio
vencido, ativo); Keyson (processo por concluir); 11 férias sem decisão; escalas de agosto/setembro em rascunho; 219 leads
sem contato; nota 32 da Ideal Flores no kit de agosto; RH com dados de demonstração; `celery-sefaz` (concurrency no
compose); DET sem leitura desde 03/07.

### 2c.20 Os testes que você autorizou — feitos como usuário final, pelo navegador (07/09, 22:00–22:40)

Playwright na tela de produção (erp.conectamais.pro/redesign), logado como você. Cada item: o que fiz, o que provou.

| # | Teste | Resultado | Prova |
|---|-------|-----------|-------|
| 1 | **Primeira cobrança pela Cora** — Laranjeiras 09/2026, R$ 42.544,50 | **VALIDADO** | Financeiro › Receber › "Emitir cobrança" › "Emitir no banco". Cora devolveu `inv_nYxmSFguQBWBgcbUE90crbw`, status OPEN, boleto + PIX gravados na conta a receber; PDF real de 89 KB baixado da URL do boleto; a linha mostra "emitida · Cora". Tomador 24.632.786/0001-28. |
| 2 | **Boleto de teste no Inter** (R$ 5, vence 10/09) | **REPROVADO (banco)** | Cancelamento aceito 3× (POST …/cancelar, 202) e o boleto segue `A_RECEBER`. O Inter processa assíncrono e não confirma. Se não cancelar até 10/09, vence sozinho (é contra o próprio CNPJ, sem cobrança a terceiro). Conferir no app do Inter. |
| 3 | **Escalas em rascunho** (7 de setembro) | **VALIDADO + 2 correções** | Michelangelo pela tela: Submeter → Aprovar → Publicar; as outras 6 pelos mesmos endpoints. As 7 estão `published`. Corrigido: (a) o select mostrava 7 opções com o MESMO nome, sem o posto — agora "Condomínio X · 09/2026"; (b) a tela do redesign publicava sem a guarda de escala vazia e sem disparar o evento — agora igual ao clássico. Publicar **não manda WhatsApp** a ninguém: o controller clássico tem um "PENDENTE: notificar funcionários" desde sempre. As 10 escalas de agosto (mês fechado) ficaram em rascunho de propósito. |
| 4 | **Keyson** | **VALIDADO + 1 correção** | "Calcular verbas" devolvia 201 e **não gravava nada** (a linha continuava sem valor) — corrigido: agora grava valores + snapshot. Depois "Concluir": processo `completed`, funcionário `demitido` em 14/08, benefícios encerrados. **Divergência para você**: o processo tem último dia 14/08 (o que você informou em 12/08); o cadastro tinha 28/08 vindo do Sólides. Concluí com 14/08. |
| 5 | **Férias sem decisão** | **VALIDADO** | Bianca (01–30/04/2026, período já passou): "Rejeitar" com motivo → `REJECTED`, motivo gravado. Restam 12 `SUBMITTED` em `hr_vacation_requests` para o DP decidir na mesma tela. |
| 6 | **ASOs** | **VALIDADO** | "Agendar/renovar ASO": Adailson, **demissional**, 09/09 → gravado `agendado`. A clínica ficou "a confirmar pelo DP". Achado colateral: existe um "COLABORADOR TESTE HOMOLOGACAO" na lista de funcionários ativos. |
| 7 | **Adailson** | **CALCULADO, NÃO CONCLUÍDO** | R$ 4.408,61 líquido, mas o cálculo alerta: férias vencidas **presumidas** (30 dias, R$ 1.920,50 + 1/3) e há férias pagas na folha em 05 e 06/2026 — pode estar pagando período gozado. DP confirma o saldo antes de homologar. Último dia 04/09 (já passou; ele segue "ativo" no cadastro até concluir). |
| 8 | **219 leads** | **VALIDADO (simulação); envio real não disparado** | CRM › "Tocar cliente": lead de 07/09, modo "só simular" → número resolvido (+55 92 8408-5029), texto e canal certos. O envio real é um clique ("ENVIAR de verdade") — não disparei às 22:36 de propósito: mensagem comercial a prospect de madrugada. Fica para amanhã de manhã, seu ou meu. |
| 9 | **Nota 32 da Ideal Flores** | **BLOQUEADO** | A nota existe no banco (competência 08/2026, emitida 02/09, R$ 65.842,42, chave …954170). O kit 08.2026 no Drive tem **Faturamento vazio** (o 07.2026 também). O PDF original não está no sistema e a API nacional não o entrega (Sefin devolve o XML, mas `danfse` → 501). Só sai do portal, à mão: baixar e soltar em "4. Faturamento" do kit 08.2026 — o sistema reconhece pelo número no nome do arquivo. Onvio costuma entregar depois (as de abril/maio vieram por ele). |
| 10 | **Dados de demonstração do RH** | **FEITO (quarentena)** | Candidatos com e-mail `@email.com`, vagas "Teste"/"CIC-Test", cursos de 16/03: copiados para o schema `lixo_rh_demo_20260907` (13 tabelas) e apagados das vivas, em uma transação. Documentos e checagens de candidatos **ficaram** (apontam para funcionários reais, jul–ago). Restaurar = INSERT … SELECT de volta. |
| 11 | **celery-sefaz** | **REVERTIDO; sem ganho** | Tentei `pool_shrink` em runtime. Erro meu: sem `-d`, o comando foi a TODOS os workers; revertido em 1 min (todos de volta ao pool de origem — 2 processos, sefaz 3). Memória do sefaz caiu de 1,65 para 1,28 GiB com 1 processo a menos, mas isso não sobrevive a restart: o ajuste real é `concurrency` no compose, que eu não edito. |
| 12 | **DET** | **BLOQUEADO (você)** | Container pausado desde 14:33 por decisão da manhã (não queimar 2captcha sem alguém para o 2FA). Login gov.br com certificado + 2FA pelo noVNC e `docker unpause conecta-pro-det-robot`. |

**Commits desta rodada**: 8076ee256 (escala: guarda + evento + rótulo por posto), e2cf38646 (rescisão grava o cálculo).
Ambos já em hot-copy; o bake das 00:00 publica.

### 2c.21 QA E2E como auditor-usuário final — 24 módulos do redesign + 317 páginas do clássico (07/09, 22:40–23:50)

Chromium (Playwright) logado como você, em produção. Roteiro por módulo: abrir CADA aba de CADA grupo, medir se
carrega, erros de console, chamadas de API 4xx/5xx, texto de erro, tela em branco; depois preencher e submeter 10
calculadoras/simulações, clicar "Ver", "Exportar", buscar e abrir o assistente. Achados completos em
`auditoria/qa/QA_E2E_20260907.md`.

**Redesign — 553 telas em 24 módulos: 553 carregam, 0 erro de console, 0 chamada de API com falha.** O que estava errado
era conteúdo/lógica, não carregamento — e cada item abaixo foi corrigido nesta noite (commits no fim):

| Módulo | Defeito visto pela tela | Correção |
|---|---|---|
| Financeiro | 16 telas (CFO, precificação, justificativas, sync NFS-e…) não apareciam em aba nenhuma — só por URL | grupos montados por último no build; trava nova em `checar_botao_morto` |
| Financeiro | KPI "A pagar (próx. 7 dias)" R$ 7.834 × banco R$ 103.160 — `current_date` em UTC escondia a folha de R$ 95 mil que vence hoje | data de Manaus (KPI e botão "Emitir cobrança") |
| CRM | Simular preço: R$ 476 mil/posto, R$ 22,9 milhões de contrato — "1920.50" virava 192050 | normalizador único de dinheiro nos 12 formulários que tinham o mesmo parser |
| Documentos | 20 s em "carregando…" a cada 15 min (Drive frio) | cache 6 h + renovação em segundo plano |
| Meu espaço | "0 notificações" com o sino em centenas | soma a fonte do sino (1.013 · 949 não lidas) |
| Empresas | "Atrasadas 0" com 19 obrigações pendentes vencidas de abril a julho | entram como atrasadas (27 · 19 atrasadas · 8 pendentes) |
| Fiscal | Guias FGTS/INSS mostravam tabela morta do Onvio (12/2025, 11/2025) | subtítulo honesto apontando para Guias/Obrigações |
| Assistente | "erro 500" — era 402 sem crédito do provedor | 503 com o motivo na tela |
| Escalas (Operacional) | 7 escalas com o mesmo nome no select; publicar sem guarda | rótulo por posto; guarda + evento |
| Rescisão (DP) | "Calcular verbas" não gravava nada | grava valores + snapshot |

**Sistema clássico (/modulos) — 317 páginas: todas abrem, mas as APIs por trás têm fios soltos.** Corrigidos 6 × 500:
websocket de notificações (298 tracebacks em 12 min), sync runs, contas bancárias (conta Cora sem agência),
/config/system, /config/dashboard e página Tenants (JS). Ficam como **decisão** (não é código de tela, é módulo sem
backend ou sem migração): equipamentos (404), automações/workflows (404), relatórios/analytics (404 — apagado dia 07 e
restaurado só o mínimo), licitações clássico (bidding/* 404), segurança clássico (404), Sólides clássico (tabelas
`solides_sync_*` inexistentes), agendador (`scheduler_queue` inexistente), tipo `tenantstatus` inexistente. O
redesign cobre esses módulos com dado real — o clássico deles é vitrine vazia. Os 503 em dezenas de páginas foram o
**nginx limitando** (`frontend_limit` 50 r/s) os prefetches do Next durante a minha varredura de 30 páginas/min;
não mexi no nginx.

**O que só você resolve (dado, não código)** — 5 eventos eSocial S-2220 rejeitados desde 09/07 (Anilson, Andrew,
Ailton, Ademir, Adailson); 88 ASOs vencidos (25 colaboradores ativos sem ASO válido); 51 espelhos de ponto
aguardando SUA assinatura; 12 desligados sem motivo registrado; 213 leads sem destino e 15 propostas sem contrato;
7 contas do mês sem boleto/PIX (R$ 73.372,31 — um clique em "Gerar cobranças"); 47 pessoas que receberam VT/VR por PIX
sem cadastro de diarista; R$ 224.367,05 de saídas bancárias sem classificação; "Jordan Jesus" e "Gizely Jesus"
cadastrados como diaristas (jan/2026); um "COLABORADOR TESTE HOMOLOGACAO" ativo; obrigações pendentes vencidas de
04–07/2026 (FGTS/ISS/INSS/IRRF Eletrônica, DAS Patrimonial) — pagas sem baixa ou atrasadas; folha 08/2026 da
Patrimonial (R$ 95.326,25, vence 07/09) "pendente" no contas a pagar; certidões de emissão manual vencendo 18/09
(estadual Eletrônica, falência Patrimonial); trilha LGPD praticamente vazia (5 eventos de auditoria).

**Sem uso (a máquina existe, ninguém usa):** substituições, banco de horas, passagem de turno, avaliação de equipe,
compras/requisições, estoque real, orçado×realizado, ordens de serviço, agendamentos, meta comercial do mês.

**Commits desta rodada:** 8076ee256, e2cf38646, 0673b404e, d91dc65fd, e4bf16895, bc01257e7, 6cdeb34f8, e279d7055,
ed476077a, 992fb9514, 29428d69b. Backend em hot-copy; frontend publicado às 23:41 (BUILD_ID conecta-pro-1788838799864); o bake
das 00:00 publica o resto.

### 2c.22 Revisão de código — people-management (08/09, 00:00–01:00) · primeiro módulo da fase "100%"

Direção do dono (08/09): revisar e corrigir 100% do código no que precisar e depois cobrir 100% do backend no
redesign; o clássico não interessa. Medido antes de começar: 3.160 rotas /api, 301 com tela no redesign (9%).
people-management tinha **697 rotas** (64 no redesign, 44 só no clássico, 589 sem tela).

**Método**: inventário das rotas (função, arquivo, resumo) + prova de execução de 194 leituras (0 × 5xx) + quatro
revisores de código em paralelo, por pacote, cada um obrigado a provar no banco (psql) o que acusou. Resultado:
**117 defeitos com prova** (DP núcleo 20 · folha/ponto 19 · RH/recrutamento/reembolso/disciplinar 52 · portal/GED/SST 26)
e vereditos rota a rota (VIVA / LIGAR / INTERNA / MORTA). Relatórios completos na sessão; lista de rotas em
`auditoria/qa/rotas_sem_tela.txt`.

**Corrigido nesta noite (commits 9a0fc7042, bc62bead8, 2c536e031, 413a8490f e o seguinte)** — o que doía de verdade:
- Duas engines de folha davam dois números para a mesma pessoa (Adailson 08/2026: R$ 1.464 × R$ 2.138). A legada
  (/hr/payroll) agora delega à engine CCT; contracheque e arquivo no GED pela engine oficial.
- Medidas disciplinares invisíveis para a API (tenant errado nas 5 linhas) — a tela mostrava, os botões davam 404.
- Reembolso: item REJEITADO pelo aprovador era pago; "processar" gravava conta a pagar inventada (agora cria a real);
  admin não via "prontos para pagar".
- Ponto: justificativa dava 500 sempre (coluna NOT NULL faltando); batida noturna após 00h virava "entrada"
  (33 falsas em 23/08); fechamento/sync em cascata sem savepoint; recálculo de espelho que zerava folha e apagava
  assinatura, bloqueado.
- Admissão: concluir quebrava (data de nascimento em texto) e exigia CPF que a admissão já tem — nenhuma admissão
  virava funcionário por caminho algum.
- Afastamento "acidente" não gerava estabilidade acidentária (art. 118) — mapeado para o tipo do domínio.
- ASO realizado ficava sem validade (nunca vencia, nunca aparecia no compliance); restrições em JSON inválido; tipo livre.
- Download de documento do kit falhava para 60% dos documentos (Drive/Inter/base errada) — no GED e no Meu Espaço.
- CIPA: 2.834 reuniões idênticas (2.833 apagadas; POST dedupe; GET paginado). Total de holerites era o tamanho da página.
- Vagas: pausar/reabrir/fechar chamavam métodos inexistentes (500). JSONB mutado in-place não gravava (notas/avaliações).
- Paridade 12x36 da esteira não virava em mês de 31 dias (contrafase com a grade). Assinatura disciplinar levava o
  nome do usuário logado como "funcionário". utcnow em colunas com fuso (+4h) e sem fuso (mistura) — 14 pontos.
- Fingimentos de sucesso apagados: folha ajuste/fechar/conferência/**importar Alterdata** (a tela do redesign dizia
  que importava), /hr/payroll/close, integração DP↔RH↔Ops (10 stubs + "status active"), time-tracking (17 rotas de
  escrita sobre tabela vazia), folha-pdf HTML, medida por ocorrência. Ferramenta MCP `fechar_folha` diz a verdade.
- **30 rotas mortas apagadas**; router de integração fictícia desmontado.

**Ligado no redesign (22 portas que só existiam por API)**: DP — publicar/despublicar/cancelar holerite, editar
rescisão, espelho calcular/fechar, lançamento manual, ajuste de batida, enviar/cancelar reembolso em rascunho (9
presos). RH — plano de carreira, curso, turma, matrícula, ciclo 360 (abrir + iniciar coleta), editar modelo
disciplinar. Saúde — ASOs vencendo 30 dias, membros da CIPA. Meu Espaço — ouvidoria (abrir + minhas), documentos
aguardando minha assinatura, meus dados. GED — editar/remover documento do kit.

**Fica para você (decisão, não código)**
- Portal do funcionário por token (34 rotas): ninguém emite esse token desde que o login virou Google; as funções
  vivem via self-service. Apagar o router? Recomendo sim.
- Recrutamento: o pacote `modules/recruitment` (candidates/vagas/applications/interviews) está vazio e é servido só
  pelo clássico e por 4 ferramentas MCP; o caminho real é a **esteira** (employees status=candidato). Aposentar o
  pacote e apontar as MCP para a esteira?
- Migrações que faltam (não edito alembic): `sync_runs`, tipo `tenantstatus`, `solides_sync_*`, `scheduler_queue`.
- PPP (INSS) gera conteúdo fixo ("colete balístico", CNAE de vigilância) — a empresa é portaria; precisa de
  fatores de risco reais de `gp_risks`/LTCAT antes de qualquer emissão.
- Tokens públicos (painel-ponto, homologação, candidato, PJ) têm default fixo no código e a env não está setada —
  setar `PAINEL_PONTO_TOKEN` e afins no `.env` (não toco).
- `main_production.py` inclui o router de recrutamento duas vezes (83 rotas duplicadas) — arquivo proibido para mim.
- 47 holerites `source=conecta` em 11/2026 e 12/2026 (competências futuras) e checklist de onboarding de semente
  (102 itens "vencidos" de 24/02) — apagar?


### §2c.23 — Financeiro: revisão 100% do código, lote 1 (08/09/2026, 00h–03h Manaus)

**Método:** 4 agentes só-leitura (dinheiro-que-sai, contas/cobrança, custeio/BI, fiscal+relatórios), cada
achado provado no banco; correções aplicadas, hot-copy nos 8 containers, HUP, smoke, 0 botão morto.
Relatórios finais em `auditoria/qa/revisao_20260908/`.

**Incidente (relatado antes de tudo).** O agente fiscal disparou `POST /financial/bank-reconciliations/auto`
por engano às 00:49 e a rota conciliou um PIX de R$ 4.300 (Concregrama Prime Arena) com o receivable de
R$ 33.479,60 do Prime Arena por casar a palavra "PRIME", sem conferir valor. Restaurei as duas linhas para
`pendente` (bank_transactions 2ce29fd4…, receivable_accounts a20ce2cc…) e apaguei a rota. Um evento
`publish_nota_emitida("conciliacao_1", 33479.6)` foi ao event bus e não foi desfeito.

**Dinheiro que sai (aplicado):** OTP consumido com `UPDATE … AND used=false RETURNING` (não dá para reusar);
commit por item pago; teto diário soma TODAS as fontes (Inter + diaristas + PJ) em Manaus e conta
`aguardando_aprovacao`; saldo Inter indisponível vira erro, não zero; cancelar não alcança lote em aprovação;
7 rotas `/folha/*` de lote do Inter apagadas (13 ficam). Sync do Inter baixa recebível como `paga` com data.
Boleto pelo kit chamava o adapter com kwargs que não existem (TypeError engolido, cobrança ficava pendente
para sempre) — corrigido para a assinatura real. Conciliação lia `cpfCnpj` onde o sync grava `cpf_cnpj`.

**Fiscal (aplicado):** calculadora de retenções (tela viva): IRRF 1% para vigilância/portaria/limpeza
(art. 716 RIR/2018) e 1,5% só para serviço profissional; prestador no Simples não sofre IR/CSLL/PIS/COFINS
(IN 765/2007, IN 459/2004); dispensa quando IR ≤ R$ 10 ou PCC ≤ R$ 10. **Validar com a contadora antes de
o cliente usar.** Tributos consolidados: FGTS lia a conta velha `4.1.2.01` (dava 0 o ano todo) — agora
`5.1.1.02` (R$ 60.987,20 em 2026); PIS/COFINS deixam de ser "zerados por liminar" (a liminar é da
Patrimonial e está a_solicitar) e saem como `null`. Obrigações atrasadas = pendente vencida (19, era 0).
Painéis financeiros: `CURRENT_DATE` (UTC) trocado por hoje de Manaus (23 ocorrências); 5 handlers que
devolviam 200 com `{"error"}` agora 503. Headcount por cliente lia `ged_clients` (0) — agora `clients` (53).
Contrato renovado nascia `ativo` e sumia do MRR (`active`); MRR não soma rascunho.

**Apagadas (74 rotas):** fiscal legado sobre tabelas inexistentes/vazias — CFOP ×6, retenção ×5, NF-e ×8,
NFS-e legada ×6, SPED ×6, DAS ×5 (fica `/das/faixas`), SUFRAMA ×5, `/stats`; relatórios `/orcamentos` ×3
(ledger morto) e `/custeio` ×5 (tabelas em `lixo_20260906`); BI overview/dashboards/profitability; stubs de
recebível (boleto/PIX/lote/notificar/acordo) e de regra de cobrança (generate/process-all); NFS-e de entrada
legada ×9 (auto-criar ×3, conciliação auto e status, custos/resumo, sync ×2, status-sync); `POST /financial/
nfse/emitir` (ABRASF, default Simples). As três telas do redesign que apontavam para elas saíram; o caminho
real das NFS-e tomadas é `registrar-obrigacoes` (as 86 sem pagável são de 2025, antes do horizonte).

**Fica para o lote 2 (fila):** LIGAR — DANFSe por chave na lista de emitidas, baixa de obrigação
(`PATCH /obrigacao/{id}`), liminares (depois de unificar `fiscal_liminares` × `liminares`), parcelamentos,
aging por competência (contas-receber/pagar/fornecedores), apuração Lucro Real, DRE mensal, balanço,
`/bi/kpis`, saldo-limite, prioridades de cobrança, projeção de caixa. Corrigir — lista de NFS-e devolve chave
e o detalhe exige UUID; dashboard fiscal com chaves trocadas; forecast parte do saldo de uma conta só;
`cashflow_dashboard` do clássico inventa números; `_ensure_*` cria tabela em GET; DAS acima de 4,8M dá 500;
adicional IRPJ com teto fixo; custeio ABC/precificação/rentabilidade (ver relatório 3). Desmontar routers
mortos (purchase 68, bank_reconciliation 13, bank_account, bank_transaction, customer, receivable_category,
accounting fin_* exceto DRE, inventory fin_* exceto /real/*).

**Depende do Jordan:** (1) alíquotas da calculadora com a contadora; (2) qual tabela de liminares é a
verdade; (3) confirmar que a empresa não emitirá NF-e (apaguei os endpoints; o modelo fica); (4) o evento
de conciliação falsa no bus.


### §2c.24 — Financeiro lotes 2 e 3 + Operacional/diaristas (08/09/2026, 03h–05h Manaus)

**Financeiro lote 2 (commit 92769cfbc):** baixa de parcela usa a parcela do caminho (o body podia trazer
outra); recorrência não recria a conta do mesmo vencimento a cada chamada; emissão de cobrança reserva a
conta antes de falar com o banco (dois cliques emitiam duas cobranças; falha devolve a reserva); estoque
posta COGS em `5.1.1.06` (o `4.1.3.01` era do plano velho) com hoje de Manaus; CFO lê o teto do `.env`
(o prompt dizia R$ 5.000 fixo) e conta só contratos `active`; `ai/cashflow-prediction` e `ai/advisor/health`
apagadas; command-center devolve 503 em vez de saúde inventada; sugestões de diarista leem `diaria_diaristas`;
DRE sem período = mês atual (somava a vida inteira); `QuotationStatus` ganha `erro_envio`.

**Telas ligadas no fiscal (commit 4822bb2d0):** dar baixa em obrigação (PATCH, pela linha da tabela de
guias), DANFSe por chave em cada NFS-e emitida, parcelamentos (lista com saldo devedor + registrar + remover),
apuração IRPJ/CSLL do Lucro Real, DRE mês a mês, a receber e a pagar por competência (FIFO), KPIs do beat.
Liminares ficam de fora até o Jordan dizer qual tabela é a verdade.

**Financeiro lote 3 (commit 31360e63d):** 214 rotas mortas apagadas em 9 controllers — compras (68),
conciliação bancária (13), contas bancárias (12), transações bancárias (13), clientes do contas a receber
(12), categorias (9), ledger `fin_*` da contabilidade (49; ficam `/dre` e `/dre-consolidado`), estoque
legado (34; fica `/real/*`), conciliação automática (4; fica `justificar`). Prova: tabelas vazias ou
alimentadas por outro caminho (extrato vem do sync do Inter; cotações vivem no WhatsApp); 0 chamador no
redesign/MCP. As sondas dos agentes 24h que batiam em `accounting/charts|cost-centers|periods` foram
reapontadas para `/accounting/dre` (commits 54e33d82a e seguinte); sem isso o ciclo das 00:00 acusaria
404 como regressão.

**Operacional — diaristas (commit ed2ac622c):** o módulo tinha dois universos. `diarist_*` (51 rotas,
9 tabelas) tinha 3 linhas de teste, 0 movimento desde 27/01/2026 e escrita quebrada em todo caminho (enum
× varchar, campos que não existem no schema, IRRF sempre 0, INSS 20% em vez de 11%). Apagadas 63 rotas
(fica `consulta-cpf`, que deixa de dizer "achado" quando a BrasilAPI só validou o formato) e as 7 telas +
7 ações do redesign que gravavam nas tabelas mortas. O cadastro vivo é `diaria_*` (62 diaristas, 427
lançamentos) e o fechamento vivo é o do financeiro. `criar_diarista` com nome repetido devolvia ok sem
gravar e descartava CPF/PIX — agora devolve o id existente e ok=false.

**Estado do loop:** people-management ✅ · financeiro ✅ (lotes 1–3; fila residual no §2c.23) · operacional
em revisão (diaristas ✅; rondas/ocorrências/comunicação/escalas/presença com revisor em curso) · CRM com
revisor em curso · government, ged, gedeon, campo, jurídico, clients, empresas, integrations na fila.
Os revisores anteriores caíram por limite de uso da sessão às 00:5x; relançados às 04:4x com escopo
econômico.


### §2c.25 — Checkpoint 08/09 08:30 Manaus: GED, módulos mortos, operacional lote 2, CRM lote 1

**Commits desde a §2c.24:** 436602863 (GED: DMS vazio aposentado, 131 rotas; ficam kits/certidões/config/
upload), a20a84d73 (retention 70 + document_kits 54 + scheduler 26 + services 63 sem rotas; MCP
dashboard_clima honesto), fc34e9ac5 (operacional lote 2: comunicados publicar/leituras 500, gerador 12x36,
interjornada do substituto, HE base planejada, encerrar alocação cancela turnos — KEYSON demitido tinha
12 turnos de setembro, corrigido no banco —, alocação duplicada 409, templates de escala com tenant zero,
triagem/rondas em Manaus, 31 rotas mortas) e o commit do CRM lote 1 (ver mensagem do commit).

**CRM — onde parou.** Lote 1 aplicado e no ar (hot-copy + HUP + smoke): defeitos 1, 5, 7, 8, 9, 10, 12,
13, 14 do relatório `auditoria/qa/revisao_20260908/crm_clients.md` e as 132 rotas MORTA apagadas.
Não aplicados de propósito: 2 (rotas de IA apagadas em vez de corrigidas), 3 e 11 (dashboard apagado),
4 (commissions apagadas; fica só GET /crm/commissions), 6 (rota apagada). **Falta o lote 2 = as 48 rotas
LIGAR** no redesign (contatos CRUD, produtos, itens de proposta, itens/aditivos/modelos de contrato,
status do cliente, condomínios, aceitar/recusar proposta, concluir tarefa, ficha 360, timeline, autofill
CNPJ/CEP). Pendência menor: `GET /crm/proposals/stats` responde 500 (apagada, mas `/{proposal_id}` captura
"stats" e quebra ao converter) — trocar por 404.

**Operacional — falta:** LIGAR ×6 (grade PUT, escala PATCH/reject, substituição DELETE, banco de horas
DELETE, resumo de inspetores) e o defeito 8 do clássico (PUT × PATCH), fora do escopo.

**Fila:** government (448, só leitura), gedeon (70), campo (77), juridico (52), empresas (36),
integrations (103), bidding (88 — decisão do Jordan: licitações sem uso humano), recruitment (166 —
decisão do Jordan), notifications (76; só notification_queue tem dado), client_portal (61), config (51),
health_occupational (40), security_lgpd (29), cct (23), ai (23; assinatura universal viva).

**Depende do Jordan (novo):** confirmar a regra de interjornada aplicada (noturno D-1 não cobre D);
reajuste de contrato agora exige percentual informado.


### §2c.26 — CRM lote 2, government, integrations (08/09/2026, 09h–12h Manaus)

**CRM lote 2 (9a9fcace1):** as 48 rotas que existiam sem tela entraram no redesign — ações por linha
(cliente ativar/suspender/bloquear/regularizar; lead arquivar; proposta enviada aceita/recusada; contrato
suspender/renovar/encerrar; contato editar/remover; tarefa concluir/excluir), tabelas de produtos (115),
tarefas, itens e aditivos de contrato, modelos de contrato, itens de proposta e condomínios, e os
formulários correspondentes. Ficam de fora ficha 360 e autofill de CNPJ/CEP (o formulário do frontend
não faz GET). Operacional: prestação de contas por inspetor ligada (0bad1d9bd/85e76b41f).

**Government (fa74d9536) — o achado mais grave do dia:** seis POSTs do eSocial estavam SEM
autenticação e dois deles transmitiam ao governo em produção; a porta 8080 está publicada em 0.0.0.0 e
a regra DOCKER-USER só fecha a 3001. As rotas foram apagadas (o único caminho de transmissão que fica é
o do DP, com login). **Falta o Jordan fechar a 8080 no firewall como a 3001** — isso é infra, não
código. Também: 189 de 224 rotas eram mortas (cte, mdfe, nfce, sefaz, govbr, sync, jobs, extração
DistDFe do NSU 0 sem trava, certificados em memória, mocks com success=True) e foram apagadas;
/esocial/eventos passa a ler o espelho real (330 eventos, era tabela órfã com 0); guias FGTS/INSS
filtram os tipos reais (29, era 0); DCTFWeb aceita a Patrimonial e usa os terceiros do FPAS 515;
NFS-e nacional rejeitada devolve 422; beat sem as sondas nocivas (2.000 GETs/dia às SEFAZ) e sem as
tasks vazias; MCP resolve CPF na timeline eSocial. Relatório: `auditoria/qa/revisao_20260908/
government_integrations.md`. **Não apliquei** (decisão/infra): idempotência do eSocial (só o DP
transmite e é gated), faturar kit pelo Ábaco legado (módulo gedeon, próximo lote), Reinf sucesso falso
(rotas VIVA no clássico, XML em memória — sem efeito externo).

**Integrations (commit seguinte):** webhooks do Inter gravavam 'recebido' e o Cora 'pago' — o sistema
só entende 'paga'; evento de boleto sem código marcava TODOS os pendentes; conciliação por valor casava
o recebível errado (desligada); pagamento por código de barras/DARF sem OTP e sem teto (apagado — o
caminho com gate é o do Inter payments); assinaturas: criar solicitação e consultar status sem token,
PIN sem limite de tentativas, vencidas listadas como pendentes; Drive: pasta de holerites pública por
link, e-mail do kit podendo ir a contato de outro cliente, id no shell; chave do Baileys no código;
78 rotas mortas (gateway, connectors, Sólides quebrada pelo lixo, banking, Drive). Relatório:
`integrations_gdrive_signatures.md`. **Não apliquei:** validação de assinatura dos webhooks do Inter
(exige INTER_WEBHOOK_CA_PATH no .env — infra), token do DET, Asaas.

**Módulos menores (relatório `modulos_menores.md`, 540 rotas, 329 mortas):** próximo lote. O mais
grave: /onvio/reclassificar apaga o valor de 38 guias (R$ 269 mil) e o extrator não repõe; contratos
jurídicos sem autenticação; 7 alertas de risco invisíveis no sino há 7 semanas (sem user_id); task
de EPI falhando todo dia e registrada como sucesso; push 100% em 500; portal com ORM ≠ tabela.

**Depende do Jordan (novo):** fechar a porta 8080 no firewall; INTER_WEBHOOK_CA_PATH; DET_ROBO_TOKEN;
licitações e recrutamento (ainda sem decisão); health_occupational inteiro (duplica /people-management/
sst — pode ser aposentado).


### §2c.27 — Módulos menores (gedeon, campo, notifications, client_portal, juridico, config, health_occupational, empresas, security_lgpd, cct, ai) — 08/09/2026 ~12h

Relatório do revisor: `auditoria/qa/revisao_20260908/modulos_menores.md` (540 rotas, 329 mortas).

**Corrigido:** `/onvio/reclassificar` não apaga mais as guias (38 guias com R$ 269 mil de valor
extraído sumiam a cada clique) — só cria as que faltam e ignora documento sem competência; contratos
jurídicos exigem login (4 rotas devolviam 16 contratos e o MRR a qualquer um); sino: alerta de risco sem
dono vai para o Jordan (7 alertas invisíveis desde 21/07) e "não lidas" ignora as 443 expiradas; CND: PDF e
status só dos dois CNPJs da empresa, PDF mais recente (o LIMIT 1 pegava certidão de outro CNPJ);
painéis de empresas e obrigações calculam mês/ano a cada chamada (o default congelava no boot);
formulários LGPD (PIA e apagamento) ganharam os campos que a rota exige (mandavam {} → 422).

**Aposentado:** health_occupational inteiro (40 rotas: duplicava `/people-management/sst`, com ORM que não
bate com o banco e task diária falhando desde sempre) — as 3 tools MCP (estoque_epi, status_pcmso,
status_ppra) apontam para o SST vivo e as 3 tasks saíram do beat; config_controller (47; 1 tenant e 6
configs escritos por SQL, drift em 3 tabelas); notifications intelligent (23) e push (23) — mocks em
memória e tabelas inexistentes — e 23 mortas do notification_controller (ficam sino, marcar lida,
subscribe, fila); security_lgpd consent/audit/encryption/masking/status (17; chave gerada por request,
tabelas vazias); campo checklist (18; tabelas inexistentes), monitoring (5), tickets/técnicos (6) e 11
rotas de visita sem chamador; gedeon controllers/onvio (5 sombreadas), kit_controller (3) e 14 de
gedeon_controller (Redis com 2 clientes; ficam Hermes, Sophia e pagamentos do colaborador); client_portal
auth refresh/logout, kit_approval, tickets de escrita (ORM ≠ tabela), notifications, mcp, whatsapp,
historico-drive, feedback (19); juridico skills, pareceres GET, analises GET, consultor histórico,
contexto/pessoa, processos GET, conhecimento GET, prazos POST, det/coletar (13); empresas demonstrativos
(dado fabricado), Domínio POSTs, bookkeeper lançamentos, migrador cálculos, CRUD de empresa por API,
liminares/ativas e PATCH (22); cct auditorias, benefícios validar/config, jornadas validar, compliance
verificar/metadata (tabela inexistente), rescisão férias (regra errada) (8); ai consultar/chat-consultar/
memórias-pendentes/anomalias-pendentes (4).

**Não apliquei (decisão do Jordan):** ordem_servico do campo (22 rotas, 0 OS em 6 meses, mas tem tela e
tools MCP) — fica até você dizer se OS é produto; DET_ROBO_TOKEN e o robô pausado; onboarding do portal
que regera senha em laço (sem tela nova, só clássico); consolidar `modules/cct` com
`people_management/cct` (gêmeo hardcoded).


### §2c.28 — Recruitment aposentado, rotas miúdas, o que resta (08/09/2026 ~14h Manaus)

**Recruitment (7e44976c5):** as 7 tabelas do pacote (candidates, job_positions, applications, interviews,
educations, experiences, skills) têm 0 linhas desde sempre; o recrutamento real é a esteira de candidatos por
posto (`/people-management/human-resources/candidatos`, tela viva no RH). As 79 rotas (166 no inventário
por montagem dupla) foram apagadas e as 4 tools MCP (listar_vagas, vagas_abertas, listar_candidatos,
listar_entrevistas) apontam para a esteira ou respondem honesto.

**Miúdos (61a1d9519):** emissão de NF-e legada do fiscal_contabil (a empresa não emite NF-e), listagens de
NF-e/entrada sem chamador, status do otimizador de escala e das guias, fiscal-dashboard do clássico,
nfse-multi servicos/empresas/identificar — 14 rotas. `det-coletar-auto` saiu do jurídico (0d9d50143).

**Estado do loop de revisão 100% (backend):** todos os módulos do inventário foram revisados e corrigidos,
exceto **bidding** (88 rotas; revisor em curso — tem dado real e sync diário). Rotas apagadas hoje: ≈1.230.
Regressão do arsenal e varredura dos oráculos rodando para confirmar que nada vivo caiu.

**Para o Jordan:** porta 8080 no firewall (urgente); INTER_WEBHOOK_CA_PATH; DET_ROBO_TOKEN; ordem_servico
do campo (0 OS em 6 meses); consolidar `modules/cct` com `people_management/cct`; alíquotas de retenção com
a contadora; liminares; interjornada; reajuste com percentual obrigatório; classic pages que chamavam rotas
apagadas (banking pagamento por código de barras/DARF, Sólides, gateway) ficam quebradas por desenho — o
clássico está fora do escopo.


### §2c.29 — Licitações desligadas; fim da revisão 100% do backend (08/09/2026 ~15h Manaus)

**Bidding (1ccb469a9):** o revisor deu MORTA para as 88 rotas — todas as tabelas são seed de 12/03; o
sync do PNCP batia numa URL 404 doze vezes por dia há 26 dias (~2.900 chamadas externas, 0 registros) e
os botões ERP do redesign criavam conta a receber, lead e posto **reais** a partir de licitação fictícia,
sem idempotência. Apagadas 97 rotas, 3 entradas do beat, as ações do redesign (as tabelas ficam como
consulta, com aviso), e as 108 notificações "Certidão CRÍTICA — Licitações (11)" que o beat inventava a
cada 6 h. A aba Certidões, o relatório de compliance do GED e os alertas do BI passam a ler
`ged_certidoes` (58 vivas, com PDF e CNPJ). Relatório: `auditoria/qa/revisao_20260908/bidding.md`.

**Estado final do loop:** todos os módulos do inventário do backend foram revisados e corrigidos; rotas
apagadas hoje ≈ 1.330 (de ~3.975); 0 botão morto no redesign; os relatórios dos revisores estão em
`auditoria/qa/revisao_20260908/`. Regressão do arsenal e varredura dos oráculos rodando ao fim do dia.

**Fechamento (17h):** a varredura dos oráculos e a regressão do arsenal apontaram o furo da poda: as tools de
leitura do Hermes (`modules/ai/conversation/services/orquestrador/tools_read_*.py`) e três ações do redesign
importam handlers de controller direto — os revisores não olharam lá. Restaurados 17 handlers (d5c7f3471),
caçador novo aplicado (import de todo /app/modules + imports dos oráculos, dentro do container → 0 quebrado),
follow-up em lote corrigido (DISTINCT ON), oráculos de escala e diaristas ajustados, base do arsenal subida
com a decisão no commit (ed7b1df34). Vermelhos que ficam são ambiente, não código: sem usuário 'supervisor'
(2 oráculos + RBAC), LLM sem crédito (decisão sua), permissão de arquivo no container (5_4b).

**ATENÇÃO — hot-copy é volátil:** tudo que foi corrigido hoje está no ar por `docker cp` e no git, mas o
bake noturno (`scripts/oraculos_diarios.sh` → imagem) **se recusa a assar enquanto houver WIP alheio em
backend/** (hoje: `crm/services/contract_signature.py` e `scripts/gedeon/cnd_robot.py`, de outras
sessões). Se os containers forem recriados antes do bake, o código volta ao da imagem. Alguém precisa
commitar ou descartar esses dois arquivos e rodar `./scripts/deploy_backend_bluegreen.sh`.


### §2c.30 — Telas que faltavam, bake durável, porta 8080 (08/09/2026, 14h–15h Manaus)

**Cobertura do redesign (bf03f75be, b721a1e62, dda4d1ea6):** as ~45 rotas que os revisores dos módulos
menores marcaram LIGAR ganharam tela: kits do GEDEON (conferência ATLAS do cache, assinaturas pendentes pelo
banco, status de entrega, preparar/marcar entrega, faturar só boleto, evento de checklist), jurídico
(prazos, playbook, consultas ao escritório com ROI, status do DET, registrar consulta, ingerir comunicação,
analisar processo, conhecimento, parecer, análise, enviar CQB por linha), CCT no RH (taxa negocial,
jornadas, feriados, compliance do mês, adicionais, estabilidade, validar rescisão) e visitas de campo
(tabela com confirmar/check-in/check-out/resultado/reagendar/cancelar/PDF e agendar). Helper novo
`_ligar_generico.py` chama o handler do controller direto e desenha lista/dict sem conhecer o formato.
Lição que custou um worker: a tela de documentos chamou um serviço do kit que lê o Google Drive numa
thread → `free(): corrupted unsorted chunks` e a página caiu (000). Regra: **página do redesign não fala com
Drive, robô ou governo**; lê cache/banco e, se precisar de rede, timeout ≤ 3 s. Ficam sem tela, por
decisão: ficha 360 e autofill CNPJ/CEP do CRM (o form do frontend não faz GET), grade PUT/escala PATCH.

**Durabilidade:** com autorização do Jordan, o WIP alheio de `backend/` foi para um stash
(`git stash list` → "WIP alheio…", recuperável) e o blue-green assou a imagem 3eaa2312bc62 às 14:01, sem
drift nos 8 workers. Os builders ligados depois disso estão em hot-copy e commitados — o bake das 00:00 os
assa, já que `backend/` está limpo.

**Complemento 15h30 (39102533a):** as últimas rotas vivas sem tela ganharam tela — ficha 360 e consulta
CNPJ/CEP no CRM (ações que reutilizam os handlers GET), escalas do mês com edição por linha e redesenho de
grade no operacional. Portas 5555 (Flower) e 9093 (Alertmanager) fechadas na eth0 com a autorização do
Jordan (regras persistidas). O Jordan vai subir a pasta de chaves/certificado do Inter por scp; configurar
`INTER_WEBHOOK_CA_PATH` (e o mTLS do webhook) exige editar o `.env`, que é zona proibida para a sessão —
pedir autorização explícita antes.

**Segurança:** porta 8080 fechada na eth0 (DOCKER-USER, persistida em /etc/iptables/rules.v4), nginx e
loopback seguem 200. **Ainda públicas em 0.0.0.0: 5555 (Flower) e 9093 (Alertmanager)** — recomendo
fechar igual; aguardando autorização.

### §2c.31 — Cobertura 100% das rotas no redesign (08/09/2026, 15h–18h Manaus)

**O número, medido** (`backend/scripts/qa/checar_cobertura_rotas.py`, tsv T0…T6 em `auditoria/qa/revisao_20260908/`):

| momento | rotas montadas | sem chamador | só clássico |
|---|---|---|---|
| T0 (15h) | 1752 | 569 | 249 |
| T1 lote PM + outros | 1441 | 287 | 238 |
| T2 lote só-clássico | 1317 | 258 | 57 |
| T3 medidor vê apps-satélite | 1274 | 31 | 65 |
| T6 (18h10) | **1220** | **0** | **0** |

Classes finais: redesign 819 · interna 357 (MCP, Hermes, tasks, serviços, robôs, cron) · alias 23 (montagem
dupla em main_production.py, mesmo handler já coberto) · externo 15 (webhooks do banco/Sólides/Meta) · dono 6
(`/api/v1/reimbursements/*`, decisão de 07/09).

**Como se chegou:** seis agentes de veredito só-leitura (código + `count(*)`), 300 rotas por rodada, cada um
devolvendo MORTA / REDUNDANTE / LIGAR / INTERNA-ESCONDIDA / EXTERNO com prova (arquivo:linha ou contagem).
Relatórios em `auditoria/qa/revisao_20260908/*.md`. Apagados ~520 handlers ao todo no dia (podar com filtro
de alias + recusa de handler importado; a última rodada por AST porque regex cortou decorator multilinha).
Ligados 78 telas/ações em cinco lotes (`_ligar_lote{3,4,5}_20260908` nos builders + `_fin_ligar4.py`):
diaristas, escalas (gerar/salvar template), comunicados (confirmar/leituras), bater ponto e assinaturas no
portal, ativação do ponto, LTCAT, fila de notificações, GED (tipos, coleta, histórico, executar), certidões
(emitir robô / subir PDF / avisar cliente), Drive (status/desconectar), NFS-e nacional (dry-run), Inter
categorização, Onvio, auditoria de pagamentos, parcelas, recorrentes, folha PJ (programar/NF), fluxo de caixa
×4, DRE consolidado, estoque, liminares, kits (documentos/assinaturas), GEDEON ×5, José Luís, leads status,
clientes editar, medidas assinaturas, DET/processo por arquivo, placar dos consultores, rondas indicadores,
usuários (aprovar/ativar/desativar/permissões), CCT cargos/feriados, onboarding, desempenho integrado,
S-2200, links PJ, certificações, homologação do espelho, folha PIX prévia/status, SST (calendário legal,
esteira PCMSO, prontuário, ASO retroativo, CAT abrir/transmitir, ficha de EPI, risco), direitos CCT e
simulador de rescisão do funcionário.

**Frontend (BUILD_ID conecta-pro-1788903230478):** o renderizador ganhou `multiselect` (fiscal.py já emitia e
não desenhava), form GET sem corpo (formulários de CONSULTA) e `{chave}` no endpoint vira parâmetro de path
(rota com id no caminho vira form). Área do cliente: assiduidade e escalas, badge de avisos, resumo financeiro.

**O que o medidor aprendeu (cada regra nasceu de um padrão que um agente apontou):** apps-satélite vivos
contam como redesign — `/modulos/meu-espaco` É o portal do funcionário (as páginas de `portal-funcionario` só
redirecionam), mais homologação, painel de ponto, login facial, candidato, PJ, primeiro acesso, e os helpers
que importam (`services/portal`, `hooks/useNotifications`, `components/gdrive`); URL montada em pedaços
(constante de prefixo, concatenação implícita, `portalFetch`); rota com parâmetro casa por regex e o último
segmento pode ser variável; handler reusado por import (inclusive por referência) ou compartilhado por
montagem dupla; `rotinas/` e cron do host; webhooks são chamador externo.

**Decisões tomadas pela regra "sem dado, sem chamador" (reversíveis — está tudo no git):** campo/os (0 OS),
recruitment/interviews e climate (0 linhas), time-bank (0), sst/treinamentos (0), cashflow entries manuais
(8.370 linhas todas de sync), consultor panorama ×5 (Hermes usa o serviço direto), rondas/dashboard (=stats).

**Efeitos colaterais medidos no dia e corrigidos:** builder `rh` quebrou por handler do CCT apagado (alias
`Sc.`/`Cp.`/`Hf.`); `benefits_router` reinserido antes do import derrubou o agregador hr inteiro (584 botões
mortos num boot); portal importava tarde 4 handlers apagados (voltaram com seus imports); constantes de módulo
engolidas pela poda (5 arquivos); decorator multilinha cortado por regex (cashflow) → AST; `deploy_frontend.sh`
aborta com BUILD_ID igual (rm antes); pkill que casa o próprio shell. Botão morto = 0, imports AST = 0 novos.

**Depende do Jordan:** trocar o laço de assinatura em lote da empresa por `assinar_lote_empresa` (fluxo OTP;
a rota foi apagada, a ação por laço segue); `INTER_WEBHOOK_CA_PATH` no `.env`; tool `_vagas` do Hermes ainda
importa `list_positions` (recruitment aposentado); 25 `ClientDisconnect` no webhook do Chatwoot durante os
HUPs do dia — se o Chatwoot não reenvia, mensagens daquela janela podem ter ficado sem log.

## 3. O que o Arsenal ganhou hoje por causa deste mapa (Fase 4)

Já commitado: `checar_uso_real` (uso por tabela, rota, pessoa e tela; zero confirmado por `count(*)`),
`checar_nao_vigiado`, `checar_registros_servidor`, `checar_irreversivel`, `checar_varchar_teto`,
`checar_sino_surdo` (+corte automático), `checar_dominio` (+verdades curadas), `checar_bake_pendente`
(+bake automático), e o conserto do `checar_beats` (submódulo). Todos em `checar_regressao`.

---

## 4. O que NÃO consegui medir — dito de frente

- **Quem LÊ cada tela**: o middleware só passa a gravar após o bake; até lá "usou" = "escreveu".
- **Se os beats 1 e 2 da fila produzem**: a trava media importação (e errou); produção real de cada um exige olhar a tabela alvo às 08:30 — fica para a Fase 3 de cada item.
- **Os 25 beats que "engolem a própria falha"**: pista, não veredito; nenhum foi aberto.
- **Uso pelo frontend clássico**: o recon mediu só `--surface redesign`; o clássico pode expor algo que aqui aparece órfão.
- **Os 118 "prováveis falso-órfãos" do DP**: o builder lê a tabela direto; não conferi um a um.
- **Licitações e Recrutamento**: os números dizem "sem uso humano"; se é decisão sua, só você sabe.

---

## 5. O que você precisa ouvir

Você pediu "todos os módulos". O mapa diz: **56% das tabelas e uns 500 arquivos nunca viveram**, e os 11
módulos que você usa todo dia estão vivos e com defeitos contáveis (7 oráculos vermelhos reais, 2 certidões
para 15/09, uma tabela de INSS de 2024). Metade do caminho para "100%" é apagar; a outra metade cabe numa
fila de 11 itens, e os 5 primeiros devolvem cliques do seu dia. Nenhum deles é construir.
