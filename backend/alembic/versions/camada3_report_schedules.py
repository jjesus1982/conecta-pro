"""Camada 3 - report_schedules: ADD 23 colunas do model (tabela vazia, puro aditivo)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="camada3_report_schedules"; down_revision="camada3_report_templates"; branch_labels=None; depends_on=None
ADDS=[("avg_execution_time",sa.Integer()),("bcc_recipients",postgresql.JSONB()),("created_by",postgresql.UUID(as_uuid=True)),("data_end_offset",sa.Integer()),("data_period",sa.String(50)),("data_start_offset",sa.Integer()),("delivery_config",postgresql.JSONB()),("email_template",sa.String(100)),("last_execution_at",sa.DateTime(timezone=True)),("last_failure_at",sa.DateTime(timezone=True)),("last_success_at",sa.DateTime(timezone=True)),("max_executions",sa.Integer()),("next_execution_at",sa.DateTime(timezone=True)),("notification_recipients",postgresql.JSONB()),("notify_on_failure",sa.Boolean()),("notify_on_success",sa.Boolean()),("relative_period",sa.Boolean()),("report_filename_pattern",sa.String(200)),("report_format",sa.String(20)),("report_parameters",postgresql.JSONB()),("retry_count",sa.Integer()),("retry_enabled",sa.Boolean()),("updated_by",postgresql.UUID(as_uuid=True))]
def upgrade():
    for n,t in ADDS: op.add_column("report_schedules",sa.Column(n,t,nullable=True))
def downgrade():
    for n,_ in ADDS: op.drop_column("report_schedules",n)
