"""conta de emprestimos de terceiros: divida nao e receita

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-12

Jordan em 12/08: a Denise emprestou R$12.000 em 06/07 para completar o pagamento
da folha de julho, e a empresa devolveu R$12.300 em 11/08 + R$1.000 em 12/08.

A ENTRADA de 06/07 estava lançada D banco / C 1.1.2.01 Clientes — ou seja, como
se um CLIENTE tivesse pago, abatendo R$12.000 de contas a receber que ninguém
devia. Dívida entrando não é cliente pagando.

O plano não tinha conta de empréstimo — só `5.2.3.02 Financiamentos`, que é
DESPESA (5.x). Dinheiro que se toma emprestado é PASSIVO enquanto não se paga.
"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

_CONTAS = (
    ("2.1.6.01", "Emprestimos de Terceiros", "LIABILITY", "CREDIT"),
)


def upgrade() -> None:
    for code, name, tipo, nature in _CONTAS:
        op.execute(f"""
            INSERT INTO fin_accounting_accounts
                (id, condominio_id, chart_id, code, name, account_type, nature,
                 classification, status, level)
            SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
                   '{code}', '{name}', '{tipo}', '{nature}', 'ANALYTICAL', 'ACTIVE', 4
            FROM fin_accounting_accounts a
            WHERE a.code = '1.1.1.01'
              AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '{code}')
            LIMIT 1
        """)


def downgrade() -> None:
    codes = "', '".join(c for c, _, _, _ in _CONTAS)
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code IN ('{codes}')")
