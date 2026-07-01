"""Camada 3 - report_templates: ADD 13 colunas do model (tabela vazia, puro aditivo). Legadas mantidas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="camada3_report_templates"; down_revision="camada3_exec_kpis_20260530"; branch_labels=None; depends_on=None
ADDS=[("query_template",sa.Text()),("tables",postgresql.JSONB()),("metrics",postgresql.JSONB()),("theme",sa.String(50)),("css_styles",sa.Text()),("logo_url",sa.String(500)),("color_scheme",postgresql.JSONB()),("allowed_users",postgresql.JSONB()),("version_notes",sa.Text()),("previous_version_id",postgresql.UUID(as_uuid=True)),("avg_generation_time",sa.Integer()),("created_by",postgresql.UUID(as_uuid=True)),("updated_by",postgresql.UUID(as_uuid=True))]
def upgrade():
    for n,t in ADDS: op.add_column("report_templates",sa.Column(n,t,nullable=True))
def downgrade():
    for n,_ in ADDS: op.drop_column("report_templates",n)
