"""fase5.4 Onda B — op_substituicao_propostas (proposta de substituição de posto)

O agente PROPÕE substituto; o gestor aprova e aplica MANUALMENTE. Operacional
(allocations/escala) permanece READ-ONLY para o agente.

Revision ID: fase54_op_subst
Revises: fase54_notif_idem

NOTA DE DIVERGÊNCIA brief×real: o brief (task-6-brief.md) apontava
down_revision = "fase54_gp_just_fix", mas essa já NÃO é a head da linhagem
fase5.4 — "fase54_notif_idempotency_unique.py" (revision "fase54_notif_idem")
já encadeia em cima dela (down_revision="fase54_gp_just_fix"). A head real
confirmada em disco (nenhuma migration aponta down_revision="fase54_notif_idem")
é "fase54_notif_idem". Encadeado nela para não abrir 2º head na linhagem 5.x.
"""
from alembic import op
import sqlalchemy as sa

revision = "fase54_op_subst"
down_revision = "fase54_notif_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "op_substituicao_propostas",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("post_id", sa.Text(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("ausente_employee_id", sa.Text(), nullable=False),
        sa.Column("substituto_employee_id", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pendente'")),
        sa.Column("proposto_por", sa.Text(), nullable=True),
        sa.Column("aprovado_por", sa.Text(), nullable=True),
        sa.Column("aprovado_em", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False,
                  server_default=sa.text("(now() AT TIME ZONE 'America/Manaus')")),
    )
    op.create_index("ix_op_subst_pendentes", "op_substituicao_propostas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_op_subst_pendentes", table_name="op_substituicao_propostas")
    op.drop_table("op_substituicao_propostas")
