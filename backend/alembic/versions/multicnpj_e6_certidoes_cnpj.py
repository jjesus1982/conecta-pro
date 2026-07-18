"""Multi-CNPJ E6: certidões (ged_certidoes) por CNPJ.

Risco alto do pré-mortem (F4): sem dimensão de CNPJ, um "FGTS regular" verde do
CNPJ1 mascara irregularidade do CNPJ2 (o empregador real). Além disso o sync
iterava CNPJs de clientes sobrescrevendo as mesmas linhas (chave era só o tipo).

Aditiva: coluna cnpj (14 dígitos), backfill = CNPJ1, unique (cnpj, document_type).

Revision ID: multicnpj_e6_certidoes
Revises: multicnpj_e5_fiscal
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op

revision = "multicnpj_e6_certidoes"
down_revision = "multicnpj_e5_fiscal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ged_certidoes", sa.Column("cnpj", sa.String(14), nullable=True))
    op.execute("UPDATE ged_certidoes SET cnpj = '35710481000103' WHERE cnpj IS NULL")
    op.create_index(
        "uq_ged_certidoes_cnpj_tipo",
        "ged_certidoes",
        ["cnpj", "document_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ged_certidoes_cnpj_tipo", table_name="ged_certidoes")
    op.drop_column("ged_certidoes", "cnpj")
