"""prepara a Asaas: conta 1.1.1.04 no plano e 'asaas' na maquina de pagamento

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-17

A Efi RECUSOU a abertura de conta em 17/08/2026. A Asaas aprovou. O problema que ela
resolve continua sendo o mesmo: a folha e as diarias sao da PATRIMONIAL, e o Cora —
banco da Patrimonial — nao envia PIX por API. Hoje o pagamento sai pelo Inter, que e
da ELETRONICA, e vira mutuo entre empresas todo mes.

A Asaas traz de quebra o que nem a Efi nem o Inter dao: **consulta de chave PIX**. O
`validate_pix_key` do Inter aponta para endpoint que responde 404 e devolve vazio
engolindo o erro — nunca validou nada; e sondei seis formatos, o escopo `dict.read`
nao esta liberado para a nossa aplicacao. Com a Asaas da para fazer o que o app do
banco faz: digitar a chave e ver o nome do titular ANTES de pagar.

Esta migration e so o que da para provar sem credencial:

1. Conta `1.1.1.04` no plano, ao lado de Inter/Cora/Efi. Sem ela o extrato da Asaas
   cairia em "conta bancaria desconhecida" e o dinheiro ficaria fora da escrituracao.
   O razao ja resolve por CODIGO de banco (CONTA_BANCO_POR_CODIGO), entao a conta
   escritura sozinha quando a linha em bank_accounts nascer — sem colar uuid no codigo.

2. `'asaas'` no CHECK de `inter_payments.banco`. O CHECK existe porque a origem viajava
   dentro de um jsonb sem validacao e o executor mandava para o INTER qualquer valor
   desconhecido — um typo pagaria pelo CNPJ errado.

⚠️ O ROTEADOR AINDA NAO TEM BRACO PARA 'asaas' (nem para 'efi'): o valor passa a ser
aceito pela constraint, e `executar` levanta "banco sem executor". Falha limpa, sem
pagar errado — mas e falha. O braco entra quando o adapter existir e for provado
contra a API real.
"""
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO fin_accounting_accounts
            (id, condominio_id, chart_id, code, name, account_type, nature,
             classification, status, level)
        SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
               '1.1.1.04', 'Asaas IP - Conta de Pagamento', a.account_type, a.nature,
               a.classification, 'ACTIVE', a.level
        FROM fin_accounting_accounts a
        WHERE a.code = '1.1.1.01'
          AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '1.1.1.04')
        LIMIT 1
    """)
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_banco")
    op.execute("ALTER TABLE inter_payments ADD CONSTRAINT ck_inter_payments_banco "
               "CHECK (banco IN ('inter','cora','efi','asaas'))")


def downgrade() -> None:
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_banco")
    op.execute("ALTER TABLE inter_payments ADD CONSTRAINT ck_inter_payments_banco "
               "CHECK (banco IN ('inter','cora','efi'))")
    op.execute("DELETE FROM fin_accounting_accounts WHERE code = '1.1.1.04'")
