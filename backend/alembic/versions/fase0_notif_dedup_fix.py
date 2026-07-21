"""Fase 0 (Task 5 FIX): corrige o índice de dedup — inclui user_id.

REGRESSÃO encontrada na auditoria (2026-07-21): o índice único (tenant_id,
correlation_id) quebrava produtores que fazem BROADCAST por destinatário — ex.
`api/v1/endpoints/auth.py::_notificar_admins_novo_cadastro` insere UMA linha por
admin com o MESMO correlation_id (user_id distinto). Com o índice de 2 colunas, o
2o admin dava unique violation → commit falhava → admins NÃO eram notificados de
novos cadastros (silenciosamente, try/except).

Correção: índice (tenant_id, correlation_id, user_id) NULLS NOT DISTINCT (PG16).
- Broadcast por destinatário (user_id distinto) → coexistem.
- Alertas do enqueue_alert (user_id NULL) → NULLS NOT DISTINCT trata NULL como
  igual → continuam deduplicando por (tenant, correlation).

Revision ID: fase0_notif_dedup_fix
Revises: fase0_notif_dedup
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase0_notif_dedup_fix"
down_revision = "fase0_notif_dedup"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS uq_notification_correlation;")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_correlation "
        "ON notification_queue (tenant_id, correlation_id, user_id) "
        "NULLS NOT DISTINCT WHERE correlation_id IS NOT NULL;"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_notification_correlation;")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_correlation "
        "ON notification_queue (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;"
    )
