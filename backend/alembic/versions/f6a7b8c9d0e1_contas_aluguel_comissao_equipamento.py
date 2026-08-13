"""contas de comissao e equipamento; aluguel ja existia

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-13

Jordan pediu as categorias de aluguel, comissão e parcelamento (12/08). Elas
faltavam na lista fechada, e por isso saídas com memo CLARO caíam na transitória
todo mês: "Aluguel escritório" R$1.700, "Comissão Vanessa" R$1.000, "Parcela 2/4
TVs" R$1.725.

  • aluguel     → 5.2.1.03 Aluguel e Condominio, que JÁ EXISTIA. Sem conta nova.
  • comissão    → 5.2.1.05, nova. Despesa comercial.
  • equipamento → 1.2.1.01, nova, e é ATIVO, não despesa.

Sobre o terceiro: "parcelamento" é FORMA DE PAGAMENTO, não natureza — e já existe
`2.1.2.04 Parcelamento Simples` para tributo, então a palavra ficaria ambígua. O
que se comprou foram TVs: equipamento. Comprar em 4 parcelas não muda a natureza,
muda o prazo.

⚠️ 1.2.1.01 nasce SEM depreciação. Capitalizar sem depreciar superestima o ativo
com o tempo — é menos errado que jogar R$6.900 de TV em despesa do mês, mas é uma
dívida declarada, não um esquecimento. Depreciação é decisão de política contábil,
e vai junto com o PL.
"""

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

# (code, name, account_type, nature, classification, level)
_CONTAS = (
    ("1.2", "ATIVO NAO CIRCULANTE", "ASSET", "DEBIT", "SYNTHETIC", 2),
    ("1.2.1", "Imobilizado", "ASSET", "DEBIT", "SYNTHETIC", 3),
    ("1.2.1.01", "Equipamentos e Instalacoes", "ASSET", "DEBIT", "ANALYTICAL", 4),
    ("5.2.1.05", "Comissoes sobre Vendas", "EXPENSE", "DEBIT", "ANALYTICAL", 4),
)


def upgrade() -> None:
    for code, name, tipo, nature, classif, nivel in _CONTAS:
        op.execute(f"""
            INSERT INTO fin_accounting_accounts
                (id, condominio_id, chart_id, code, name, account_type, nature,
                 classification, status, level)
            SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
                   '{code}', '{name}', '{tipo}', '{nature}', '{classif}', 'ACTIVE', {nivel}
            FROM fin_accounting_accounts a
            WHERE a.code = '1.1.1.01'
              AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '{code}')
            LIMIT 1
        """)


def downgrade() -> None:
    codes = "', '".join(c for c, _, _, _, _, _ in _CONTAS)
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code IN ('{codes}')")
