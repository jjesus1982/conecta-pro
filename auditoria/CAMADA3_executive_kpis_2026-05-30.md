# CAMADA 3 — executive_kpis (FRENTE 4, tabela 1/5)

**Data:** 2026-05-30
**Status:** ✅ **APLICADO EM PRODUÇÃO** — dado preservado, `/reports/kpis` destravado, sem perda.

> Validado em staging → ⏸️ OK do Jordan → produção. Backup fresco antes.

---

## 1. Achado que simplificou

Os "splits" temidos (`threshold_critical/warning/target/excellent`) estavam **VAZIOS** (NULL nas 10 linhas) → viraram colunas novas vazias, **sem migração de dado**. Só 5 colunas legadas tinham dado.

## 2. Decisões do Jordan (mapeamento)

| Coluna legada (com dado) | Decisão |
|---|---|
| `precision` (0,1,2) → `decimal_places` | **RENAME** (preserva dado) |
| `visibility` ('all') → `visible_on_dashboard` (bool) | **ADD `visible_on_dashboard=true`, MANTER `visibility`** |
| `history`, `calculation_frequency_minutes`, `history_retention_days` (jsonb/int com dado) | **MANTER legadas + ADD as novas vazias** (zero perda, sem adivinhar jsonb) |

## 3. Migration aplicada (1 RENAME + 26 ADD)

- `ALTER TABLE executive_kpis RENAME COLUMN precision TO decimal_places;`
- ADD (nullable, vazias): prefix, suffix, display_format, warning_threshold_low/high, critical_threshold_low/high, period_start/end, calculation_config, historical_values, last_12_months, owner_name, department, color_scheme, alert_recipients, last_alert_at, alert_frequency, yearly_target, quarterly_targets, monthly_targets, related_kpis, created_by, updated_by.
- ADD (NOT NULL default true): `visible_on_dashboard`, `alerts_enabled`.
- **Legadas mantidas** (model ignora, dado preservado): history, calculation_frequency_minutes, history_retention_days, visibility, threshold_*, trend_percentage, allowed_roles, dashboard_config, next_calculation_at.
- **Sem deploy de código** — o model `executive_kpi.py` já esperava essas colunas; era só o banco que faltava.

## 4. Validação

- **Staging:** 27 statements OK; `decimal_places=0,1,2` preservado; `visible_on_dashboard=true`; query com as 30 colunas do model → 10 linhas lidas; `/reports/kpis` → 401 (não 500).
- **Produção:** `decimal_places=0,1,2` (dado preservado), `visible_on_dashboard=true`; prova ao vivo via conexão asyncpg do backend: `QUERY OK | code=MRR decimal_places=2 visible=True`; `/reports/kpis` → **401** (era 500); `erros_coluna=0`.
- **Alembic:** avançado para `camada3_exec_kpis_20260530` (chain de `frente2_renames_20260530`). Migration versionada em `alembic/versions/`.

## 5. Backup / Rollback

- Backup: `conecta_pro_PRE_CAMADA3_EKPIS_20260530_221540.dump`.
- Rollback: `downgrade()` da migration (drop dos 26 ADD + rename decimal_places→precision), ou restore do dump.

## 6. Restantes da Camada 3 (próximas tabelas, quando o Jordan quiser)

`report_templates`, `report_schedules`, `benchmarks`, `financial_kpis` — mesmo método: levanto legado×model com dado real, você decide os mapeamentos (provável que vários "splits" também estejam vazios, como aqui), valido em staging, aplico em prod com sua aprovação.

**Resumo:** executive_kpis reconciliado em produção preservando todo o dado (decimal_places via rename; legadas mantidas; novas vazias adicionadas), `/reports/kpis` destravado, versionado e reversível. 1 de 5 tabelas da Camada 3 concluída.
