"""Multi-CNPJ E2: empresa_id em contracts (dimensão legal da contratada).

Aditiva e dormante: coluna NULLABLE + backfill = CNPJ1 (Eletrônica), FK para
empresas, índice. Nenhum comportamento muda até os consumers lerem a coluna.
A classificação Patrimonial×Eletrônica é aplicada DEPOIS, por regra de negócio
do Jordan (tabela canônica no PRD_MULTI_CNPJ_2026-07-17), nunca por CNAE.

Revision ID: multicnpj_e2_contracts
Revises: lgpd_tables_20260702
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "multicnpj_e2_contracts"
down_revision = "lgpd_tables_20260702"
branch_labels = None
depends_on = None

# UUID canônico do CNPJ1 na tabela empresas (seed sprint67)
_ELETRONICA_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def upgrade() -> None:
    op.add_column(
        "contracts",
        sa.Column("empresa_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_contracts_empresa_id",
        "contracts",
        "empresas",
        ["empresa_id"],
        ["id"],
    )
    op.create_index("ix_contracts_empresa_id", "contracts", ["empresa_id"])
    # Backfill: todo contrato existente pertence ao CNPJ1 até classificação explícita
    op.execute(
        f"UPDATE contracts SET empresa_id = '{_ELETRONICA_ID}' WHERE empresa_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_contracts_empresa_id", table_name="contracts")
    op.drop_constraint("fk_contracts_empresa_id", "contracts", type_="foreignkey")
    op.drop_column("contracts", "empresa_id")
