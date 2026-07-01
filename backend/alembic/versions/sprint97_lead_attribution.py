"""sprint97: campos de atribuicao de marketing no lead (F0+F1 - Conecta Marketing AI)

Revision ID: sprint97_lead_attribution
Revises: sprint96_lead_qualif
Create Date: 2026-06-17

Adiciona campos de ATRIBUICAO de origem ao lead, para fechar o funil
marketing -> lead -> contrato -> receita (CAC/ROAS/ROI por campanha):
  - utm_source/medium/campaign/content/term : tracking de landing/links
  - source_platform : plataforma de origem (meta_ads, google_ads, instagram, ...)
  - mkt_campaign_id : vinculo (solto, sem FK) com marketing_campaigns.id
  - ad_referral (JSONB) : payload de Click-to-WhatsApp (CTWA) vindo do anuncio
    (source_id, source_type, headline, body, ctwa_clid, etc.)

Todas as colunas sao NULLABLE e aditivas -> operacao segura e reversivel,
nao reescreve dados existentes.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "sprint97_lead_attribution"
down_revision = "sprint96_lead_qualif"
branch_labels = None
depends_on = None


_COLS = [
    ("utm_source", sa.String(255)),
    ("utm_medium", sa.String(255)),
    ("utm_campaign", sa.String(255)),
    ("utm_content", sa.String(255)),
    ("utm_term", sa.String(255)),
    ("source_platform", sa.String(50)),
    ("mkt_campaign_id", sa.String(64)),
]


def upgrade():
    for nome, tipo in _COLS:
        op.add_column("leads", sa.Column(nome, tipo, nullable=True))
    op.add_column(
        "leads",
        sa.Column("ad_referral", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("leads", "ad_referral")
    for nome, _ in reversed(_COLS):
        op.drop_column("leads", nome)
