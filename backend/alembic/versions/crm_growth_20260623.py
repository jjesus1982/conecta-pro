"""crm growth: 9 features HubSpot-like (catálogo, sequências, workflows, forms, agendamento,
segmentos, propriedades custom, scoring configurável, forecast/metas).

Revision ID: crm_growth_20260623
Revises: crm_timeline_tasks_20260623
Create Date: 2026-06-23

Autorizado por Jordan (chat) p/ esta missão ("implementa todos... deixe tudo funcionando"), com
backup (.chunk_archive/db_pre_crmgrowth_20260623.dump) e âncora de imagem.

Tudo ADITIVO/REVERSÍVEL: 13 tabelas novas (sem FK rígida, padrão dos models novos do CRM) +
2 colunas JSONB (leads.custom_fields, opportunities.custom_fields) com default '{}'.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "crm_growth_20260623"
down_revision = "crm_timeline_tasks_20260623"
branch_labels = None
depends_on = None


def _ts(t):
    t.append(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    t.append(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    return t


def upgrade():
    # 4) Catálogo de produtos/serviços (SKU)
    op.create_table(
        "crm_products",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("sku", sa.String(50), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("unit", sa.String(20), nullable=False, server_default="un"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("service_type", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )

    # 1) Sequências/cadências
    op.create_table(
        "crm_sequences",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("steps", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )
    op.create_table(
        "crm_sequence_enrollments",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("sequence_id", UUID(as_uuid=False), nullable=False, index=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("last_step_at", sa.DateTime(timezone=True), nullable=True),
        *_ts([]),
    )

    # 2) Workflows / automação
    op.create_table(
        "crm_workflows",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_event", sa.String(50), nullable=False, index=True),
        sa.Column("conditions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        *_ts([]),
    )
    op.create_table(
        "crm_workflow_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=False), nullable=False, index=True),
        sa.Column("entity_type", sa.String(30), nullable=True),
        sa.Column("entity_id", UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3) Formulários de captura
    op.create_table(
        "crm_forms",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True, index=True),
        sa.Column("fields", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("redirect_url", sa.String(500), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="website"),
        sa.Column("submit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )
    op.create_table(
        "crm_form_submissions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("form_id", UUID(as_uuid=False), nullable=False, index=True),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5) Agendamento de reunião/vistoria
    op.create_table(
        "crm_booking_links",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True, index=True),
        sa.Column("duration_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("weekly_availability", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )
    op.create_table(
        "crm_bookings",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("booking_link_id", UUID(as_uuid=False), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        *_ts([]),
    )

    # 6) Listas/segmentação dinâmica
    op.create_table(
        "crm_segments",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity", sa.String(30), nullable=False, server_default="lead"),
        sa.Column("filters", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )

    # 7) Propriedades customizadas
    op.create_table(
        "crm_custom_properties",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("entity", sa.String(30), nullable=False, index=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )
    op.create_unique_constraint("uq_crm_custom_prop_entity_key", "crm_custom_properties", ["entity", "key"])
    op.add_column("leads", sa.Column("custom_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("opportunities", sa.Column("custom_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))

    # 8) Lead scoring configurável
    op.create_table(
        "crm_scoring_rules",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("field", sa.String(60), nullable=False),
        sa.Column("operator", sa.String(20), nullable=False, server_default="eq"),
        sa.Column("value", sa.String(255), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_ts([]),
    )

    # 9) Forecast / metas de venda
    op.create_table(
        "crm_quotas",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("seller_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("seller_name", sa.String(255), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("target_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        *_ts([]),
    )
    op.create_unique_constraint("uq_crm_quota_seller_period", "crm_quotas", ["seller_id", "period_year", "period_month"])


def downgrade():
    op.drop_constraint("uq_crm_quota_seller_period", "crm_quotas", type_="unique")
    op.drop_table("crm_quotas")
    op.drop_table("crm_scoring_rules")
    op.drop_column("opportunities", "custom_fields")
    op.drop_column("leads", "custom_fields")
    op.drop_constraint("uq_crm_custom_prop_entity_key", "crm_custom_properties", type_="unique")
    op.drop_table("crm_custom_properties")
    op.drop_table("crm_segments")
    op.drop_table("crm_bookings")
    op.drop_table("crm_booking_links")
    op.drop_table("crm_form_submissions")
    op.drop_table("crm_forms")
    op.drop_table("crm_workflow_runs")
    op.drop_table("crm_workflows")
    op.drop_table("crm_sequence_enrollments")
    op.drop_table("crm_sequences")
    op.drop_table("crm_products")
