"""contracts.payment_day — o dia de vencimento é cláusula, não constante

Revision ID: contrato_dia_venc_20260821
Revises:
Create Date: 2026-08-21

O modelo de contrato trazia "até o dia 05 (cinco) de cada mês" como TEXTO FIXO, duas
vezes. O Green Hills negociou dia 8. Sem coluna, o modelo só serviria para um cliente —
e ele foi cadastrado justamente para servir a vários.

`grace_period_days` (já existente, sem consumidor de regra no CRM) passa a guardar a
carência do PRIMEIRO pagamento, que é o que o nome diz.
"""
import sqlalchemy as sa
from alembic import op

revision = "contrato_dia_venc_20260821"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("payment_day", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_contracts_payment_day", "contracts",
        "payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)")


def downgrade() -> None:
    op.drop_constraint("ck_contracts_payment_day", "contracts", type_="check")
    op.drop_column("contracts", "payment_day")
