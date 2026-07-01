"""sprint94: proposta multi-prazo + recorrencia

Revision ID: sprint94_proposal_terms
Revises: sprint93_client_email_nullable
Create Date: 2026-06-10

Cria proposal_term_options (opcoes de prazo/mensalidade por proposta) + 3 colunas
em proposals: billing_type (recurring|one_time), selected_term_option_id (FK->option
escolhida) e reference_number (numero original do PDF, ex. 00091).

Manual (NAO autogenerate). rev id curto (<=32 chars; alembic_version e varchar(32)).
gen_random_uuid() confirmado disponivel no banco (pg13+/pgcrypto).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "sprint94_proposal_terms"
down_revision = "sprint93_client_email_nullable"
branch_labels = None
depends_on = None


def upgrade():
    # (a) tabela de opcoes de prazo (criada ANTES da FK em proposals)
    op.create_table(
        "proposal_term_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("monthly_value", sa.Float(), nullable=False),  # double, consistente com proposals.total
        sa.Column("composition", postgresql.JSONB(), nullable=True),  # [{name,value}] fiel ao PDF
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_proposal_term_options_proposal_id", "proposal_term_options", ["proposal_id"])

    # (b)(c)(d) novas colunas em proposals
    op.add_column("proposals", sa.Column("billing_type", sa.String(length=20), nullable=False, server_default="recurring"))
    op.add_column("proposals", sa.Column("selected_term_option_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("proposals", sa.Column("reference_number", sa.String(length=50), nullable=True))

    # (e) FK selected_term_option_id -> proposal_term_options.id (DEPOIS da tabela existir)
    op.create_foreign_key(
        "fk_proposals_selected_term_option",
        "proposals",
        "proposal_term_options",
        ["selected_term_option_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    # ordem inversa
    op.drop_constraint("fk_proposals_selected_term_option", "proposals", type_="foreignkey")
    op.drop_column("proposals", "reference_number")
    op.drop_column("proposals", "selected_term_option_id")
    op.drop_column("proposals", "billing_type")
    op.drop_index("ix_proposal_term_options_proposal_id", table_name="proposal_term_options")
    op.drop_table("proposal_term_options")
