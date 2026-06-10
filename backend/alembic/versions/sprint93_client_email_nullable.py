"""sprint93: proposals.client_email nullable

Revision ID: sprint93_client_email_nullable
Revises: sprint92_proposal_followups
Create Date: 2026-06-10

Torna proposals.client_email opcional. O e-mail do cliente e IDEAL mas NAO
essencial para registrar uma proposta. Operacao segura/reversivel (DROP NOT NULL
nao reescreve dados). Espelha sprint91 (leads.email nullable).

Nota: revision id curto (<=32 chars) por causa do alembic_version.version_num
ser varchar(32).
"""

import sqlalchemy as sa

from alembic import op

revision = "sprint93_client_email_nullable"
down_revision = "sprint92_proposal_followups"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "proposals",
        "client_email",
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade():
    # Atencao: so volta a NOT NULL se nao houver propostas com client_email NULL.
    op.alter_column(
        "proposals",
        "client_email",
        existing_type=sa.String(255),
        nullable=False,
    )
