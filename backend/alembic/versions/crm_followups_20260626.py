"""crm_followups + crm_followup_optout + fix crm_quotas (NULLS NOT DISTINCT)

PROMPT 7 — follow-up/envio de proposta por WhatsApp (José Luís) + correção do bug de metas
que duplicava linhas com seller_id NULL (NULL != NULL nunca conflita na UNIQUE).

Revision ID: crm_followups_20260626   (<=32 chars: alembic_version é varchar(32))
Revises: crm_pricing_cct_20260624
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "crm_followups_20260626"
down_revision = "crm_pricing_cct_20260624"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── crm_followups: registro de cada toque do José Luís ──────────────────────────────
    op.create_table(
        "crm_followups",
        sa.Column("id", UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("deal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("cliente_id", UUID(as_uuid=False), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        sa.Column("proposal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("phone_e164", sa.String(20), nullable=True),
        sa.Column("phone_canonical", sa.String(20), nullable=True),
        sa.Column("canal", sa.String(20), nullable=False, server_default="whatsapp"),
        sa.Column("template", sa.String(120), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="agendado"),
        sa.Column("agendado_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resposta_texto", sa.Text(), nullable=True),
        sa.Column("resposta_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("classificacao", sa.String(20), nullable=True),
        sa.Column("chatwoot_conversation_id", sa.Integer(), nullable=True),
        sa.Column("chatwoot_message_id", sa.Integer(), nullable=True),
        sa.Column("criado_por", sa.String(120), nullable=True),
        sa.Column("detalhe", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_crm_followups_deal", "crm_followups", ["deal_id"])
    op.create_index("ix_crm_followups_status", "crm_followups", ["status"])
    op.create_index("ix_crm_followups_phone", "crm_followups", ["phone_canonical"])
    op.create_index("ix_crm_followups_sched", "crm_followups", ["agendado_para"])

    # ── crm_followup_optout: respeitar "não quero receber" ──────────────────────────────
    op.create_table(
        "crm_followup_optout",
        sa.Column("phone_canonical", sa.String(20), primary_key=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── FIX crm_quotas: dedup + UNIQUE NULLS NOT DISTINCT ──────────────────────────────
    # Causa do "soma de metas": seller_id NULL nunca conflita (NULL != NULL no Postgres),
    # então cada POST /crm/quotas (meta da empresa, sem vendedor) inseria nova linha.
    # 1) Colapsa duplicatas por (seller_id, ano, mês) mantendo a melhor (maior valor/contagem),
    #    e remove as demais.
    op.execute("""
        WITH ranked AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY COALESCE(seller_id::text,'__company__'), period_year, period_month
                   ORDER BY updated_at DESC NULLS LAST) AS rn,
                 MAX(target_value) OVER (
                   PARTITION BY COALESCE(seller_id::text,'__company__'), period_year, period_month) AS mv,
                 MAX(target_count) OVER (
                   PARTITION BY COALESCE(seller_id::text,'__company__'), period_year, period_month) AS mc
          FROM crm_quotas
        )
        UPDATE crm_quotas q
           SET target_value = r.mv, target_count = r.mc, updated_at = now()
          FROM ranked r
         WHERE q.id = r.id AND r.rn = 1
    """)
    op.execute("""
        DELETE FROM crm_quotas q USING (
          SELECT id, row_number() OVER (
                   PARTITION BY COALESCE(seller_id::text,'__company__'), period_year, period_month
                   ORDER BY updated_at DESC NULLS LAST) AS rn
          FROM crm_quotas) r
        WHERE q.id = r.id AND r.rn > 1
    """)
    # 2) Recria a UNIQUE com NULLS NOT DISTINCT (PG >= 15) — agora seller_id NULL conflita,
    #    e o ON CONFLICT do upsert passa a funcionar para metas da empresa.
    op.execute("ALTER TABLE crm_quotas DROP CONSTRAINT IF EXISTS uq_crm_quota_seller_period")
    op.execute("""
        ALTER TABLE crm_quotas
          ADD CONSTRAINT uq_crm_quota_seller_period
          UNIQUE NULLS NOT DISTINCT (seller_id, period_year, period_month)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE crm_quotas DROP CONSTRAINT IF EXISTS uq_crm_quota_seller_period")
    op.execute("""
        ALTER TABLE crm_quotas
          ADD CONSTRAINT uq_crm_quota_seller_period
          UNIQUE (seller_id, period_year, period_month)
    """)
    op.drop_table("crm_followup_optout")
    op.drop_index("ix_crm_followups_sched", table_name="crm_followups")
    op.drop_index("ix_crm_followups_phone", table_name="crm_followups")
    op.drop_index("ix_crm_followups_status", table_name="crm_followups")
    op.drop_index("ix_crm_followups_deal", table_name="crm_followups")
    op.drop_table("crm_followups")
