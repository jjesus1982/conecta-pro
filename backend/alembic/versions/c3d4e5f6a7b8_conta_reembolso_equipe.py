"""conta de reembolso de equipe: separa despesa reembolsada de remuneracao

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-11

Por que existe: R$56,85 de "Café treinamento mirante das flores" estava
classificado como `pj_prolabore` — ou seja, entrando como REMUNERAÇÃO do Eliziel.
Não é: é despesa da empresa que ele adiantou. Jordan mandou separar em 11/08.

Não é caso isolado: a base tem 43 saídas com a categoria legada `reembolso`
(R$621,01) — iFood, Uber, material comprado por colaborador. Padrão recorrente,
que estava indo para a transitória por falta de conta.
"""

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

_CODE = "5.1.1.08"
_NAME = "Reembolsos e Despesas de Equipe"


def upgrade() -> None:
    op.execute(f"""
        INSERT INTO fin_accounting_accounts
            (id, condominio_id, chart_id, code, name, account_type, nature,
             classification, status, level)
        SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
               '{_CODE}', '{_NAME}', 'EXPENSE', 'DEBIT', 'ANALYTICAL', 'ACTIVE', 4
        FROM fin_accounting_accounts a
        WHERE a.code = '1.1.1.01'
          AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '{_CODE}')
        LIMIT 1
    """)


def downgrade() -> None:
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code = '{_CODE}'")
