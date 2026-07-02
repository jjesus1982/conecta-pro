# FECHAMENTO DA RODADA FIN+DP — Verificação NOT NULL + FORWARD corrigido + aplicado

**Data:** 2026-06-01 · **Escopo:** `financial/` + `hr/` (DP-folha). **Objetivo:** verificar o furo NOT-NULL, corrigir o que precisar, aplicar com segurança e entregar o relatório.
**Princípio:** dado real intocável — só CREATE/ADD, zero UPDATE/DROP/DELETE.

---

## RESULTADO EM 1 LINHA
O furo NOT-NULL **não existia** (todas as 14 tabelas-alvo estão vazias). Mas a verificação **achou outro furo**: o `FORWARD.sql` referenciava 28 tipos enum sem criá-los → **corrigido** (CREATE TYPE idempotente prependado). FORWARD agora roda do zero até COMMIT. financial+hr: **FAIL 55 → 16** (OK 40 → 79). Nenhum dado tocado.

---

## PASSO 1 — VERIFICAÇÃO READ-ONLY (contagem em produção)
Todas as 14 tabelas que recebem coluna `NOT NULL` estão **vazias**:

| Tabela | Linhas |
|---|---:|
| codigos_servico | 0 |
| fin_stock_inventories | 0 |
| fin_stock_inventory_items | 0 |
| fin_stock_movements | 0 |
| fin_stock_reservations | 0 |
| products | 0 |
| purchase_quotation_items | 0 |
| purchase_quotations | 0 |
| purchase_requisition_items | 0 |
| purchase_requisitions | 0 |
| simples_nacional_das | 0 |
| sped_files | 0 |
| suframa_operacoes | 0 |
| work_schedules | 0 |

Reforço: o FORWARD tem **62 ADD COLUMN ... NOT NULL**, distribuídos só por essas tabelas vazias (work_schedules 27, suframa_operacoes 6, suframa_configs 5, sped_files 5, simples_nacional_das 4, fin_stock_* 6, purchase_* 4, codigos_servico 1, …). **As 4 tabelas populadas/deferidas (financial_widgets, fiscal_obligations, cashflow_forecasts, nfe_itens) não são tocadas pelo FORWARD — 0 ocorrências.**

## PASSO 2 — DECISÃO
- **NOT NULL:** como TODAS as 14 estão em 0 → **nenhum NOT NULL precisou ser afrouxado**. O FORWARD roda limpo nesse aspecto.
- **Furo real encontrado e corrigido (enums):** rodando o `FORWARD.sql` cru num staging restaurado do dump PRE, ele **falhou** em `type "analysistype" does not exist` — o SQL criava as 17 tabelas mas **não criava os tipos enum** que elas usam (a aplicação original criava via SQLAlchemy).
  - **Correção:** prependei 28 blocos `DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN duplicate_object THEN null; END $$;` (idempotentes) logo após o `BEGIN;`. Enums: activitytype/level/status, allocationbasis/method/status/type, analysisscope/status/type, cost*/driver*/pool* status/type, report_*_enum, cache_*_enum, reportformat, profitabilitylevel, delivery_method_enum, valueaddedtype.
  - Agora o `FORWARD.sql` é **auto-suficiente e replayável** (importante para disaster-recovery).

## PASSO 3 — BACKUP + STAGING
- **Backup PRE confirmado:** `backups/postgresql/conecta_pro_PRE_MIGRATIONS_FINDP_20260601_005409.dump` (3.802.028 bytes > 0, válido).
- **Staging:** `conecta_pro_drift_check` recriado do dump PRE (estado pré-migração, 531 tabelas) e rodado o **FORWARD corrigido com `ON_ERROR_STOP=1`**:
  - Resultado: **chega ao `COMMIT` sem erro**. 531 → **548 tabelas** (+17).
  - ORM staging pós-FORWARD: financial+hr **OK=79 / FAIL=16** (prova de que o `.sql` sozinho reproduz o resultado completo a partir do zero).

## PASSO 4 — PRODUÇÃO
> Nota de transparência: o conteúdo do balde 1+2 **já havia sido aplicado** em produção na rodada anterior (via script de metadados; alembic `findp_b1b2_20260601`). Aqui re-apliquei o **FORWARD corrigido** em produção para confirmar idempotência e COMMIT.
- FORWARD corrigido em produção (`ON_ERROR_STOP=1`): **chegou ao COMMIT** (NOTICE "already exists, skipping" — confirma idempotência, nenhum erro).
- **ORM produção financial+hr: OK=79 / FAIL=16.**
  - **financial: 45 FAIL → 9** (36 models corrigidos: 15 tabelas criadas + 21 tabelas vazias completadas).
  - **hr: 10 FAIL → 7** (3 models corrigidos: payroll_integrations, payroll_exports, work_schedules).
- **Backend health HTTP 200**; **20 containers healthy**.
- **Nenhum dado alterado:** só CREATE/ADD. Contagens idênticas ao backup: `employees=58, nfses=27, hr_vacation_periods=67, fiscal_obligations=23, financial_widgets=4, cashflow_forecasts=12, payable_accounts=19, receivable_accounts=21`.

### Prova ORM (antes → depois)
| Métrica | Antes (raio-X) | Depois |
|---|---:|---:|
| financial FAIL | 45 | **9** |
| hr FAIL | 10 | **7** |
| financial+hr OK | 40 | **79** |
| Linhas de dado tocadas | — | **0** |

