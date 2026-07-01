"""crm: soft-delete de documentos (crm_documents.arquivado) + meta por QUANTIDADE de contratos
(crm_quotas.target_count).

Revision ID: crm_docs_quota_20260624b
Revises: crm_documents_20260624
Create Date: 2026-06-24

Aditivo/reversível. Autorizado por Jordan (PROMPT 4).
"""
from alembic import op
import sqlalchemy as sa

revision = "crm_docs_quota_20260624b"
down_revision = "crm_documents_20260624"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("crm_documents", sa.Column("arquivado", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("crm_quotas", sa.Column("target_count", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("crm_quotas", "target_count")
    op.drop_column("crm_documents", "arquivado")
