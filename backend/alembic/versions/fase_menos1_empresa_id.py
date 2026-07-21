"""Fase -1 (Task 2): empresa_id + quarentena nas 5 tabelas sem discriminador de CNPJ.

Fecha o risco de VAZAMENTO cross-CNPJ (pre-mortem A1): financeiro AR/AP, nfses,
occurrences e leads nao tinham empresa_id, e os 2 CNPJs compartilham o mesmo
condominio_id (escritorio) -> agregar por ele misturaria Eletronica x Patrimonial.

Decisao Jordan (2026-07-21): como nenhuma das 5 tem derivacao DETERMINISTICA de
CNPJ (occurrences.employee_id 100% NULL; nfses sem chave/vinculo; AR/AP carimbados
no escritorio; leads sem vinculo), TODAS vao para QUARENTENA (empresa_review=true,
empresa_id=NULL) - nada e chutado. Jordan reclassifica via relatorio depois.
Guard-rail: agregacao por CNPJ NUNCA inclui linha com empresa_review=true.

Counts: occurrences 4, nfses 27, receivable 22, payable 71, leads 22.

Revision ID: fase_menos1_empresa_id
Revises: fase_menos1_identidade
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase_menos1_empresa_id"
down_revision = "fase_menos1_identidade"
branch_labels = None
depends_on = None

TABELAS = ["occurrences", "nfses", "receivable_accounts", "payable_accounts", "leads"]


def upgrade():
    for t in TABELAS:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS empresa_id uuid;")
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS empresa_review boolean DEFAULT false;")
        # Sem derivacao deterministica -> quarentena total (nunca chuta CNPJ).
        op.execute(f"UPDATE {t} SET empresa_review = true WHERE empresa_id IS NULL;")


def downgrade():
    for t in TABELAS:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS empresa_review;")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS empresa_id;")
