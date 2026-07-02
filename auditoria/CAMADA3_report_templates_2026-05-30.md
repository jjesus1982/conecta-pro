# CAMADA 3 — report_templates (FRENTE 4, tabela 2/5)

**Data:** 2026-05-30 · **Status:** ✅ **APLICADO EM PRODUÇÃO** — trivial (tabela vazia, puro aditivo).

## Análise
- **0 linhas** → zero dado em risco, **nenhuma decisão de mapeamento**.
- Renames (codigo/nome/descricao/metadata, tenant_id) já feitos na Frente 2.
- Legadas db-only (grouping, sorting, totals_config, style_config, owner_id) — vazias, **mantidas** (model ignora).

## Migration aplicada (13 ADD COLUMN, todas nullable)
`query_template, tables, metrics, theme, css_styles, logo_url, color_scheme, allowed_users, version_notes, previous_version_id, avg_generation_time, created_by, updated_by`.
Sem deploy de código (model já esperava). Versionada: `camada3_report_templates` (chain de `camada3_exec_kpis_20260530`).

## Validação
- Staging: 13 ADD OK; query com todas as colunas do model roda.
- Produção: 13/13 colunas; `alembic=camada3_report_templates`; query viva via asyncpg OK; `/reports/templates` → 401 (era 500).
- Nota: a 1ª tentativa falhou porque o nome de revisão (>32 chars) excedia `alembic_version.version_num VARCHAR(32)` — transação atômica → zero estado parcial; encurtei e reapliquei.

## Rollback
`downgrade()` (DROP dos 13 ADD). Backup recente: `conecta_pro_PRE_CAMADA3_EKPIS_20260530_221540.dump`.

**2 de 5 tabelas da Camada 3 concluídas.** Restam: report_schedules, benchmarks, financial_kpis.
