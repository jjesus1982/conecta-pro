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
