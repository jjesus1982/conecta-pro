"""fase6-f10: termination_processes.verbas_snapshot (snapshot das verbas na finalizacao)

Revision ID: fase6_f10_verbas_snapshot
Revises: f5p_empresa_id_fo
Create Date: 2026-08-01

Coluna ADITIVA-NULLABLE (classe mais segura: nao reescreve dados, nao trava, reversivel).
Guarda o calc COMPLETO de calculate_severance no momento da finalizacao (complete_termination),
para o TRCT no chat renderizar SO do que foi homologado — nunca recalcular (lição do holerite).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "fase6_f10_verbas_snapshot"
down_revision = "f5p_empresa_id_fo"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "termination_processes",
        sa.Column("verbas_snapshot", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("termination_processes", "verbas_snapshot")
