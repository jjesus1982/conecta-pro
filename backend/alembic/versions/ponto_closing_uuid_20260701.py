"""Ponto: gp_monthly_closings.employee_id Integer -> String(36) (employees têm UUID).

Seguro: tabela vazia (0 rows). ALTER TYPE com cast explícito.

Revision ID: ponto_closing_uuid_20260701
Revises: cert_feature_20260701
"""

import sqlalchemy as sa
from alembic import op

revision = "ponto_closing_uuid_20260701"
down_revision = "cert_feature_20260701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "gp_monthly_closings",
        "employee_id",
        existing_type=sa.Integer(),
        type_=sa.String(36),
        existing_nullable=False,
        postgresql_using="employee_id::varchar",
    )


def downgrade() -> None:
    op.alter_column(
        "gp_monthly_closings",
        "employee_id",
        existing_type=sa.String(36),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="employee_id::integer",
    )
