"""contas da cadeia do caixa: transitorias, diarista, socio, transferencia

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-08-11
"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1f2c3d4e5f6"
branch_labels = None
depends_on = None

# (code, name, account_type, nature). Espelha plano_contas_caixa.py — mudar um
# sem o outro deixa lançamento apontando para conta que não existe no plano, e
# o balancete mostra "(conta não mapeada)".
#
# Valores em MAIÚSCULA e em inglês porque é o que as 70 contas existentes usam
# (ASSET/LIABILITY/EXPENSE/REVENUE, DEBIT/CREDIT, ANALYTICAL, ACTIVE) — as
# colunas são enums do Postgres, não texto livre.
_CONTAS = (
    ("5.1.1.07", "Diaristas e Coberturas", "EXPENSE", "DEBIT"),
    ("2.1.5.01", "Socios - Conta Corrente", "LIABILITY", "CREDIT"),
    ("1.1.9.01", "Transferencias entre Empresas do Grupo", "ASSET", "DEBIT"),
    ("2.1.2.09", "Tributos a Recolher - a identificar", "LIABILITY", "CREDIT"),
    ("5.9.9.01", "Saidas a Classificar (transitoria)", "EXPENSE", "DEBIT"),
    ("4.9.9.01", "Entradas a Classificar (transitoria)", "REVENUE", "CREDIT"),
)


def upgrade() -> None:
    # condominio_id e chart_id vêm de uma conta existente: o plano é único e
    # herdar evita inventar tenant. Sem conta no plano, o balancete rotula
    # "(conta não mapeada no plano)" e a escrituração fica ilegível.
    for code, name, tipo, nature in _CONTAS:
        op.execute(f"""
            INSERT INTO fin_accounting_accounts
                (id, condominio_id, chart_id, code, name, account_type, nature,
                 classification, status, level)
            SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
                   '{code}', '{name}', '{tipo}', '{nature}', 'ANALYTICAL', 'ACTIVE',
                   length('{code}') - length(replace('{code}', '.', '')) + 1
            FROM fin_accounting_accounts a
            WHERE a.code = '1.1.1.01'
              AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '{code}')
            LIMIT 1
        """)


def downgrade() -> None:
    codes = "', '".join(c for c, _, _, _ in _CONTAS)
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code IN ('{codes}')")
