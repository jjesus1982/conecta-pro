"""o mesmo boleto nao pode virar duas contas a pagar

Revision ID: 42ddd4d1cb20
Revises: a91f3c7d5e24
Create Date: 2026-08-21

O radar por e-mail le a caixa e cria conta a pagar a partir do codigo de barras. O mesmo
boleto chega mais de uma vez na vida real: o fornecedor reenvia, alguem encaminha, a
rodada roda de novo antes do commit anterior. Sem garantia no BANCO, vira divida em
dobro — e divida em dobro no contas a pagar faz o fluxo de caixa mentir.

Checar com SELECT antes do INSERT nao basta: duas execucoes simultaneas passam as duas
pela verificacao. O indice unico e a unica garantia que nao depende de ordem.

PARCIAL de proposito:
  • so onde `origem = 'boleto_email'` — nao mexe nos 310 pagaveis que ja existem, que
    vem de NFS-e/folha/guia e podem repetir document_number legitimamente;
  • ignora status 'cancelada': boleto cancelado e reemitido com o MESMO codigo de barras
    acontece, e nesse caso o titulo novo tem de poder nascer.

Mesmo padrao de `uq_boleto_vivo_por_codigo` em inter_payments (a3b4c5d6e7f8), que impede
preparar o mesmo pagamento duas vezes.

⚠️ O id desta revisao foi sorteado, nao escolhido a mao: em 19/08 duas sessoes criaram
migrations com o mesmo id inventado, o alembic marcou a revisao como aplicada e rodou so
UMA — a outra sumiu sem erro, e `alembic current` dizia head com a tabela intacta.
"""
from alembic import op

revision = "42ddd4d1cb20"
down_revision = "a91f3c7d5e24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payable_boleto_email
            ON payable_accounts (document_number)
         WHERE origem = 'boleto_email'
           AND document_number IS NOT NULL
           AND status <> 'cancelada'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_payable_boleto_email")
