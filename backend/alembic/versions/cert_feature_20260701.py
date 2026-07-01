"""Certificacao Humana (hr_certifications) — gate C rastreavel dos calculos de risco juridico.

Additive: cria 1 tabela nova. Nao toca nada existente. Reversivel (drop na downgrade).

Revision ID: cert_feature_20260701
Revises: crm_loop_20260627
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "cert_feature_20260701"
down_revision = "crm_loop_20260627"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_certifications",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tipo_calculo", sa.String(40), nullable=False),
        sa.Column("referencia_id", sa.String(64), nullable=True),
        sa.Column("referencia_tipo", sa.String(40), nullable=True),
        sa.Column("competencia", sa.String(7), nullable=True),
        sa.Column("employee_id", UUID(as_uuid=False), nullable=True),
        sa.Column("cliente_id", UUID(as_uuid=False), nullable=True),
        sa.Column("calculado_valor", sa.Numeric(14, 2), nullable=True),
        sa.Column("esperado_valor", sa.Numeric(14, 2), nullable=True),
        sa.Column("divergencia", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("divergencia_desc", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("hash_conteudo", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pendente'")),
        sa.Column("certificado_por", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("certificado_em", sa.DateTime(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_hr_certifications_tipo_calculo", "hr_certifications", ["tipo_calculo"])
    op.create_index("ix_hr_certifications_referencia_id", "hr_certifications", ["referencia_id"])
    op.create_index("ix_hr_certifications_competencia", "hr_certifications", ["competencia"])
    op.create_index("ix_hr_certifications_employee_id", "hr_certifications", ["employee_id"])
    op.create_index("ix_hr_certifications_cliente_id", "hr_certifications", ["cliente_id"])
    op.create_index("ix_hr_certifications_status", "hr_certifications", ["status"])
    op.create_index("ix_hr_certifications_hash_conteudo", "hr_certifications", ["hash_conteudo"])


def downgrade() -> None:
    op.drop_table("hr_certifications")
