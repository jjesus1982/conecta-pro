"""crm_negociacao_state — orquestração José Luís ↔ Jordan (acompanhamento de negociação)

Estado por negociação (proposta): quem está conduzindo (José Luís ou Jordan), última
resposta do cliente, último lembrete enviado ao dono. Suporta: pausar quando o Jordan
assume, lembrar pendências (3 dias → 1x/dia) e o resumo diário.

Revision ID: crm_negociacao_20260626   (<=32 chars)
Revises: crm_followups_20260626
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_negociacao_20260626"
down_revision = "crm_followups_20260626"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_negociacao_state",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("proposal_id", UUID(as_uuid=False), nullable=True, unique=True),
        sa.Column("deal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("cliente_id", UUID(as_uuid=False), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        sa.Column("phone_canonical", sa.String(20), nullable=True),
        sa.Column("cliente_nome", sa.String(255), nullable=True),
        # responsavel: 'jose_luis' (acompanha sozinho) | 'jordan' (dono assumiu, pausa tudo) | 'fechado'
        sa.Column("responsavel", sa.String(20), nullable=False, server_default="jose_luis"),
        sa.Column("ultimo_status", sa.Text(), nullable=True),
        sa.Column("last_client_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposta_enviada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_negociacao_responsavel", "crm_negociacao_state", ["responsavel"])
    op.create_index("ix_negociacao_cliente", "crm_negociacao_state", ["cliente_id"])
    op.create_index("ix_negociacao_phone", "crm_negociacao_state", ["phone_canonical"])

    # lembretes/agenda do dono (José Luís lembra o Jordan): "me lembra amanhã de X"
    op.create_table(
        "crm_owner_reminder",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quando", sa.DateTime(timezone=True), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("enviado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_owner_reminder_due", "crm_owner_reminder", ["enviado", "quando"])


def downgrade() -> None:
    op.drop_index("ix_owner_reminder_due", table_name="crm_owner_reminder")
    op.drop_table("crm_owner_reminder")
    op.drop_index("ix_negociacao_phone", table_name="crm_negociacao_state")
    op.drop_index("ix_negociacao_cliente", table_name="crm_negociacao_state")
    op.drop_index("ix_negociacao_responsavel", table_name="crm_negociacao_state")
    op.drop_table("crm_negociacao_state")
