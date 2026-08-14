"""o mesmo boleto nao pode ter duas ordens vivas ao mesmo tempo

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-14

Em 14/08/2026 o Jordan preparou o MESMO boleto (R$1.060,00, vale-transporte) duas
vezes com 2 minutos de diferenca: uma no Inter e outra no Cora. Nao foi distracao —
o OTP durava 5 minutos, o e-mail demorou, e ele refez. Sobraram duas ordens vivas do
mesmo documento em bancos de CNPJ diferente. Se as duas fossem aprovadas, o boleto
seria pago duas vezes, uma delas pela empresa errada.

Codigo de barras identifica o DOCUMENTO: valor e vencimento estao dentro dele, entao
o boleto do mes seguinte tem outro codigo. Pagar o mesmo codigo duas vezes e sempre
erro — nunca operacao legitima.

Indice PARCIAL: so vale para ordens VIVAS. Cancelada e erro ficam de fora de
proposito, senao uma tentativa que falhou impediria a correta de existir — que e
exatamente a situacao de hoje (a do Inter foi cancelada, a do Cora tem que viver).

A trava vive aqui, no banco, e nao so no servico: o servico da a mensagem legivel,
o indice garante que nao passa nem em corrida entre duas telas abertas.
"""
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Limpa colisao pre-existente antes de criar o indice: se ja houver dois boletos
    # vivos com o mesmo codigo, o CREATE falha e o deploy para. Mantem o mais recente.
    op.execute("""
        UPDATE inter_payments p SET status = 'cancelado',
            observacoes = coalesce(observacoes,'') ||
                ' | [migration a3b4c5d6e7f8] cancelada: outra ordem VIVA do mesmo boleto ja existia'
        WHERE p.payment_type = 'boleto'
          AND p.status NOT IN ('cancelado','erro')
          AND coalesce(p.destinatario->>'codigo_barras','') <> ''
          AND EXISTS (
            SELECT 1 FROM inter_payments o
             WHERE o.payment_type = 'boleto'
               AND o.status NOT IN ('cancelado','erro')
               AND o.destinatario->>'codigo_barras' = p.destinatario->>'codigo_barras'
               AND o.created_at > p.created_at)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_boleto_vivo_por_codigo
            ON inter_payments ((destinatario->>'codigo_barras'))
         WHERE payment_type = 'boleto'
           AND status NOT IN ('cancelado','erro')
           AND coalesce(destinatario->>'codigo_barras','') <> ''
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_boleto_vivo_por_codigo")
