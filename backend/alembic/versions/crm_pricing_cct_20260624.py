"""crm precificação CCT 2026: parâmetros editáveis + tabela de funções (alinhado à
Planilha_Formacao_Preco_CCT2026_ConectaMais — Lucro Real, divisor, margem 15%).

Revision ID: crm_pricing_cct_20260624
Revises: crm_audit_log_20260624
Create Date: 2026-06-24

Aditivo. Autorizado por Jordan (PROMPT 5).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_pricing_cct_20260624"
down_revision = "crm_audit_log_20260624"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_pricing_params",
        sa.Column("chave", sa.String(40), primary_key=True),
        sa.Column("valor", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column("grupo", sa.String(40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "crm_pricing_funcoes",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("salario_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("jornada_dias", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("noturno", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hora_reduzida", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ronda", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("periculosidade", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("insalubridade", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade():
    op.drop_table("crm_pricing_funcoes")
    op.drop_table("crm_pricing_params")
