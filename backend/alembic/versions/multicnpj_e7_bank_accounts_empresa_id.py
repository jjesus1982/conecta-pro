"""Multi-CNPJ E7: bank_accounts.empresa_id (vínculo banco↔empresa por FK, não por JSON).

Achado de integridade (auditoria 20/07 #8): bank_accounts não tinha empresa_id — o
vínculo da conta com a empresa era só uma string dentro de integration_config (JSON),
sem integridade referencial. Roteamento de dinheiro (Inter=Eletrônica, Cora=Patrimonial)
dependia de string livre e o fluxo de caixa não conseguia segregar por CNPJ.

Aditiva: coluna empresa_id (UUID), backfill por bank_code (077=Inter→Eletrônica,
403=Cora→Patrimonial, demais→principal), índice. UUID resolvido em runtime pelo slug
(portável entre ambientes); num DB novo sem empresas/contas, o backfill é no-op.

Revision ID: multicnpj_e7_bank_empresa
Revises: multicnpj_e6_certidoes
Create Date: 2026-07-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "multicnpj_e7_bank_empresa"
down_revision = "multicnpj_e6_certidoes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bank_accounts",
        sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    conn = op.get_bind()
    elet = conn.execute(
        sa.text("SELECT id FROM empresas WHERE slug='conecta_eletronica'")
    ).scalar()
    patr = conn.execute(
        sa.text("SELECT id FROM empresas WHERE slug='conecta_patrimonial'")
    ).scalar()
    # Cora (403) → Patrimonial; todo o resto (Inter 077 e legados) → Eletrônica/principal.
    if patr:
        conn.execute(
            sa.text(
                "UPDATE bank_accounts SET empresa_id=:p "
                "WHERE empresa_id IS NULL AND bank_code = '403'"
            ),
            {"p": patr},
        )
    if elet:
        conn.execute(
            sa.text(
                "UPDATE bank_accounts SET empresa_id=:e "
                "WHERE empresa_id IS NULL AND (bank_code <> '403' OR bank_code IS NULL)"
            ),
            {"e": elet},
        )
    op.create_index("ix_bank_accounts_empresa_id", "bank_accounts", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_accounts_empresa_id", table_name="bank_accounts")
    op.drop_column("bank_accounts", "empresa_id")
