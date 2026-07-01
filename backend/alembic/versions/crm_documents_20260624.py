"""crm_documents: registro de documentos gerados (proposta/contrato/recibo/OS/aditivo/atestado/relatório)
com link de download público tokenizado.

Revision ID: crm_documents_20260624
Revises: crm_growth_20260623
Create Date: 2026-06-24

Autorizado por Jordan (chat). Aditivo/reversível: 1 tabela nova, sem FK rígida.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_documents_20260624"
down_revision = "crm_growth_20260623"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_documents",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tipo", sa.String(40), nullable=False, index=True),
        sa.Column("titulo", sa.String(255), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("arquivo", sa.String(500), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("ref_tipo", sa.String(30), nullable=True),
        sa.Column("ref_id", sa.String(64), nullable=True),
        sa.Column("tamanho_kb", sa.Numeric(10, 1), nullable=True),
        sa.Column("teste", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("crm_documents")
