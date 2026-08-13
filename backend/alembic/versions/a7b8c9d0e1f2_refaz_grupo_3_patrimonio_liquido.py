"""refaz o grupo 3 (PL): linha de servico e aliquota nao sao patrimonio

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-13

O grupo 3 estava corrompido: `3.1.1 Portaria`, `3.1.2 Vigilancia` e `3.1.3
Limpeza` dentro de *Capital Social*, e `3.2.1 ISS 5%` dentro de *Lucros
Acumulados*. Linha de servico e aliquota de imposto no lugar de patrimonio —
alguem usou o grupo 3 como se fosse catalogo.

Seguro refazer: as 8 contas tem **ZERO lancamentos**. Nada a migrar.

Sem PL nao ha balanco (Ativo = Passivo + PL nao fecha), o resultado nunca e
encerrado (2027 somaria em cima de 2026) e distribuicao de lucro isenta nao tem
base escritural.

3.3.01 (Apuracao do Resultado) e conta de PASSAGEM: recebe receita e despesa no
encerramento e volta a zero na mesma operacao. Existe porque `accounting_entries`
tem UM debito e UM credito por linha — sem ela nao da para transferir N contas de
resultado para o PL.
"""

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_REMOVER = ("3.1.1", "3.1.2", "3.1.3", "3.2.1", "3.1.01")

_CRIAR = (
    ("3.1.1.01", "Capital Social Subscrito", "EQUITY", "CREDIT", "ANALYTICAL", 4),
    ("3.2.1.01", "Lucros ou Prejuizos Acumulados", "EQUITY", "CREDIT", "ANALYTICAL", 4),
    ("3.3", "Apuracao do Resultado", "EQUITY", "CREDIT", "SYNTHETIC", 2),
    ("3.3.1.01", "Apuracao do Resultado do Exercicio", "EQUITY", "CREDIT", "ANALYTICAL", 4),
    # Onde mora o que o razao NAO sabe do passado. Mesmo desenho da transitoria de
    # saidas: o balanco fecha desde o primeiro dia e a ignorancia fica com nome e
    # valor, em vez de virar omissao. O capital social real vem do contador.
    ("3.9.9.01", "Saldo de Abertura a Identificar", "EQUITY", "CREDIT", "ANALYTICAL", 4),
)


def upgrade() -> None:
    # DESATIVA, não apaga. A primeira versão fazia DELETE checando
    # `accounting_entries` — e quebrou na FK `fk_line_account`: as contas estão
    # referenciadas por `fin_journal_entry_lines`, o OUTRO razão (o quase-vazio,
    # dívida estrutural conhecida). Conferir um razão e apagar com base nele é
    # como se perde história em base com duas escrituras.
    for code in _REMOVER:
        op.execute(f"""
            UPDATE fin_accounting_accounts
               SET status = 'INACTIVE',
                   name = name || ' [DESATIVADA 13/08: não é patrimônio]'
             WHERE code = '{code}' AND status <> 'INACTIVE'
        """)
    op.execute("UPDATE fin_accounting_accounts SET name = 'Capital Social' WHERE code = '3.1'")
    op.execute("UPDATE fin_accounting_accounts SET name = 'Lucros ou Prejuizos Acumulados' "
               "WHERE code = '3.2'")
    for code, name, tipo, nature, classif, nivel in _CRIAR:
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
    codes = "', '".join(c for c, _, _, _, _, _ in _CRIAR)
    op.execute(f"DELETE FROM fin_accounting_accounts WHERE code IN ('{codes}')")
