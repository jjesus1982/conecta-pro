# KPIs financeiros — defasagem e placeholders (item de conserto separado)

> Aberto por T4 em 2026-07-21 após o Jordan flagrar "Saldo Inter" exibindo R$67.757 (snapshot
> de 5 dias) quando o saldo real ao vivo era R$15.270,74. Investigação abaixo. **A raiz não é
> uma tela — é o pipeline de KPI.** As telas do redesign (raio-x/relatórios) só espelham
> `financial_kpis`; já ficaram honestas (mostram "não calculado" p/ o que nunca foi computado).

## Tabela `financial_kpis` — estado em 2026-07-21
| Código | KPI | Fonte no recalc | Situação |
|---|---|---|---|
| KPI-001 | MRR | `src_mrr` (soma clients.mrr) | ✅ calculado, correto (R$270.586,96) |
| KPI-002 | Saldo Inter | `src_saldo` (**API Inter ao vivo**) | ✅ agora correto (R$15.270,74) — estava velho só porque o job não firava |
| KPI-005 | Contratos Ativos | `src_contratos_ativos` (count status=active) | ✅ 10 (o "11" seria draft CTR-2026-00015; não conta) |
| **KPI-003** | **Compliance Lucro Real (100%)** | **NENHUMA** | 🔴 **placeholder — nada calcula. Precisa fórmula real ou remoção.** |
| **KPI-004** | **Inadimplência (17,04%)** | **NENHUMA** | 🔴 **placeholder — nada calcula. Um olhar cru nos recebíveis dá número bem diferente.** |
| **KPI-006** | **Score Saúde Financeira (68,5)** | **NENHUMA** | 🔴 **placeholder — nada calcula. Sem base.** |

## Causa raiz — duas coisas distintas
1. **Valores defasados (Saldo Inter, MRR, Contratos)**: o job agendado `analytics.recalcular_kpis`
   (celery beat, horário + diário, fila `gov.batch`) **não estava firando** — o container
   `conecta-pro-celery-beat` estava caído/instável (reiniciou durante os deploys de 21/07). A
   LÓGICA do job está correta: `kpi_recalc_service.recalcular_kpis()` puxa o saldo Inter ao vivo,
   MRR e contratos reais. Rodado à mão em 21/07 16:32 → os 3 voltaram frescos e corretos.
   **Conserto**: garantir que o `celery-beat` fique de pé (healthcheck/restart) e monitorar a
   última execução; sem ele, TODO KPI/agregado envelhece em silêncio.
2. **KPIs que nunca são calculados (Compliance, Inadimplência, Score)**: `recalcular_kpis` NÃO
   tem `src_` para KPI-003/004/006. São valores semeados na tabela que **nenhuma rotina atualiza**
   — se passavam por métrica real. **Conserto**: definir a fórmula real (fonte + cálculo) para
   cada um, OU removê-los. Enquanto não houver fórmula, ficam honestamente "não calculado".

## Onde ainda pode enganar (fora do módulo do T4)
- O **dashboard executivo do CLÁSSICO** (`analytics`, tabela executive/`financial_kpis`) também
  exibe Compliance/Inadimplência/Score. O fix de display do T4 só cobre as telas do **redesign**
  (raio-x/relatórios). O clássico precisa do mesmo tratamento pelo dono do módulo analytics.

## O que o T4 já fez (2026-07-21)
- Puxou o saldo Inter REAL ao vivo (R$15.270,74) e corrigiu `bank_accounts` + `financial_kpis`.
- Rodou `recalcular_kpis` real → KPI-001/002/005 frescos e batendo com a fonte.
- Telas raio-x/relatórios: valor só é honrado com prova de cálculo (timestamp), senão
  "não calculado"; nova coluna "Atualizado". Commit `2ab0b3a5` (deploy blue-green).
- **NÃO** inventou fórmula p/ os 3 placeholders (seria repetir o erro). Ficam sinalizados.

## Adendo — saldos bancários (bank_accounts) têm o MESMO problema (2026-07-21)
| Conta | Stored (ERP) | Real ao vivo | last_balance_update | Fix |
|---|---|---|---|---|
| **Inter** (CNPJ1) | ~~R$67.757~~ | **R$15.270,74** | estava 16/07 (velho) | corrigido; sync existe (parou c/ beat) |
| **Cora** (CNPJ2 Patrimonial) | ~~R$0,00~~ | **R$34.237,37** | **NULL = NUNCA** | corrigido ao vivo; `cora_sync_service` nunca firou |

