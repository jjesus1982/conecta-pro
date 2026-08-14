"""ordem de pagamento: lote aprovado no sistema, executado no app do banco

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-14

O Cora nao envia PIX por API (confirmado na doc: nem por chave, nem por QR). 99,8%
do que sai da conta da Patrimonial e PIX. Entao o pagamento continua sendo feito no
app do celular — mas o CONTROLE passa a viver aqui.

Inverte a ordem das coisas: hoje e "executado no app, descoberto depois"; passa a ser
"aprovado no sistema, executado no app". O lote nasce RASCUNHO, exige OTP para virar
APROVADO, e so entao os itens ficam 'aguardando_execucao_app'. O extrato do dia
seguinte fecha cada item pelo CPF do favorecido + valor do liquido — regra provada em
14/08/2026 fechando 84 de 96 pagamentos de folha de marco e junho, com zero ambiguo.

NAO cria tabela de OTP: reusa `inter_lote_otp`, que ja e generica (lote_id e uuid
solto, sem FK).

Teto: o guard le CONECTA_LIMITE_DIARIO_PAGAMENTOS (R$100.000). A folha medida em
agosto foi R$94.394,91 — 94% do teto num lote so. Por isso o guard existe aqui e nao
so na tela.
"""
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS folha_lote_ordem (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            referencia    varchar(40)  NOT NULL,
            competencia   varchar(7)   NOT NULL,
            banco         varchar(12)  NOT NULL,
            empresa_id    uuid,
            total_centavos bigint      NOT NULL CHECK (total_centavos > 0),
            qtd_itens     integer      NOT NULL CHECK (qtd_itens > 0),
            status        varchar(24)  NOT NULL DEFAULT 'RASCUNHO',
            criado_por    varchar(120),
            aprovado_por  varchar(120),
            aprovado_em   timestamptz,
            concluido_em  timestamptz,
            observacao    text,
            created_at    timestamptz  NOT NULL DEFAULT now(),
            updated_at    timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT ck_lote_status CHECK (status IN
                ('RASCUNHO','APROVADO','EXECUTANDO','CONCLUIDO','CONCLUIDO_PARCIAL','CANCELADO')),
            CONSTRAINT uq_lote_ref UNIQUE (referencia)
        )
    """)
    op.execute("COMMENT ON TABLE folha_lote_ordem IS "
               "'Lote de pagamentos aprovado no sistema (OTP+teto) e executado no app do banco. "
               "O extrato fecha cada item pelo CPF+valor.'")
    # Vinculo dos itens ao lote. Colunas separadas por tabela — sao dois cadastros
    # distintos (CLT e PJ) e juntar os dois numa tabela unica e outra reforma.
    op.execute("ALTER TABLE payroll_payments ADD COLUMN IF NOT EXISTS lote_ordem_id uuid")
    op.execute("ALTER TABLE financial_pagamentos_pj ADD COLUMN IF NOT EXISTS lote_ordem_id uuid")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payroll_lote ON payroll_payments(lote_ordem_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pj_lote ON financial_pagamentos_pj(lote_ordem_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pj_lote")
    op.execute("DROP INDEX IF EXISTS idx_payroll_lote")
    op.execute("ALTER TABLE financial_pagamentos_pj DROP COLUMN IF EXISTS lote_ordem_id")
    op.execute("ALTER TABLE payroll_payments DROP COLUMN IF EXISTS lote_ordem_id")
    op.execute("DROP TABLE IF EXISTS folha_lote_ordem")
