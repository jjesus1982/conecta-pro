"""sprint90: cwi_message_log (Fase 2 CRM - atendimento WhatsApp/Chatwoot)

Revision ID: sprint90_cwi_message_log
Revises: findp_b1b2_20260601
Create Date: 2026-06-05

Tabela de LOG (append-only) das mensagens WhatsApp trocadas via Chatwoot/Baileys.
- Sem FK rigida de proposito: log nunca deve falhar ao gravar por questao
  referencial (ex.: criacao de lead em rollback nao pode impedir o registro
  cru da mensagem). client_id/lead_id sao UUID nullable (clients/leads usam UUID).
- Idempotencia do webhook: chatwoot_message_id UNIQUE (NULLs distintos no PG,
  entao multiplas saidas ainda sem id nao colidem).
- phone_canonical: telefone normalizado (so digitos) para casar com leads.phone
  (varchar 20). Normalizacao prevista: remover '+' e, para match com leads, o '55'.
"""
from alembic import op
import sqlalchemy as sa

revision = "sprint90_cwi_message_log"
down_revision = "findp_b1b2_20260601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cwi_message_log",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("direction", sa.String(3), nullable=False),  # 'in' | 'out'
        sa.Column("phone_canonical", sa.String(20), nullable=True),  # so digitos
        sa.Column("chatwoot_conversation_id", sa.Integer, nullable=True),
        sa.Column("chatwoot_message_id", sa.Integer, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("client_id", sa.UUID(), nullable=True),  # sem FK (log append-only)
        sa.Column("lead_id", sa.UUID(), nullable=True),  # sem FK (log append-only)
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # idempotencia do webhook: nao logar a mesma mensagem 2x
    op.create_unique_constraint(
        "uq_cwi_chatwoot_message_id", "cwi_message_log", ["chatwoot_message_id"]
    )
    # match por telefone e busca por conversa
    op.create_index(
        "ix_cwi_phone_canonical", "cwi_message_log", ["phone_canonical"]
    )
    op.create_index(
        "ix_cwi_conversation", "cwi_message_log", ["chatwoot_conversation_id"]
    )


def downgrade():
    op.drop_index("ix_cwi_conversation", "cwi_message_log")
    op.drop_index("ix_cwi_phone_canonical", "cwi_message_log")
    op.drop_constraint(
        "uq_cwi_chatwoot_message_id", "cwi_message_log", type_="unique"
    )
    op.drop_table("cwi_message_log")
