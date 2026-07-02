# RODADA DE MIGRATIONS — FINANCEIRO + DP-FOLHA (balde 1+2 aplicados, balde 3 para decisão)

**Data:** 2026-06-01 · **Escopo:** módulos `financial/` e `hr/` (DP-folha) — nenhum outro tocado.
**Princípio aplicado:** dado real trabalhista/contábil intocável. Backup antes, staging valida antes, **só CREATE TABLE / ADD COLUMN** — zero DROP/UPDATE/DELETE em todo o processo.

---

## RESUMO EXECUTIVO
- **financial+hr models: FAIL 55 → 16** (OK 40 → **79**). 39 models saíram de FAIL→OK.
- **BALDE 1+2 aplicado (staging→produção):** 17 tabelas criadas + 324 colunas aditivas. **Zero linhas de dado tocadas.**
- **BALDE 3 (NÃO aplicado):** 5 tabelas rename-com-dado + 4 tabelas populadas com colunas divergentes + 1 enum + 1 bug de código → **lista de decisão do Jordan abaixo**.
- **Modelos suspeitos (NÃO criados):** 5 tabelas hr com FK para `funcionarios` (tabela inexistente).
- Backup PRE: `conecta_pro_PRE_MIGRATIONS_FINDP_20260601_005409.dump` (validado). Backend **health 200**, **20 containers healthy**. Alembic: `drop_openclaw_tables` → **`findp_b1b2_20260601`**.

---

## PASSO 0 — Backup + Staging
- `pg_dump -Fc` produção → `backups/postgresql/conecta_pro_PRE_MIGRATIONS_FINDP_20260601_005409.dump` (3.8 MB, validado com `pg_restore --list`, 522 data entries).
- Staging `conecta_pro_drift_check` recriado a partir DESTE dump (531 tabelas = prod; dados reais preservados).

## A CLASSIFICAÇÃO — OS 3 BALDES

### Total de falhas em financial+hr: 55
| Balde | O quê | Qtde | Ação |
|---|---|---:|---|
| **1** | Colunas aditivas em tabelas **vazias** | 324 cols / 22 tabelas | ✅ Aplicado autônomo |
| **2** | Tabelas inexistentes, model coerente, vazias | 17 tabelas | ✅ Aplicado autônomo |
| **3a** | Tabelas rename-com-dado-real | 5 | 🛑 Decisão Jordan |
| **3b** | Tabelas **populadas** com colunas divergentes (possível rename) | 4 | 🛑 Decisão Jordan |
| **3c** | Enum divergente | 1 | 🛑 Decisão Jordan |
| **—** | Modelos suspeitos (FK→tabela inexistente) | 5 | 🛑 Revisão Jordan |
| **—** | Bug de código (não-schema) | 1 | ℹ️ Fora de migration |

---

## BALDE 1 — ADITIVO SEGURO (✅ aplicado: 324 colunas)
Colunas que o model espera, em tabelas **vazias (0 linhas)** → adicionadas exatamente como o model (nullability preservada). 22 tabelas:
`codigos_servico, fin_stock_inventories, fin_stock_inventory_items, fin_stock_movements, fin_stock_reservations, goods_receipt_items, goods_receipts, payable_categories, payment_methods, products, purchase_approvals, purchase_order_items, purchase_quotation_items, purchase_quotations, purchase_requisition_items, purchase_requisitions, receivable_categories, simples_nacional_das, sped_files, suframa_configs, suframa_operacoes, work_schedules`.
> Como todas estavam vazias, adicionar colunas (mesmo NOT NULL) é seguro: não há linha para violar. Zero risco de dado.

## BALDE 2 — TABELAS DE FUNCIONALIDADE (✅ aplicado: 17 tabelas vazias)
Criadas a partir do metadata do model (estrutura exata), **sem FK constraints** (vários alvos de FK estão quebrados/são views — ver nota), nascendo vazias:

