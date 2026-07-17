"""Multi-CNPJ E3: empresa_id (empregador) em employees e hr_payslips.

Aditiva e dormante: colunas NULLABLE + backfill = CNPJ1 (Eletrônica), FKs para
empresas, índices. O flip para a Patrimonial acontece SOMENTE via script de
espelhamento com as datas oficiais da Portte (pré-mortem F2: espelhar, não
assumir). hr_payslips ganha o empregador POR COMPETÊNCIA — folhas históricas
ficam CNPJ1 para sempre (pré-mortem F1: imutabilidade histórica).

Revision ID: multicnpj_e3_employees
Revises: multicnpj_e2_contracts
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "multicnpj_e3_employees"
down_revision = "multicnpj_e2_contracts"
branch_labels = None
depends_on = None

_ELETRONICA_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"


def _add(table: str) -> None:
    op.add_column(
        table,
        sa.Column("empresa_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(f"fk_{table}_empresa_id", table, "empresas", ["empresa_id"], ["id"])
    op.create_index(f"ix_{table}_empresa_id", table, ["empresa_id"])
    op.execute(f"UPDATE {table} SET empresa_id = '{_ELETRONICA_ID}' WHERE empresa_id IS NULL")


def upgrade() -> None:
    _add("employees")
    _add("hr_payslips")


def downgrade() -> None:
    for table in ("hr_payslips", "employees"):
        op.drop_index(f"ix_{table}_empresa_id", table_name=table)
        op.drop_constraint(f"fk_{table}_empresa_id", table, type_="foreignkey")
        op.drop_column(table, "empresa_id")
