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
