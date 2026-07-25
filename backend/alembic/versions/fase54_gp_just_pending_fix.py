"""fase5.4 — normaliza gp_justifications status 'pending' (EN) -> 'pendente' (PT canônico)

Revision ID: fase54_gp_just_fix
Revises: p5_3_proativo_state_regra
"""
from alembic import op

revision = "fase54_gp_just_fix"
down_revision = "p5_3_proativo_state_regra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotente: só toca linhas que ainda estão no valor EN antigo.
    op.execute(
        "UPDATE gp_justifications SET status = 'pendente' WHERE status = 'pending'"
    )


def downgrade() -> None:
    # Sem downgrade destrutivo: não re-inglesamos o dado (o canônico é 'pendente').
    pass
