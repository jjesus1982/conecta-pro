# CAMADA 3 — report_schedules (FRENTE 4, tabela 3/5)

**Data:** 2026-05-30 · **Status:** ✅ **APLICADO EM PRODUÇÃO** — trivial (tabela vazia, puro aditivo).

## Análise
- **0 linhas** → zero dado em risco, **nenhuma decisão de mapeamento**.
- `code` **não é** coluna do model do report_schedules → `codigo` (legado) fica como está, **sem rename**.
- Demais legadas db-only (consecutive_failures, filters, last_execution, next_execution, notification_config, output_format, owner_id, parameters, storage_path, webhook_url) — vazias, **mantidas** (model ignora; ele usa next_execution_at/last_execution_at/report_parameters/report_format/delivery_config etc.).

## Migration aplicada (23 ADD COLUMN, todas nullable)
`avg_execution_time, bcc_recipients, created_by, data_end_offset, data_period, data_start_offset, delivery_config, email_template, last_execution_at, last_failure_at, last_success_at, max_executions, next_execution_at, notification_recipients, notify_on_failure, notify_on_success, relative_period, report_filename_pattern, report_format, report_parameters, retry_count, retry_enabled, updated_by`.

Sem deploy de código (model já esperava). Versionada: `camada3_report_schedules` (chain de `camada3_report_templates`).

## Validação
- **Staging:** 23 ADD OK; query com as colunas do model roda.
- **Produção:** 23/23 colunas; `alembic=camada3_report_schedules`; query viva via asyncpg OK (`SELECT next_execution_at, report_format, delivery_config, retry_enabled, created_by` → OK).

## Rollback
`downgrade()` (DROP dos 23 ADD). Backup recente: `conecta_pro_PRE_CAMADA3_EKPIS_20260530_221540.dump`.

**3 de 5 tabelas da Camada 3.** (Próximas: benchmarks, financial_kpis.)
