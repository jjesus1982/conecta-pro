"""crm_client_notes (ficha viva) + crm_system_state (heartbeat) — fechamento do ciclo

Revision ID: crm_loop_20260627   (<=32 chars)
Revises: crm_visita_20260627
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_loop_20260627"
down_revision = "crm_visita_20260627"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ficha viva: anotações compartilhadas por cliente (Cowork + José Luís leem/escrevem).
    op.create_table(
        "crm_client_notes",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cliente_id", UUID(as_uuid=False), nullable=True),
        sa.Column("cliente_ref", sa.String(255), nullable=True),   # cnpj/nome/id usado p/ achar
        sa.Column("cliente_nome", sa.String(255), nullable=True),
        sa.Column("phone_canonical", sa.String(20), nullable=True),
        sa.Column("nota", sa.Text(), nullable=False),
        sa.Column("autor", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_crm_client_notes_ref", "crm_client_notes", ["cliente_ref"])
    op.create_index("ix_crm_client_notes_phone", "crm_client_notes", ["phone_canonical"])

    # Estado do sistema (chave/valor): cooldown do heartbeat, flags operacionais.
    op.create_table(
        "crm_system_state",
        sa.Column("chave", sa.String(80), primary_key=True),
        sa.Column("valor", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("crm_system_state")
    op.drop_index("ix_crm_client_notes_phone", table_name="crm_client_notes")
    op.drop_index("ix_crm_client_notes_ref", table_name="crm_client_notes")
    op.drop_table("crm_client_notes")
