"""Fase 4 (4.A): feedback humano nos consultores (util/correcao/feedback_em).

Pré-mortem F4: os consultores 'aprendiam' sem NENHUM sinal de qualidade do gestor.
Esta migration adiciona a coluna de feedback nas 8 tabelas *_consultas: o Jordan
marca 👍/👎 (+ correção opcional) em cada resposta. O placar de aprendizado
(consultor_hub.placar_aprendizado) lê isso; a memória (aprender) passa a preferir o
que foi 👍 e a NÃO reforçar o que foi 👎. É o 'certificar que aprendem'.

Revision ID: fase4_feedback_consultas
Revises: fase0_notif_dedup_fix
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase4_feedback_consultas"
down_revision = "fase0_notif_dedup_fix"
branch_labels = None
depends_on = None

_TBLS = [
    "ceo_consultas", "financial_cfo_consultas", "juridico_consultas", "gedeon_consultas",
    "comercial_consultas", "operacional_consultas", "rh_consultas", "fiscal_consultas",
]


def upgrade():
    for t in _TBLS:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS util boolean;")
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS correcao text;")
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS feedback_em timestamptz;")


def downgrade():
    for t in _TBLS:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS feedback_em;")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS correcao;")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS util;")
