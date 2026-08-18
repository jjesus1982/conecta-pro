"""cadastra a conta Asaas em bank_accounts (banco 461, Patrimonial)

Revision ID: a91f3c7d5e24
Revises: b4c5d6e7f8a9
Create Date: 2026-08-18

⚠️ Esta migration nasceu com o id `c5d6e7f8a9b0` e COLIDIU com uma de outra sessao
(`onvio_por_empresa`), criada em paralelo com o mesmo id. O alembic avisa ("present more
than once"), marca a revisao como aplicada e roda UMA das duas — a outra some sem erro.
Foi o que aconteceu: `alembic current` dizia head, e a conta nao existia. Id trocado para
`a91f3c7d5e24`. Com varias sessoes no mesmo repo, id inventado a mao colide.

Sem esta linha o `asaas_sync_service` levanta "Conta Asaas (bank_code 461) nao
registrada" e o extrato nao entra em lugar nenhum — o dinheiro ficaria fora da
conciliacao. A conta do plano (1.1.1.04) ja existe desde b4c5d6e7f8a9; o razao casa por
CODIGO de banco, entao a escrituracao passa a funcionar sozinha quando esta linha nasce.

EMPRESA = PATRIMONIAL, e isso e o ponto todo: a Asaas entrou porque a folha e as diarias
sao da Patrimonial e o Cora, banco dela, nao envia PIX por API — hoje o pagamento sai
pelo Inter, que e da Eletronica, e vira mutuo entre empresas todo mes. A conta de sandbox
respondeu `owner.name = CONECTAMAIS PATRIMONIAL LTDA` na consulta de chave PIX de
18/08/2026, o que confirma o CNPJ do lado deles.

⚠️ FALTA CONFERIR o CNPJ da conta de PRODUCAO. Se ela estiver na Eletronica, a Asaas nao
resolve o problema que a fez entrar, e esta linha muda de empresa.

allows_receipts = FALSE de proposito: recebimento continua sendo pelo Cora. Esta conta e
so saida (PIX de folha, diarias, VT/VR). Marcar como recebedora faria relatorio de
entrada procurar dinheiro que nunca vai chegar aqui.

Na Asaas nao ha agencia/conta no formato bancario classico — o que existe e o Wallet ID.
Ele NAO cabe em `account_number` (varchar(20) contra 36 caracteres do UUID), e truncar
produziria um identificador que PARECE valido e nao e. Vai para `integration_config`,
que e jsonb e e o lugar de identificador de integracao. `account_number` fica NULL:
ausencia honesta em vez de dado mutilado.
"""
from alembic import op

revision = "a91f3c7d5e24"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None

WALLET = "ccf28918-4025-452a-9c5a-3d3ad38eaf1b"


def upgrade() -> None:
    # Copia condominio_id e os defaults da linha do Cora — mesma empresa (Patrimonial),
    # entao herdar dela e mais seguro que eu chutar uuid de condominio.
    op.execute(f"""
        INSERT INTO bank_accounts
            (id, condominio_id, empresa_id, name, bank_code, bank_name, account_number,
             agency, account_type, status, opening_balance, current_balance,
             blocked_balance, available_balance, is_main_account, allows_payments,
             allows_receipts, allows_transfers, pix_enabled, boleto_enabled, ativo,
             holder_name, holder_document, integration_type, integration_config,
             created_at, updated_at)
        SELECT gen_random_uuid(), c.condominio_id, c.empresa_id,
               'Asaas IP - Patrimonial', '461', 'Asaas IP S.A.', NULL,
               NULL, 'checking', c.status, 0, 0, 0, 0,
               FALSE, TRUE, FALSE, TRUE, TRUE, FALSE, TRUE,
               'CONECTAMAIS PATRIMONIAL LTDA', '66014833000110', 'asaas',
               jsonb_build_object('wallet_id', '{WALLET}'),
               NOW(), NOW()
        FROM bank_accounts c
        WHERE c.bank_code = '403'
          AND NOT EXISTS (SELECT 1 FROM bank_accounts x WHERE x.bank_code = '461')
        LIMIT 1
    """)


def downgrade() -> None:
    op.execute("DELETE FROM bank_accounts WHERE bank_code = '461'")
