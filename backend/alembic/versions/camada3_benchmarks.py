"""Camada 3 - benchmarks: ADD 37 colunas do model (tabela vazia, aditivo)."""
from alembic import op
import sqlalchemy as sa
revision="camada3_benchmarks"; down_revision="camada3_report_schedules"; branch_labels=None; depends_on=None
ADDS=[('alert_if_above', 'DOUBLE PRECISION'), ('alert_if_below', 'DOUBLE PRECISION'), ('alerts_enabled', 'BOOLEAN'), ('average_value', 'DOUBLE PRECISION'), ('calculation_method', 'TEXT'), ('color_code', 'VARCHAR(7)'), ('created_by', 'UUID'), ('currency_code', 'VARCHAR(3)'), ('current_company_value', 'DOUBLE PRECISION'), ('decimal_places', 'INTEGER'), ('deviation', 'DOUBLE PRECISION'), ('deviation_percentage', 'DOUBLE PRECISION'), ('display_order', 'INTEGER'), ('geographic_region', 'VARCHAR(100)'), ('historical_values', 'JSONB'), ('icon', 'VARCHAR(50)'), ('improvement_deadline', 'TIMESTAMPTZ'), ('improvement_target', 'DOUBLE PRECISION'), ('is_currency', 'BOOLEAN'), ('is_percentage', 'BOOLEAN'), ('market_segment', 'VARCHAR(100)'), ('notes', 'TEXT'), ('reference_month', 'INTEGER'), ('reference_quarter', 'INTEGER'), ('reference_year', 'INTEGER'), ('related_kpi_ids', 'JSONB'), ('source_date', 'TIMESTAMPTZ'), ('source_name', 'VARCHAR(200)'), ('source_report', 'VARCHAR(200)'), ('source_url', 'VARCHAR(500)'), ('sub_industry', 'VARCHAR(100)'), ('trend', 'VARCHAR(20)'), ('updated_by', 'UUID'), ('valid_from', 'TIMESTAMPTZ'), ('valid_until', 'TIMESTAMPTZ'), ('visible_on_dashboard', 'BOOLEAN'), ('year_over_year_change', 'DOUBLE PRECISION')]
def upgrade():
    for n,t in ADDS: op.execute(f'ALTER TABLE benchmarks ADD COLUMN IF NOT EXISTS {n} {t}')
def downgrade():
    for n,_ in ADDS: op.execute(f'ALTER TABLE benchmarks DROP COLUMN IF EXISTS {n}')