**financial (15):** custeio ABC → `fin_cost_pools, fin_cost_drivers, fin_cost_objects, fin_cost_activities, fin_cost_allocations, fin_cost_analyses`; fiscal/SPED → `ecd_resumos, efd_contribuicoes_resumos, efd_icms_ipi_resumos, sped_registros, simples_nacional_configs, tax_configurations, tax_tables`; BI → `financial_analytics_cache, financial_scheduled_reports`.
**hr (2):** `payroll_integrations, payroll_exports`.

**Nota técnica (FK constraints omitidas):** as 17 tabelas foram criadas **sem** constraints de FK porque (a) nascem vazias e (b) vários modelos apontam FK para alvos quebrados (`funcionarios` inexistente) ou views (`payroll_periods` é VIEW, não tabela). A ausência de FK no banco **não** afeta o ORM (relacionamentos são resolvidos no código). As FKs podem ser adicionadas depois, quando os modelos forem revisados. Também normalizei `server_default` que vinha como string literal `'gen_random_uuid()'` para a função SQL `gen_random_uuid()` (bug de model que impediria CREATE).

### PROVA ORM (antes → depois) — staging E produção idênticos
| Banco | financial+hr OK antes | OK depois | FAIL antes | FAIL depois |
|---|---:|---:|---:|---:|
| staging | 40 | **79** | 55 | 16 |
| **produção** | 40 | **79** | 55 | **16** |

### Confirmação de segurança (produção)
- Dados intactos (contagem idêntica ao backup): `employees=58, nfses=27, hr_vacation_periods=67, fiscal_obligations=23, financial_widgets=4, cashflow_forecasts=12, payable_accounts=19, receivable_accounts=21`.
- Backend **health HTTP 200**; **20 containers healthy**.
- Apenas CREATE TABLE + ADD COLUMN executados (por construção do script — nenhum DROP/UPDATE/DELETE).

---

## BALDE 3 — REDESENHO COM DADO REAL (🛑 NÃO aplicado — decisão do Jordan)

### 3a) Tabelas rename-com-dado (model novo ↔ tabela legada com dado real)

**1. `nfse` (model, 91 cols) ↔ `nfses` (27 NFS-e REAIS)**
- Dado real em `nfses`: numero_nfse, valor_servicos, iss_valor, prestador/tomador, inss_liminar_aplicada… (27 notas autorizadas).
- Opções: **(A)** renomear `nfses`→`nfse` + mapear colunas para o schema do model (preserva as 27); **(B)** manter `nfses` canônica e apontar o model para ela; **(C)** model `nfse` é conceito novo distinto (criar vazio) e `nfses` continua. **Recomendo A ou B — 27 registros fiscais reais.**

**2. `nfe` (model, 76 cols) ↔ `nfes` (2 NF-e reais)** — mesma decisão (escala menor: 2 registros).

**3. `nfse_lotes` (model, 18 cols)** — legado `nfse_entrada` (10) é **conceito diferente** (NFS-e de ENTRADA/fornecedores, tem payable_id). `nfse_lotes` é controle de LOTES de emissão → provavelmente **genuinamente novo (balde 2)**, mas acoplado à decisão do `nfse`. Criar vazio quando a decisão 1 for tomada.

**4. `employee_vacation_periods` (model, 18 cols) ↔ `hr_vacation_periods` (67 FÉRIAS REAIS)**
- `hr_vacation_periods` tem exatamente a estrutura de período aquisitivo (start_date, end_date, period_number, days_entitled, days_used, days_sold, days_remaining, limit_date…) — **67 períodos reais de funcionários**.
- Opções: **(A)** o model `employee_vacation_periods` (portal self-service) deve LER de `hr_vacation_periods` (apontar/rename) — preserva 67; **(B)** são tabelas distintas (portal × DP) e o portal nasce vazio. **CRÍTICO: dado trabalhista — 67 períodos. Não criar vazio sem decisão.**

**5. `employee_vacation_requests` (model, 54 cols) ↔ `hr_vacation_requests` (15) / `vacation_requests` (10)**
- `hr_vacation_requests` (15) casa com o model (period_id, days_requested, manager_approved, hr_approved…). `vacation_requests` (10, tenant_id) é versão mais simples/antiga.
- Decisão: qual é a canônica para o portal? Mapear de `hr_vacation_requests`?

