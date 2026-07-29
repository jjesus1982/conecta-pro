"""add empresa_id to fiscal_obligations (multi-CNPJ pareamento)

Revision ID: f5p_empresa_id_fo
Revises: fase56a_fraud_risk_profiles
Create Date: 2026-07-28

Fecha o furo de escopo apontado pela auditoria (graphify 2026-07-28): fiscal_obligations
não tinha empresa_id, então guias da Eletrônica e da Patrimonial na mesma competência
se sobrescreviam. Backfill: guias históricas são todas da Eletrônica (Portte fazia a
Eletrônica em Lucro Real).
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f5p_empresa_id_fo"
down_revision: str | None = "fase56a_fraud_risk_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def upgrade() -> None:
    op.add_column(
        "fiscal_obligations",
        sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_fiscal_obligations_empresa_id", "fiscal_obligations", ["empresa_id"]
    )
    op.execute(
        f"UPDATE fiscal_obligations SET empresa_id = '{ELETRONICA}' WHERE empresa_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_fiscal_obligations_empresa_id", table_name="fiscal_obligations")
    op.drop_column("fiscal_obligations", "empresa_id")
