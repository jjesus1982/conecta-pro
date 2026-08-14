"""prepara a Efi: conta 1.1.1.03, coluna banco no pagamento e estado DEVOLVIDO

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-14

Tres coisas que dao para construir ANTES de a conta Efi existir — assim, quando as
credenciais chegarem, o que falta e so o adapter falar com a API.

1. CONTA 1.1.1.03 no plano. Toda entrada e saida vira lancamento no razao pela conta
   do banco; sem ela o extrato da Efi cairia em "conta bancaria desconhecida" e o
   dinheiro ficaria fora da escrituracao — a doenca que este modulo passou 13 e 14/08
   curando.

2. COLUNA `banco` em inter_payments. A tabela ja tem status, OTP, lote_id, auditoria e
   reconciled_bank_tx_id, e e quase agnostica de banco — falta so dizer QUAL. Sem isso
   a alternativa seria erguer um segundo sistema de money-out ao lado do que existe, e
   dois sistemas de dinheiro saindo e como se perde controle.
   Default 'inter' porque as 43 linhas existentes sao todas do Inter.

3. Estado DEVOLVIDO na constraint de status. Um Pix liquidado PODE voltar: a Efi tem o
   status DEVOLVIDO e a homologacao dela ate gera devolucao de proposito (R$4,00 gera
   duas de R$2,00). O desenho que recebemos tratava LIQUIDADO como terminal e nao
   previa a volta — pagamento que volta e some do sistema vira diferenca de saldo sem
   origem.
"""
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) conta do banco Efi no plano, espelhando 1.1.1.01/1.1.1.02
    op.execute("""
        INSERT INTO fin_accounting_accounts
            (id, condominio_id, chart_id, code, name, account_type, nature,
             classification, status, level)
        SELECT gen_random_uuid(), a.condominio_id, a.chart_id,
               '1.1.1.03', 'Banco Efi - Conta Corrente', a.account_type, a.nature,
               a.classification, 'ACTIVE', a.level
        FROM fin_accounting_accounts a
        WHERE a.code = '1.1.1.01'
          AND NOT EXISTS (SELECT 1 FROM fin_accounting_accounts x WHERE x.code = '1.1.1.03')
        LIMIT 1
    """)

    # 2) qual banco executa o pagamento
    op.execute("ALTER TABLE inter_payments ADD COLUMN IF NOT EXISTS banco varchar(12) "
               "NOT NULL DEFAULT 'inter'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_inter_payments_banco ON inter_payments(banco)")
    # Ate aqui a origem vivia dentro do jsonb `destinatario._origem`, sem validacao, e
    # o executor mandava para o INTER qualquer valor que nao fosse 'cora' — um typo
    # pagava pelo banco errado, de outro CNPJ. A constraint faz falhar na porta.
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_banco")
    op.execute("ALTER TABLE inter_payments ADD CONSTRAINT ck_inter_payments_banco "
               "CHECK (banco IN ('inter','cora','efi'))")
    op.execute("COMMENT ON COLUMN inter_payments.banco IS "
               "'inter | cora | efi — qual banco executa. A tabela nasceu so do Inter; "
               "o fluxo D7 (preparar/OTP/aprovar/executar) serve aos tres.'")

    # 3) DEVOLVIDO: Pix liquidado pode voltar
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_status")
    op.execute("""
        ALTER TABLE inter_payments ADD CONSTRAINT ck_inter_payments_status
        CHECK (status IN ('preparado','aprovado','executado','confirmado',
                          'cancelado','erro','aguardando_aprovacao','devolvido'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_status")
    op.execute("""
        ALTER TABLE inter_payments ADD CONSTRAINT ck_inter_payments_status
        CHECK (status IN ('preparado','aprovado','executado','confirmado',
                          'cancelado','erro','aguardando_aprovacao'))
    """)
    op.execute("ALTER TABLE inter_payments DROP CONSTRAINT IF EXISTS ck_inter_payments_banco")
    op.execute("DROP INDEX IF EXISTS idx_inter_payments_banco")
    op.execute("ALTER TABLE inter_payments DROP COLUMN IF EXISTS banco")
    op.execute("DELETE FROM fin_accounting_accounts WHERE code = '1.1.1.03'")
