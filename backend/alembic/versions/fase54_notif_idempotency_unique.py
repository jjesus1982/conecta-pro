"""fase5.4 — índice ÚNICO PARCIAL de idempotência no sino (communication_notifications)

Idempotência atômica da primitiva `propor()`: uma proposta gera N notificações
(uma por aprovador) que COMPARTILHAM a mesma idempotency_key — portanto o unique
NÃO pode ser só na key. A chave real é o par (destinatário, key): re-criar o
mesmo (user_id, idempotency_key) é bloqueado atomicamente pelo banco, mas N
destinatários distintos passam. Combinado com `ON CONFLICT DO NOTHING` no INSERT
do sino, duas execuções concorrentes da MESMA proposta resultam em N (não 2N).

Parcial: WHERE (extra_data->>'idempotency_key') IS NOT NULL — as notificações
legadas (5.3 e anteriores, sem idempotency_key) ficam de fora e não colidem.

Revision ID: fase54_notif_idem
Revises: fase54_gp_just_fix
"""
from alembic import op

revision = "fase54_notif_idem"
down_revision = "fase54_gp_just_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS → migration idempotente. Índice PARCIAL só sobre linhas com
    # idempotency_key não-nulo (rows legadas ficam fora, zero colisão retroativa).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_idempotency_user "
        "ON communication_notifications "
        "(user_id, (extra_data->>'idempotency_key')) "
        "WHERE (extra_data->>'idempotency_key') IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_notif_idempotency_user")
