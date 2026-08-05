"""central-rascunhos: agent_drafts (rascunhos criados pelo agente p/ aprovacao humana)

Revision ID: central_agent_drafts
Revises: fase6_f10_verbas_snapshot
Create Date: 2026-08-05

Tabela ÚNICA onde todo rascunho criado pelo chat/agente vive até um humano aprovar
na Central de Aprovações. NADA aqui é executado: `payload` guarda os args para o
executor de domínio rodar SÓ na aprovação. Propositor = AGENTE (solicitado_por é só
trilha, não exclui ninguém de aprovar) — casa com "o agente cria, eu aprovo" e mata o
fail-closed de admin único. Dinheiro/eSocial: requires_otp=true trava a execução sem OTP.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "central_agent_drafts"
down_revision = "fase6_f10_verbas_snapshot"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("modulo", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'rascunho'")),
        sa.Column("gate", sa.Text(), nullable=False, server_default=sa.text("'🔵'")),
        sa.Column("requires_otp", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("roles_aprovador", ARRAY(sa.Text()), nullable=False),
        sa.Column("criado_por_agente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("solicitado_por", UUID(as_uuid=True), nullable=True),
        sa.Column("solicitado_por_nome", sa.Text(), nullable=True),
        sa.Column("empresa_id", UUID(as_uuid=True), nullable=True),
        sa.Column("entity_ref", sa.Text(), nullable=True),
        sa.Column("erro_execucao", sa.Text(), nullable=True),
        sa.Column("decidido_por", UUID(as_uuid=True), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_drafts_status_created", "agent_drafts", ["status", "created_at"])
    op.create_index("ix_agent_drafts_empresa", "agent_drafts", ["empresa_id"])


def downgrade():
    op.drop_index("ix_agent_drafts_empresa", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_status_created", table_name="agent_drafts")
    op.drop_table("agent_drafts")