## Tabelas criadas (balde 2) e colunas (balde 1)
- **17 tabelas** vazias (custeio ABC: fin_cost_pools/drivers/objects/activities/allocations/analyses; fiscal/SPED: ecd_resumos, efd_contribuicoes_resumos, efd_icms_ipi_resumos, sped_registros, simples_nacional_configs, tax_configurations, tax_tables; BI: financial_analytics_cache, financial_scheduled_reports; DP: payroll_integrations, payroll_exports).
- **324 colunas** aditivas em 22 tabelas vazias.

## Models suspeitos — NÃO criados (revisão do Jordan)
5 tabelas hr com FK para `funcionarios` (tabela inexistente; real é `employees`): `employee_documents, employee_notifications, employee_payroll_configs, employee_preferences, payroll_events`. Não materializadas para não fixar schema de model quebrado.

## Reversão
- **REVERSAL:** `auditoria/REVERSAO_MIGRATIONS_FIN_DP_2026-06-01.sql` (324 DROP COLUMN IF EXISTS + 17 DROP TABLE IF EXISTS, em transação).
- ⚠️ **O `DROP TABLE ... CASCADE` só é seguro enquanto as 17 tabelas estiverem VAZIAS.** Se a funcionalidade começar a gravar dado nelas, revisar o downgrade antes de usar.
- **FORWARD (corrigido, replayável):** `auditoria/FORWARD_MIGRATIONS_FIN_DP_2026-06-01.sql` (28 CREATE TYPE + 17 CREATE TABLE + 324 ADD COLUMN, idempotente).
- **Alembic:** `findp_b1b2_20260601` (upgrade/downgrade embutidos). **Restore total:** `pg_restore` do dump PRE.

## Pendências registradas
1. **Endurecer NOT NULL depois:** as 62 colunas NOT NULL caíram em tabelas vazias — corretas hoje. Quando a funcionalidade preencher dado, manter a constraint (já está NOT NULL). Nenhuma foi afrouxada nesta rodada.
2. **Balde 3** (rename-com-dado: nfse↔nfses 27, nfe↔nfes 2, employee_vacation_*↔hr_vacation_* 67/15, 4 tabelas populadas) — aguardando decisão (ver `MIGRATIONS_FINANCEIRO_DP_2026-05-31.md`).
3. **Suspeitos funcionarios** (5 hr) — corrigir FK→employees no model antes de criar.
4. **Bug código** `fin_journal_entries .unique()` — fora de migration.
5. **`fin_accounting_periods` / enum `periodstatus` → é FIX DE CÓDIGO, não de banco** (ver Correção 2026-06-17 abaixo).

---

## ⚠️ CORREÇÃO (2026-06-17) — diagnóstico do `periodstatus` revisado
Ao testar a skill `finding-schema-drift` no módulo financial, o pull de evidência (read-only) corrigiu o que este relatório e o de 05-31 diziam sobre o `fin_accounting_periods`:
- **O que se afirmava:** o enum `periodstatus` não aceitava `PENDING` → opções "(A) `ALTER TYPE ADD VALUE 'PENDING'` no banco ou (B) migrar o dado".
- **Realidade verificada no banco:** o tipo `periodstatus` **já aceita** `PENDING, OPEN, CLOSING, CLOSED, REOPENED, ARCHIVED`. As 3 linhas têm `status='PENDING'`, **válido no banco**.
- **Causa real:** o **Enum Python do model** está desatualizado (`FUTURE, OPEN, CLOSING, LOCKED`) e não inclui `PENDING` → o SQLAlchemy falha ao mapear a linha no load (`'PENDING' is not among the defined enum values`).
- **Conclusão:** **não há nada a fazer no banco** (já está correto). É **correção de código**: alinhar o Enum Python (`PeriodStatus`) ao tipo do banco. Reclassificado de "balde 3c (enum/banco)" para **"OUTROS — fix de código"** (mesma categoria do `.unique()`).

---

## RESUMO (10 linhas)
1. Contagem (PASSO 1): as 14 tabelas que recebem coluna NOT NULL estão **todas com 0 linhas** → NOT NULL é seguro.
2. **Nenhum NOT NULL precisou ser afrouxado.**
3. Mas a verificação achou **outro furo**: o FORWARD.sql não criava os 28 tipos enum das 17 tabelas → **corrigido** (CREATE TYPE idempotente).
4. FORWARD corrigido roda do zero (staging restaurado do PRE) **até COMMIT sem erro**; 531→548 tabelas.
5. **financial: 45 FAIL → 9** (36 corrigidos). **hr: 10 FAIL → 7** (3 corrigidos). OK total 40→**79**.
6. Backup PRE confirmado (3,8 MB, válido); staging OK; produção re-aplicada idempotente até COMMIT.
7. **Backend health 200; 20 containers healthy.**
8. **Nenhum dado real tocado** — só CREATE/ADD; contagens idênticas ao backup (employees=58, nfses=27, hr_vacation_periods=67).
9. Reversão pronta (REVERSAL.sql) — DROP CASCADE só seguro enquanto as 17 tabelas estiverem vazias.
10. Restam 16 FAIL = balde 3 + suspeitos funcionarios + bug de código, todos aguardando decisão (não autônomos).
