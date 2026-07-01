"""Camada 3 - executive_kpis: rename precision->decimal_places + ADD colunas do model (vazias). Legadas mantidas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="camada3_exec_kpis_20260530"; down_revision="frente2_renames_20260530"; branch_labels=None; depends_on=None
ADDS=[("prefix",sa.String(10)),("suffix",sa.String(10)),("display_format",sa.String(50)),("warning_threshold_low",sa.Float()),("warning_threshold_high",sa.Float()),("critical_threshold_low",sa.Float()),("critical_threshold_high",sa.Float()),("period_start",sa.DateTime(timezone=True)),("period_end",sa.DateTime(timezone=True)),("calculation_config",postgresql.JSONB()),("historical_values",postgresql.JSONB()),("last_12_months",postgresql.JSONB()),("owner_name",sa.String(200)),("department",sa.String(100)),("color_scheme",postgresql.JSONB()),("alert_recipients",postgresql.JSONB()),("last_alert_at",sa.DateTime(timezone=True)),("alert_frequency",sa.String(50)),("yearly_target",sa.Float()),("quarterly_targets",postgresql.JSONB()),("monthly_targets",postgresql.JSONB()),("related_kpis",postgresql.JSONB()),("created_by",postgresql.UUID(as_uuid=True)),("updated_by",postgresql.UUID(as_uuid=True))]
def upgrade():
    op.alter_column("executive_kpis","precision",new_column_name="decimal_places")
    for n,t in ADDS: op.add_column("executive_kpis",sa.Column(n,t,nullable=True))
    op.add_column("executive_kpis",sa.Column("visible_on_dashboard",sa.Boolean(),nullable=False,server_default="true"))
    op.add_column("executive_kpis",sa.Column("alerts_enabled",sa.Boolean(),nullable=False,server_default="true"))
def downgrade():
    for n in ["visible_on_dashboard","alerts_enabled"]+[a[0] for a in ADDS]: op.drop_column("executive_kpis",n)
    op.alter_column("executive_kpis","decimal_places",new_column_name="precision")
