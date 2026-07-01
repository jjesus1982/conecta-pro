"""sprint91: leads.email nullable (Fase 2 - leads de WhatsApp sem email)

Revision ID: sprint91_lead_email_nullable
Revises: sprint90_cwi_message_log
Create Date: 2026-06-05

Torna leads.email opcional. Leads capturados via WhatsApp (Chatwoot) tem apenas
telefone, sem email. Operacao segura/reversivel (DROP NOT NULL nao reescreve dados).
"""
from alembic import op
import sqlalchemy as sa

revision = "sprint91_lead_email_nullable"
down_revision = "sprint90_cwi_message_log"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "leads",
        "email",
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade():
    # Atencao: so volta a NOT NULL se nao houver leads com email NULL.
    op.alter_column(
        "leads",
        "email",
        existing_type=sa.String(255),
        nullable=False,
    )