### 3b) Tabelas POPULADAS com colunas divergentes (possível rename PT→EN — NÃO toquei)
Estas têm dado real e o model pede **muitas** colunas com nomes diferentes — cheira a redesenho, não aditivo. **Deferidas inteiras** (nenhuma coluna adicionada):

| Tabela | Linhas | Cols ausentes | Natureza | Evidência |
|---|---:|---:|---|---|
| `financial_widgets` | 4 | **49** | Reescrita PT→EN | DB tem `titulo/tipo/tipo_grafico/cores`; model quer `codigo/nome/chart_type/colors/threshold_*` |
| `cashflow_forecasts` | 12 | 37 | Expansão | DB `expected_inflows/outflows/balance`; model `expected_receivables/payables/...` + forecast detalhado |
| `fiscal_obligations` | 23 | 23 | Expansão | DB simples; model adiciona multa/protocolo/retificação/responsável |
| `nfe_itens` | 2 | 33 | Expansão fiscal | model adiciona ICMS/IPI/PIS/COFINS/II detalhados (cluster do `nfe`) |

→ Para cada: decidir **mapear dado das colunas atuais → novas** (rename/backfill) ou **tratar as novas como aditivas nullable** (dado antigo fica nas colunas PT). Recomendo revisar `financial_widgets` primeiro (reescrita clara).

### 3c) Enum divergente
**`fin_accounting_periods.status` = enum `periodstatus`** — 3 linhas, **todas com `PENDING`**, mas o enum só aceita `FUTURE, OPEN, CLOSING, LOCKED`.
- Opções: **(A)** `ALTER TYPE periodstatus ADD VALUE 'PENDING'` (adiciona ao enum — aditivo); **(B)** migrar os 3 registros `PENDING`→`OPEN` (ou outro válido). Decisão de semântica contábil sua.

---

## MODELOS SUSPEITOS — NÃO criados (revisão do Jordan)
5 tabelas hr cujo model tem **FK para `funcionarios`** (tabela que **não existe** — a real é `employees`):
`employee_documents, employee_notifications, employee_payroll_configs, employee_preferences, payroll_events`.
→ Decisão: corrigir o model para FK→`employees` (e então criar as tabelas), OU confirmar que `funcionarios` deveria existir. **Não criei** para não materializar um schema baseado em model quebrado.

## BUG DE CÓDIGO (não-schema, fora de migration)
`fin_journal_entries` — endpoint precisa de `.unique()` no Result (eager-load de coleção). É **bug de código** (não drift). Listado para correção no código quando for mexer no razão contábil.

---

## REVERSÃO (downgrade)
Tudo reversível. Arquivos exatos gerados:
- **Forward:** `auditoria/FORWARD_MIGRATIONS_FIN_DP_2026-06-01.sql` (17 CREATE + 324 ALTER ADD).
- **Reversão:** `auditoria/REVERSAO_MIGRATIONS_FIN_DP_2026-06-01.sql` (324 DROP COLUMN IF EXISTS + 17 DROP TABLE IF EXISTS, em transação).
- **Alembic:** migration `backend/alembic/versions/findp_b1b2_20260601.py` (upgrade/downgrade embutidos). `alembic_version`: `drop_openclaw_tables` → `findp_b1b2_20260601`.
- **Restore total:** `pg_restore` do dump PRE_MIGRATIONS reverte tudo ao estado inicial.

Como balde 1+2 só CRIARAM tabelas vazias e adicionaram colunas vazias, o downgrade não perde nenhum dado real.

---

## CONTAGEM FINAL
| Métrica | Antes | Depois |
|---|---:|---:|
| financial+hr models OK | 40 | **79** |
| financial+hr models FAIL | 55 | **16** |
| Tabelas criadas (vazias) | — | 17 |
| Colunas adicionadas (vazias) | — | 324 |
| Linhas de dado tocadas | — | **0** |

Os 16 FAIL remanescentes = 5 (balde 3a) + 4 (balde 3b) + 1 (enum 3c) + 5 (suspeitos) + 1 (bug de código) — **todos requerem decisão sua, nenhum é aplicável autônomo.**
