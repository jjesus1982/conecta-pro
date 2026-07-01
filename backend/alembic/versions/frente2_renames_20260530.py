"""FRENTE 2 Camada 1+2: renames PT->EN (preserva dado) + aditivos seguros

Revision ID: frente2_renames_20260530
Revises: sprint89_inter_kit_fk
Create Date: 2026-05-30

Camada 1: access_history/sync_queue metadata->extra_metadata (destrava 500).
Camada 2: 34 renames triviais de alta confianca (codigo/nome/descricao/ordem/metadata).
Aditivos: 6 extra_metadata genuinos + 10 tenant_id (nullable).
NAO inclui Camada 3 (redesenho/splits) — backlog de produto.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "frente2_renames_20260530"
down_revision = "sprint89_inter_kit_fk"
branch_labels = None
depends_on = None

RENAMES = [('access_history', 'metadata', 'extra_metadata'), ('api_endpoints', 'metadata', 'extra_metadata'), ('api_keys', 'metadata', 'extra_metadata'), ('audit_logs', 'metadata', 'extra_metadata'), ('benchmarks', 'nome', 'name'), ('benchmarks', 'codigo', 'code'), ('benchmarks', 'descricao', 'description'), ('benchmarks', 'metadata', 'extra_metadata'), ('compliance_checks', 'metadata', 'extra_metadata'), ('compliance_rules', 'metadata', 'extra_metadata'), ('data_retention_policies', 'metadata', 'extra_metadata'), ('executive_kpis', 'nome', 'name'), ('executive_kpis', 'codigo', 'code'), ('executive_kpis', 'descricao', 'description'), ('executive_kpis', 'metadata', 'extra_metadata'), ('financial_kpis', 'ordem', 'order'), ('financial_widgets', 'ordem', 'order'), ('id_maps', 'metadata', 'extra_metadata'), ('integration_logs', 'metadata', 'extra_metadata'), ('report_exports', 'metadata', 'extra_metadata'), ('report_schedules', 'nome', 'name'), ('report_schedules', 'descricao', 'description'), ('report_schedules', 'metadata', 'extra_metadata'), ('report_templates', 'nome', 'name'), ('report_templates', 'codigo', 'code'), ('report_templates', 'descricao', 'description'), ('report_templates', 'metadata', 'extra_metadata'), ('service_catalog', 'metadata', 'extra_metadata'), ('service_orders', 'metadata', 'extra_metadata'), ('service_reports', 'metadata', 'extra_metadata'), ('sla_configs', 'metadata', 'extra_metadata'), ('sync_queue', 'metadata', 'extra_metadata'), ('tenant_settings', 'metadata', 'extra_metadata'), ('webhook_configs', 'metadata', 'extra_metadata')]
EM_ADD = ['checklist_itens', 'device_tokens', 'financial_kpis', 'mobile_sessions', 'notification_templates', 'work_schedules']
TID_ADD = ['benchmarks', 'execution_logs', 'executive_kpis', 'push_ab_test_results', 'push_delivery_reports', 'push_device_sessions', 'push_notification_actions', 'report_exports', 'report_schedules', 'report_templates']


def upgrade():
    for t, pt, en in RENAMES:
        op.alter_column(t, pt, new_column_name=en)
    for t in EM_ADD:
        op.add_column(t, sa.Column("extra_metadata", postgresql.JSONB(), nullable=True))
    for t in TID_ADD:
        op.add_column(t, sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    for t in TID_ADD:
        op.drop_column(t, "tenant_id")
    for t in EM_ADD:
        op.drop_column(t, "extra_metadata")
    for t, pt, en in RENAMES:
        op.alter_column(t, en, new_column_name=pt)
