"""proposal_followups: estado/auditoria de follow-up de propostas

Revision ID: sprint92_proposal_followups
Revises: sprint91_lead_email_nullable
Create Date: 2026-06-10

Tabela auditavel (1 registro por follow-up agendado/enviado) para a rotina de
follow-up de propostas respeitar a cadencia (1o follow-up 2d apos sent_at; depois
a cada 7d enquanto responded_at IS NULL) sem remandar todo dia, e ter trilha LGPD.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "sprint92_proposal_followups"
down_revision = "sprint91_lead_email_nullable"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proposal_followups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # FK real same-schema (public), mesmo padrao de proposal_items -> proposals
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),  # 1 = 1o (2d); 2+ = 7d
        sa.Column("channel", sa.String(length=20), nullable=True),  # whatsapp|email|both|none
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),  # pending|sent|failed|skipped
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),  # quando deveria sair
        sa.Column("sent_at", sa.DateTime(), nullable=True),  # quando efetivamente saiu (null se so listado)
        sa.Column("detail", sa.Text(), nullable=True),  # erro, ou nota 'lista gerada, disparo desligado'
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_proposal_followups_proposal", "proposal_followups", ["proposal_id"])
    op.create_index("ix_proposal_followups_status_sched", "proposal_followups", ["status", "scheduled_for"])


def downgrade():
    op.drop_index("ix_proposal_followups_status_sched", table_name="proposal_followups")
    op.drop_index("ix_proposal_followups_proposal", table_name="proposal_followups")
    op.drop_table("proposal_followups")
