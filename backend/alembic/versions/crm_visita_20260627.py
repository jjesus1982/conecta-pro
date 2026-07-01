"""crm_visit_reports + crm_meetings — Assistente de Visita Técnica & Comercial (José Luís)

Captura de visita (fotos/áudios/vídeos analisados → achados), relatório técnico+comercial
estruturado, PDF, cadastro de lead/oportunidade e agendamento de reunião com confirmação.

Revision ID: crm_visita_20260627   (<=32 chars)
Revises: crm_negociacao_20260626
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "crm_visita_20260627"
down_revision = "crm_negociacao_20260626"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_visit_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cliente_nome", sa.String(255), nullable=True),
        sa.Column("cliente_id", UUID(as_uuid=False), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        sa.Column("deal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("data_visita", sa.Date(), nullable=True),
        sa.Column("panorama", sa.Text(), nullable=True),
        sa.Column("achados", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("situacao_atual", sa.Text(), nullable=True),
        sa.Column("diagnostico_tecnico", sa.Text(), nullable=True),
        sa.Column("oportunidade_comercial", sa.Text(), nullable=True),
        sa.Column("proximos_passos", sa.Text(), nullable=True),
        sa.Column("conteudo_md", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="rascunho"),
        sa.Column("criado_por", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_crm_visit_cliente", "crm_visit_reports", ["cliente_nome"])
    op.create_index("ix_crm_visit_status", "crm_visit_reports", ["status"])

    op.create_table(
        "crm_meetings",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("cliente_nome", sa.String(255), nullable=True),
        sa.Column("lead_id", UUID(as_uuid=False), nullable=True),
        sa.Column("deal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("visit_report_id", UUID(as_uuid=False), nullable=True),
        sa.Column("quando", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local", sa.String(255), nullable=True),
        sa.Column("tipo", sa.String(30), nullable=False, server_default="reuniao"),
        sa.Column("status", sa.String(20), nullable=False, server_default="sugerido"),
        sa.Column("lembrete_enviado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("criado_por", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_crm_meetings_quando", "crm_meetings", ["quando"])
    op.create_index("ix_crm_meetings_status", "crm_meetings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_crm_meetings_status", table_name="crm_meetings")
    op.drop_index("ix_crm_meetings_quando", table_name="crm_meetings")
    op.drop_table("crm_meetings")
    op.drop_index("ix_crm_visit_status", table_name="crm_visit_reports")
    op.drop_index("ix_crm_visit_cliente", table_name="crm_visit_reports")
    op.drop_table("crm_visit_reports")
