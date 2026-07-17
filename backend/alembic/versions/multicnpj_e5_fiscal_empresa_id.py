"""Multi-CNPJ E5: empresa_id nas tabelas fiscais + checkpoint de NSU por empresa.

- nfse_emitidas_nacional: emissor era IMPLÍCITO (CNPJ1) — ganha empresa_id,
  backfill = Eletrônica. Notas da Patrimonial importadas depois entram com o id dela.
- nfse_tomadas_nacional / nfe_entradas: tomador/destinatário implícito — idem.
- fiscal_nsu_checkpoint: NSU da DistribuiçãoDFe é POR CNPJ no gov — checkpoint
  por (empresa, tipo) substitui o NSU global/parâmetro solto.

Aditiva/dormante: nada muda até os serviços consumirem as colunas.

Revision ID: multicnpj_e5_fiscal
Revises: multicnpj_e3_employees
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "multicnpj_e5_fiscal"
down_revision = "multicnpj_e3_employees"
branch_labels = None
depends_on = None

_ELETRONICA_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
_TABELAS = ("nfse_emitidas_nacional", "nfse_tomadas_nacional", "nfe_entradas")


def upgrade() -> None:
    for table in _TABELAS:
        op.add_column(
            table,
            sa.Column("empresa_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(f"fk_{table}_empresa_id", table, "empresas", ["empresa_id"], ["id"])
        op.create_index(f"ix_{table}_empresa_id", table, ["empresa_id"])
        op.execute(f"UPDATE {table} SET empresa_id = '{_ELETRONICA_ID}' WHERE empresa_id IS NULL")

    op.create_table(
        "fiscal_nsu_checkpoint",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("empresa_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),  # ex.: 'nfe_dfe', 'nfse_adn'
        sa.Column("ultimo_nsu", sa.String(20), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("empresa_id", "tipo", name="uq_nsu_checkpoint_empresa_tipo"),
    )


def downgrade() -> None:
    op.drop_table("fiscal_nsu_checkpoint")
    for table in reversed(_TABELAS):
        op.drop_index(f"ix_{table}_empresa_id", table_name=table)
        op.drop_constraint(f"fk_{table}_empresa_id", table, type_="foreignkey")
        op.drop_column(table, "empresa_id")
