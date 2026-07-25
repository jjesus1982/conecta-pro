"""proativo_alert_state: renomeia familia -> regra (escopo correto p/ marcar_resolvidos)

Fase 5.3 T3 residual (pós-review): a unidade de resolução tinha que ser a REGRA
(`caixa_baixo_cnpj`, `aging_reforcado`, ...), não a FAMÍLIA (`financeiro`). Uma
família com 2+ regras vazava — se uma regra falhasse na detecção e a outra
tivesse sucesso, `marcar_resolvidos` escopado por família resolvia em massa os
alertas ativos da regra que falhou. Tabela nova (Fase 5.3), vazia em produção
→ rename é seguro e não perde dado.

Revision ID: p5_3_proativo_state_regra
Revises: p5_3_proativo_state
"""
from alembic import op

revision = "p5_3_proativo_state_regra"
down_revision = "p5_3_proativo_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("proativo_alert_state", "familia", new_column_name="regra")


def downgrade() -> None:
    op.alter_column("proativo_alert_state", "regra", new_column_name="familia")
