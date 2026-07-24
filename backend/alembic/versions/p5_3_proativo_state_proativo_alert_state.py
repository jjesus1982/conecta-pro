"""proativo_alert_state — estado de transição das regras proativas (Fase 5.3)

Revision ID: p5_3_proativo_state
Revises: fase2_entity_overrides
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p5_3_proativo_state"
down_revision = "fase2_entity_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proativo_alert_state",
        sa.Column("correlation_id", sa.Text(), primary_key=True),
        sa.Column("familia", sa.Text(), nullable=False),
        sa.Column("severidade", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("destinatarios", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_seen_at", sa.TIMESTAMP(), nullable=False,
                  server_default=sa.text("(now() AT TIME ZONE 'America/Manaus')")),
        sa.Column("last_seen_at", sa.TIMESTAMP(), nullable=False,
                  server_default=sa.text("(now() AT TIME ZONE 'America/Manaus')")),
        sa.Column("resolved_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("notified_individually", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.create_index("ix_proativo_state_ativos", "proativo_alert_state",
                    ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_proativo_state_ativos", table_name="proativo_alert_state")
    op.drop_table("proativo_alert_state")
