"""nfse: separa "pedi o cancelamento" de "o ADN cancelou"

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-13

Julho fechou R$378.286,98 — R$108.386,92 acima do real. Dois pares do MESMO
servico foram faturados pelos DOIS CNPJs na transicao (n109/n13 Laranjeiras e
n111/n21 Ideal Flores), e as duas notas da Eletronica (codigo de servico 110201,
"Vigilancia, seguranca ou monitoramento" — servico humanizado, que a partir de
julho e da Patrimonial) foram postas em cancelamento pelo Jordan.

`cancelada` continua sendo o que o AMBIENTE NACIONAL diz: os eventos e105101 /
e105102 escrevem nela. Marcar a mao ali confundiria o pedido com a confirmacao —
e um cancelamento REJEITADO no gov ficaria para sempre fora do faturamento sem
ninguem descobrir.

`cancelamento_solicitado_em` guarda o pedido. O sync do ADN a LIMPA quando o
evento chega: coluna preenchida = pedimos e o gov ainda nao confirmou. O oraculo
do painel fiscal acusa qualquer pedido parado ha mais de 30 dias.
"""
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE nfse_emitidas_nacional "
        "ADD COLUMN IF NOT EXISTS cancelamento_solicitado_em timestamptz"
    )
    op.execute(
        "COMMENT ON COLUMN nfse_emitidas_nacional.cancelamento_solicitado_em IS "
        "'Pedido de cancelamento feito por nos. NULL quando o ADN confirma (evento e105101/e105102). "
        "Preenchido = aguardando o gov.'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE nfse_emitidas_nacional DROP COLUMN IF EXISTS cancelamento_solicitado_em"
    )
