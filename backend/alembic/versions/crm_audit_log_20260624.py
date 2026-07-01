"""crm_audit_log: log de auditoria de todas as escritas (POST/PUT/PATCH/DELETE) da API.

Revision ID: crm_audit_log_20260624
Revises: crm_docs_quota_20260624b
Create Date: 2026-06-24

Aditivo. Autorizado por Jordan (PROMPT 4 — log de auditoria).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_audit_log_20260624"
down_revision = "crm_docs_quota_20260624b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_audit_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_table("crm_audit_log")
