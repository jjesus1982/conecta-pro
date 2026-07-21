"""Fase 0 (Task 5): consolida duplicatas do notification_queue + indice unico de dedup.

Pre-mortem E2 (VERIFICADO): o dedup por correlation_id era ilusorio (indice
nao-unico, nunca consultado). Havia 10 grupos duplicados (sst recorrentes + auth
cadastro re-inseridos): 58 linhas -> 16 apos consolidar. Depois desta migration, o
helper enqueue_alert faz UPSERT contra este indice unico (nunca mais duplica).

Revision ID: fase0_notif_dedup
Revises: fase_menos1_consultas_baseline
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase0_notif_dedup"
down_revision = "fase_menos1_consultas_baseline"
branch_labels = None
depends_on = None


def upgrade():
    # Consolida: mantem a linha mais recente por (tenant_id, correlation_id); id desempata.
    op.execute(
        """
        DELETE FROM notification_queue a USING notification_queue b
        WHERE a.correlation_id IS NOT NULL
          AND a.correlation_id = b.correlation_id
          AND a.tenant_id IS NOT DISTINCT FROM b.tenant_id
          AND (a.created_at < b.created_at
               OR (a.created_at = b.created_at AND a.id < b.id));
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_correlation
        ON notification_queue (tenant_id, correlation_id)
        WHERE correlation_id IS NOT NULL;
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_notification_correlation;")
