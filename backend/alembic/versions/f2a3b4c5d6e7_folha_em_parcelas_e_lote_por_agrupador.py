"""folha em parcelas (adiantamento 40% + saldo 60%) e lote por agrupador

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-14

Ate aqui a empresa so pagou salario INTEGRAL, uma vez por competencia. Em 20/08/2026
paga pela primeira vez um adiantamento de 40%, e o saldo de 60% por volta de 05/09.
Quatro coisas no sistema impediam isso — todas medidas, nenhuma suposta:

1. `uq_payroll_payment_emp_mes_ano UNIQUE (employee_id, mes, ano)` — a MESMA pessoa
   nao podia ter dois pagamentos na mesma competencia. O segundo INSERT era recusado
   pelo Postgres. Vira `(employee_id, mes, ano, parcela)`.

2. Nao existia conceito de parcela. `valor_liquido` era o liquido cheio e ponto.
   Agora `valor_liquido` e o valor DESTA parcela (e o que sai do banco, e o que o
   extrato tem que casar), e `parcela`/`parcelas_total` dizem de qual pedaco se
   trata. O liquido cheio continua vivendo em `hr_payslips.net_salary`, que e do DP
   — nao se duplica numero de dinheiro em duas tabelas.

3. A JANELA de fechamento era fixa: "dia 1 a 20 do mes SEGUINTE a competencia".
   Um adiantamento pago no dia 20 do PROPRIO mes cai fora dela e ficaria eternamente
   sem par — o mesmo defeito que deixou 12 pagamentos pendurados por meses ate
   14/08/2026. Por isso `data_prevista`: a janela passa a ser em volta da data que a
   parcela deveria sair, e nao de uma regra decorada.

4. `uq_lote_ref UNIQUE (referencia)` com referencia `ORDEM-<BANCO>-<competencia>`
   permitia UM lote por banco por mes. Lote por condominio/posto precisa de varios,
   e cada parcela e outro lote. Referencia passa a caber agrupador e parcela — por
   isso ela cresce de 40 para 80 caracteres.
"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) parcela
    op.execute("ALTER TABLE payroll_payments ADD COLUMN IF NOT EXISTS parcela smallint "
               "NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE payroll_payments ADD COLUMN IF NOT EXISTS parcelas_total smallint "
               "NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE payroll_payments ADD COLUMN IF NOT EXISTS data_prevista date")
    op.execute("ALTER TABLE payroll_payments DROP CONSTRAINT IF EXISTS ck_payroll_parcela")
    op.execute("ALTER TABLE payroll_payments ADD CONSTRAINT ck_payroll_parcela "
               "CHECK (parcela >= 1 AND parcelas_total >= 1 AND parcela <= parcelas_total)")
    op.execute("COMMENT ON COLUMN payroll_payments.valor_liquido IS "
               "'Valor DESTA parcela — o que sai do banco e o que o extrato casa. O liquido "
               "cheio da competencia vive em hr_payslips.net_salary (dominio do DP).'")
    op.execute("COMMENT ON COLUMN payroll_payments.data_prevista IS "
               "'Quando esta parcela deve sair. Define a janela de conciliacao; sem ela o "
               "adiantamento pago no dia 20 do proprio mes cairia fora da busca.'")

    # 2) a unique passa a incluir a parcela
    op.execute("ALTER TABLE payroll_payments DROP CONSTRAINT IF EXISTS uq_payroll_payment_emp_mes_ano")
    op.execute("DROP INDEX IF EXISTS uq_payroll_payment_emp_mes_ano")
    op.execute("ALTER TABLE payroll_payments ADD CONSTRAINT uq_payroll_payment_emp_mes_ano_parcela "
               "UNIQUE (employee_id, mes, ano, parcela)")

    # 3) lote por agrupador (posto hoje; cliente quando o cadastro do operacional
    #    estiver correto — medido em 14/08: cliente_nome falta em 13 de 52 e cruza
    #    com o posto, entao agrupar por cliente hoje montaria lote errado)
    op.execute("ALTER TABLE folha_lote_ordem ADD COLUMN IF NOT EXISTS agrupador varchar(60)")
    op.execute("ALTER TABLE folha_lote_ordem ADD COLUMN IF NOT EXISTS parcela smallint "
               "NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE folha_lote_ordem ALTER COLUMN referencia TYPE varchar(80)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lote_ordem_comp ON folha_lote_ordem(competencia, parcela)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_lote_ordem_comp")
    op.execute("ALTER TABLE folha_lote_ordem DROP COLUMN IF EXISTS parcela")
    op.execute("ALTER TABLE folha_lote_ordem DROP COLUMN IF EXISTS agrupador")
    op.execute("ALTER TABLE payroll_payments DROP CONSTRAINT IF EXISTS uq_payroll_payment_emp_mes_ano_parcela")
    op.execute("ALTER TABLE payroll_payments ADD CONSTRAINT uq_payroll_payment_emp_mes_ano "
               "UNIQUE (employee_id, mes, ano)")
    op.execute("ALTER TABLE payroll_payments DROP CONSTRAINT IF EXISTS ck_payroll_parcela")
    op.execute("ALTER TABLE payroll_payments DROP COLUMN IF EXISTS data_prevista")
    op.execute("ALTER TABLE payroll_payments DROP COLUMN IF EXISTS parcelas_total")
    op.execute("ALTER TABLE payroll_payments DROP COLUMN IF EXISTS parcela")
