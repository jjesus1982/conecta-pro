# CAMADA 3 — benchmarks (FRENTE 4, tabela 4/5)

**Data:** 2026-05-30 · **Status:** ✅ **APLICADO EM PRODUÇÃO** — trivial (tabela vazia, puro aditivo).

## Análise
- **0 linhas** → zero dado em risco, **nenhuma decisão de mapeamento**.
- Renames (codigo/nome/descricao/metadata, tenant_id) já feitos na Frente 2.
- Legadas db-only — todas vazias, **mantidas** (model ignora). `precision` (legado vazio) coexiste com `decimal_places` (nova) — sem perda, sem rename necessário (tabela vazia).

## Migration aplicada (37 ADD COLUMN, todas nullable)
Geradas automaticamente do model `modules/reports/models/benchmark.py` (mapeamento de tipos SQLAlchemy→PG):
`alert_if_above, alert_if_below, alerts_enabled, average_value, calculation_method, color_code, created_by, currency_code, current_company_value, decimal_places, deviation, deviation_percentage, display_order, geographic_region, historical_values, icon, improvement_deadline, improvement_target, is_currency, is_percentage, market_segment, notes, reference_month, reference_quarter, reference_year, related_kpi_ids, source_date, source_name, source_report, source_url, sub_industry, trend, updated_by, valid_from, valid_until, visible_on_dashboard, year_over_year_change`.

Sem deploy de código (model já esperava). Versionada: `camada3_benchmarks` (chain de `camada3_report_schedules`).

## Validação
- **Staging:** 37 ADD OK; query com colunas do model roda.
- **Produção:** colunas-chave presentes (`decimal_places, visible_on_dashboard, current_company_value, historical_values, created_by, year_over_year_change, source_url`); `alembic=camada3_benchmarks`; query viva via asyncpg OK.

## Rollback
`downgrade()` (DROP dos 37 ADD). Backup recente: `conecta_pro_PRE_CAMADA3_EKPIS_20260530_221540.dump`.

**4 de 5 tabelas da Camada 3.** (Última: financial_kpis — zona protegida, autorizada.)
