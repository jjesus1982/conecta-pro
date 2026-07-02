# FRENTE 2 — Camadas 1+2 (renames) + Aditivos Seguros — APLICADOS EM PRODUÇÃO

**Data:** 2026-05-30
**Status:** ✅ **APLICADO E VALIDADO EM PRODUÇÃO** — dado preservado, 2 famílias de 500 destravadas, zero regressão.
**Camada 3 (redesenho):** **fora de escopo** — backlog de produto do Jordan (detalhado na §7).

> Fluxo: backup fresco → validação completa em staging → ⏸️ pausa/OK do Jordan → produção → validação ao vivo. Tudo reversível.

---

## 1. Backup usado

- `/opt/conecta-pro/backups/conecta_pro_PRE_RENAME_20260530_181725.dump`
- Validado: **4533 objetos**, formato CUSTOM, de `conecta_pro` (prod), PG 16.11.

## 2. Migration criada (versionada)

- `backend/alembic/versions/frente2_renames_20260530.py`
- `revision = "frente2_renames_20260530"`, `down_revision = "sprint89_inter_kit_fk"`.
- **upgrade:** 34 renames (`op.alter_column ... new_column_name`) + 16 `add_column`.
- **downgrade:** inverso exato (drop dos 16 adds + rename de volta).

## 3. Camada 1+2 — renames aplicados (34 colunas, 23 tabelas) — DADO PRESERVADO

| Rename | Tabelas | Tipo |
|---|---:|---|
| `metadata → extra_metadata` (JSONB) | 21 | inclui **Camada 1**: `access_history`, `sync_queue` (destravam 500) |
| `nome → name` | 4 | varchar |
| `descricao → description` | 4 | varchar/text |
| `codigo → code` | 3 | varchar |
| `ordem → "order"` | 2 | integer (palavra reservada — quotada) |

**Prova de preservação de dado (produção, antes → depois):**
- `executive_kpis`: antes `codigo='CLIENTES', nome='Clientes Ativos'` → depois `code='CLIENTES', name='Clientes Ativos'` — **idêntico**, coluna antiga sumiu (renomeada, não duplicada).
- Todas as 21 `metadata` eram **JSONB** → rename preserva tipo, bate com o model.

## 4. Aditivos seguros aplicados (16 ADD COLUMN, reversíveis)

- `extra_metadata` (JSONB, nullable) — **6 tabelas genuínas**: `checklist_itens, device_tokens, financial_kpis, mobile_sessions, notification_templates, work_schedules`.
- `tenant_id` (UUID, nullable) — **10 tabelas**: `benchmarks, execution_logs, executive_kpis, push_ab_test_results, push_delivery_reports, push_device_sessions, push_notification_actions, report_exports, report_schedules, report_templates`.

## 5. Endpoints destravados (antes → depois)

| Endpoint | Antes | Depois | Prova |
|---|---|---|---|
| `/api/v1/audit/access` | **500** (`column access_history.extra_metadata does not exist`) | **401** (auth) | coluna agora consultável |
| `/api/v1/integrations/integrations/sync` | **500** (`sync_queue.extra_metadata`) | **401** (auth) | coluna agora consultável |

**Prova conclusiva ao vivo** (query via a própria conexão asyncpg do backend, sem restart):
```
access_history: OK   sync_queue: OK   executive_kpis: OK (linha lida: code, name, extra_metadata, tenant_id)
→ "CONEXAO VIVA ENXERGA O SCHEMA NOVO — sem stale cache"
```
- `erros_coluna_recentes = 0` nos logs do backend.

## 6. alembic_version saneado (3 → 1)

- Antes: `sprint87_d7_payments, sprint88_inter_cat, sprint89_inter_kit_fk` (corrompido — ancestrais + folha juntos).
- Depois: **`frente2_renames_20260530`** (linha única). Aplicado **atômico** junto com a DDL (uma transação: renames + adds + `DELETE`/`INSERT` no alembic_version).

## 7. 🔴 CAMADA 3 — tabelas que CONTINUAM 500 (backlog de produto do Jordan)

Estas têm **redesenho de model** (não rename mecânico) — só os renames triviais (codigo/nome/descricao) foram aplicados; os **splits e semântica nova NÃO** (exigem sua decisão de mapeamento de dados):

| Tabela | Exemplo de redesenho (não automatizável) |
|---|---|
| `executive_kpis` | `threshold_critical` → `critical_threshold_high` + `critical_threshold_low` (**split 1→2**); `threshold_warning` → `warning_threshold_high`+`low`; `precision`→`decimal_places`; `visibility`→`visible_on_dashboard` |
| `report_templates` | model espera `query_template, css_styles, theme, metrics, tables, previous_version_id...` — estrutura nova vs colunas legadas (`grouping, sorting, style_config, totals_config`) |
| `report_schedules` | model: `data_period, relative_period, report_format, delivery_config, retry_enabled...` vs legado (`filters, parameters, output_format, storage_path, webhook_url`) |
| `benchmarks` | model: `current_company_value, year_over_year_change, geographic_region, sub_industry...` vs legado (`company_value, gap_to_benchmark, region, segment`) — splits + semântica |
| `financial_kpis` | model em inglês (`threshold_critical_max/min`, `historico_valores`, `meta_*`) vs legado PT — mistura de rename + reestruturação |

**Como destravar (futuro, uma por vez, com sua decisão):** você define o mapeamento (`threshold_critical` vira `high` ou `low`? como dividir?), eu escrevo a migration de dados sob medida e valido no restore antes de produção. **Sem adivinhação.**

## 8. Rollback (disponível)

```bash
# Reverter a migration (rename de volta + drop dos 16 adds), via SQL gerado:
psql -h <prod> -U postgres -d conecta_pro -f /tmp/downgrade.sql
# + restaurar alembic_version se desejar o estado anterior
# Último caso: restore do dump conecta_pro_PRE_RENAME_20260530_181725.dump
```
`alembic downgrade` também disponível (a migration tem `downgrade()` exato).

## 9. Estado final

Produção: **health 200, 3520 rotas (sem regressão)**, 34 renames + 16 adds aplicados, dado preservado (provado), 2 endpoints destravados, alembic saneado. Staging `conecta_pro_drift_check` preservado para a Camada 3. Migration versionada no host (entra no próximo rebuild).