Ambos os saldos vêm de adapters mTLS que FUNCIONAM (`InterClient.consultar_saldo`, `CoraAdapter.get_balance` — READ-only, visibilidade). O buraco é orquestração: os jobs de sync de saldo não rodam de forma confiável → o `bank_accounts.current_balance` fica velho/zero e se passa por real. **Conserto (item separado):** agendar+monitorar `cora_sync_service` e o sync Inter junto do `analytics.recalcular_kpis`, sempre gravando `last_balance_update` (a régua: sem timestamp fresco, o saldo NÃO é confiável).

## RAIZ REAL encontrada e RESOLVIDA (2026-07-21) — o scheduler estava MORTO
Investigando o "job não fira", achei a causa de TUDO: **`conecta-pro-celery-beat` estava em
crash-loop — RestartCount=7464** — rodando uma **imagem velha** (de dias atrás) que não tinha
`modules/fiscal_contabil/obrigacoes/tasks.py` (arquivo que o `celery_app.py` inclui). Beat
quebrava no boot com `ModuleNotFoundError` → reiniciava → quebrava, 7464×. **Nenhuma tarefa
agendada NUNCA firava** → não só saldos/KPIs: fiscal, eSocial-espelho, Solides, CRM, SST, gedeon,
operacional — TODA a automação estava parada. Os workers (batch/priority/…) também rodavam
imagem de 2 dias (o deploy blue-green só recria o `backend`, nunca a frota celery).

**Conserto aplicado:**
1. `docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --force-recreate`
   em beat + TODOS os workers → frota inteira na imagem atual (`fb37e651`). Beat: **RestartCount=0**,
   estável, e voltou a firar todo o schedule (visto no log: inter_reconciliacao, nfse, esocial,
   solides, crm, sst, gedeon…). Provado end-to-end: disparei `analytics.recalcular_kpis` → batch
   worker executou (financial=3, executive=10).
2. `cora_sync_service` agora grava o saldo em `bank_accounts` (bug: puxava e não persistia).
3. **KPI-002 estava MAL ROTULADO**: `src_saldo` = `SUM(current_balance)` de TODAS as contas ativas,
   mas o rótulo era "Saldo Inter". Só "batia" porque Cora era 0. Com Cora corrigido, virou
   Inter(15.270,74)+Cora(34.237,37)=**49.508,11** = total em bancos, não Inter. **Renomeei o KPI-002
   para "Saldo em bancos"** (o valor está certo como total; a tela `saldos` mostra por conta).

**Aberto (não crítico, flag):** conta `ZZE2E_TestBank_001` está ativa e entra na soma do KPI
(hoje R$0, inofensivo; se ganhar saldo, polui). E o dashboard executivo do CLÁSSICO ainda mostra
os 3 placeholders (Compliance/Inadimplência/Score) como reais — dono do analytics precisa dar
fórmula ou remover. Beat vivo agora recalcula tudo de hora em hora.

## Os 3 placeholders — RESOLVIDOS com fórmula real (2026-07-21)
Deixaram de ser valores fabricados; agora têm coletor real em `kpi_recalc_service.FINANCIAL_MAP`
(recalculados de hora em hora pelo beat). Provado no dashboard CLÁSSICO `/financial/bi/kpis` e no
redesign raio-x. Os placeholders escondiam um quadro MELHOR que o real:
| KPI | Placeholder | Real (fórmula) | Fórmula |
|---|---|---|---|
| Compliance Lucro Real | 100% | **83,87%** | % de `fiscal_obligations` com status 'cumprida' (26/31) |
| Inadimplência | 17,04% | **45,75%** | Σ vencido em aberto ÷ Σ exigível (pago+aberto), `receivable_accounts` |
| Score Saúde Financeira | 68,5 | **48,6** | composto: 40% margem + 35% adimplência + 25% liquidez (saldo÷a pagar) |

**Score — metodologia explícita (não é caixa-preta):** pesos 40/35/25 são uma definição INICIAL
ajustável; cada componente vem de dado real (margem=executive MARGEM; adimplência=100−inadimplência;
liquidez=saldo em bancos÷contas a pagar em aberto, teto 100). Documentado no docstring de
`src_score_saude_financeira`. Jordan pode retunar os pesos.

**Durabilidade:** commit `fa1c3860` + bake + recriação do worker `celery-batch` (imagem nova) →
o recalcular_kpis agendado passa a computar os 6 KPIs (antes pulava KPI-003/004/006).
