"""sprint96: ficha de qualificacao estruturada no lead (JSONB)

Revision ID: sprint96_lead_qualif
Revises: sprint95_crm_data_cleanup
Create Date: 2026-06-14

Adiciona coluna leads.qualificacao (JSONB) para guardar a ficha de qualificacao
estruturada que o agente (Jose Luis) coleta na conversa: segmento, tipo_solucao,
seguranca_atual, motivacao, urgencia e — para condominios — tipo_imovel (casas/
apartamentos/misto), unidades, blocos, portoes_veiculares, fluxo_veicular
(entrada_saida_unica | entrada_e_saida_separadas), entradas_pedestres, tem_guarita,
postos_portaria_hoje. JSONB permite evoluir por segmento sem migracao nova a cada
campo, e e filtravel no Postgres.

Reversivel. rev id curto (<=32 chars; alembic_version e varchar(32)).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "sprint96_lead_qualif"
down_revision = "sprint95_crm_data_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "leads",
        sa.Column(
            "qualificacao",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("leads", "qualificacao")
