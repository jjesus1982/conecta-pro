"""crm: timeline cross-entidade (crm_activities) + tarefas (crm_tasks)

Revision ID: crm_timeline_tasks_20260623
Revises: dp_ferias_20260618
Create Date: 2026-06-23

Autorizado por Jordan (chat) p/ esta missão, com backup (backups/rebuild/
backup_pre_timeline_tasks_20260623.dump) e âncora (conecta-pro-backend:pre-timeline-tasks-20260623).

1) crm_activities: client_id -> nullable + colunas lead_id/opportunity_id/proposal_id (nullable,
   indexadas) p/ a timeline ligar lead/deal/proposta, não só cliente. Aditivo/reversível.
2) crm_tasks: tabela nova de tarefas/lembretes (vazia, sem FK rígida — segue padrão dos novos models).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_timeline_tasks_20260623"
down_revision = "dp_ferias_20260618"
branch_labels = None
depends_on = None


def upgrade():
    # --- 1) crm_activities: timeline cross-entidade ---
    op.alter_column("crm_activities", "client_id", existing_type=UUID(), nullable=True)
    for col in ("lead_id", "opportunity_id", "proposal_id"):
        op.add_column("crm_activities", sa.Column(col, UUID(as_uuid=False), nullable=True))
        op.create_index(f"ix_crm_activities_{col}", "crm_activities", [col])

    # --- 2) crm_tasks: tarefas/lembretes ---
    op.create_table(
        "crm_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assigned_to_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("created_by_id", UUID(as_uuid=False), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("opportunity_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("client_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("proposal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("crm_tasks")
    for col in ("proposal_id", "opportunity_id", "lead_id"):
        op.drop_index(f"ix_crm_activities_{col}", table_name="crm_activities")
        op.drop_column("crm_activities", col)
    op.alter_column("crm_activities", "client_id", existing_type=UUID(), nullable=False)
