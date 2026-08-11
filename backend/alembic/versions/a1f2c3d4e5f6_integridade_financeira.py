"""integridade financeira: trava de sinal + impressao digital no extrato

Revision ID: a1f2c3d4e5f6
Revises: central_agent_drafts
Create Date: 2026-08-10
"""

from alembic import op

revision = "a1f2c3d4e5f6"
down_revision = "central_agent_drafts"
branch_labels = None
depends_on = None

# Espelha modules/financial/services/integridade.py. Mudar um sem o outro
# deixa o Python e o banco discordando — que é como o defeito nasce.
_ENTRADA = "'credit','credito','pix_recebido','boleto_recebido'"
_SAIDA = "'debit','debito','pix_enviado','boleto_pago','saque','ted'"

# Mesma normalização de descricao_canonica(): tira o código mascarado da
# contraparte, colapsa pontuação e espaço.
_CANONICA = (
    "regexp_replace(regexp_replace(regexp_replace("
    "upper(coalesce(description,'')), 'CP :[0-9]+-', '', 'g'), "
    "'[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g')"
)


def upgrade() -> None:
    # amount = 0 é tolerado (existe 1 linha legítima com valor zero).
    # transaction_type NULL é tolerado (importadores antigos).
    # Tipo CONHECIDO com sinal errado é RECUSADO — era o defeito da Cora.
    # Tipo DESCONHECIDO também é recusado: fail-closed, quem criar um tipo
    # novo declara a direção aqui.
    op.execute(
        f"""
        ALTER TABLE bank_transactions
        ADD CONSTRAINT ck_bank_tx_sinal_coerente CHECK (
            amount = 0
            OR transaction_type IS NULL
            OR (lower(transaction_type) IN ({_ENTRADA}) AND amount > 0)
            OR (lower(transaction_type) IN ({_SAIDA})  AND amount < 0)
        )
        """
    )

    # Índice NÃO-único sobre a impressão digital: acelera a detecção de duplicata
    # (regra `extrato_duplicado`) sem proibir repetição legítima.
    #
    # ponytail: índice ÚNICO foi descartado de propósito. Neste domínio o mesmo
    # valor, no mesmo dia, para a mesma contraparte É legítimo — 3 saques de
    # R$1.000 no Banco24h é limite por operação, não duplicata. Só o ID do próprio
    # banco distinguiria, e ele é nulo em 3.036 das 4.502 linhas. Trocar por índice
    # único quando/se todo importador passar a gravar o ID do banco.
    op.execute(
        f"""
        CREATE INDEX ix_bank_tx_impressao_digital ON bank_transactions (
            bank_account_id, (transaction_date::date), amount, ({_CANONICA})
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bank_tx_impressao_digital")
    op.execute(
        "ALTER TABLE bank_transactions DROP CONSTRAINT IF EXISTS ck_bank_tx_sinal_coerente"
    )
