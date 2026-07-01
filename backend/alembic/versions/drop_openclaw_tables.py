"""Remove OpenClaw (Opcao 2 — 2026-05-31): drop das 3 tabelas openclaw_*. Motor de auto-remediacao aposentado.
Downgrade: restaurar do backup backups/openclaw_tables_PRE_DROP_*.dump (recriacao manual nao incluida)."""
from alembic import op
revision="drop_openclaw_tables"; down_revision="camada3_financial_kpis"; branch_labels=None; depends_on=None
def upgrade():
    op.execute("DROP TABLE IF EXISTS openclaw_interventions CASCADE")
    op.execute("DROP TABLE IF EXISTS openclaw_patterns CASCADE")
    op.execute("DROP TABLE IF EXISTS openclaw_knowledge_base CASCADE")
def downgrade():
    pass  # restaurar do dump backups/openclaw_tables_PRE_DROP_*.dump
