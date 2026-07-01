"""sprint98: biblioteca de conteudo de marketing (F2+ Conecta Marketing AI)

Revision ID: sprint98_mkt_content
Revises: sprint97_lead_attribution
Create Date: 2026-06-17

Cria a tabela marketing_content_drafts: biblioteca de pecas geradas pelo agente
Copywriter (rascunho -> aprovado -> arquivado), human-in-the-loop. Tabela nova,
sem impacto em dados existentes; reversivel.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "sprint98_mkt_content"
down_revision = "sprint97_lead_attribution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_content_drafts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("formato", sa.String(50), nullable=False, index=True),
        sa.Column("formato_label", sa.String(100), nullable=True),
        sa.Column("titulo", sa.String(255), nullable=True),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("briefing", sa.Text(), nullable=True),
        sa.Column("objetivo", sa.String(500), nullable=True),
        sa.Column("publico", sa.String(500), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="rascunho", index=True),
        sa.Column("created_by_id", UUID(as_uuid=False), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("marketing_content_drafts")
