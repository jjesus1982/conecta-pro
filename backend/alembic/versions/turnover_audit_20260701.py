"""Turnover: cria turnover_audit_logs (faltou na retention_schema — o dashboard escreve audit).

Revision ID: turnover_audit_20260701
Revises: retention_schema_20260701
"""

from alembic import op

revision = "turnover_audit_20260701"
down_revision = "retention_schema_20260701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    import modules.retention.turnover.models.turnover_models  # noqa: F401
    from core.models import Base

    t = next((x for x in Base.metadata.tables.values() if x.name == "turnover_audit_logs"), None)
    if t is not None:
        t.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS turnover_audit_logs CASCADE")
