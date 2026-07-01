"""employees: cct_cargo_id (UUID FK) + adicionais por funcionário (insalub/pericul/ronda).

Idempotente (IF NOT EXISTS / checagem de tipo) — as colunas já existem em produção;
esta migration garante o schema em deploys limpos e registra a revisão.

Revision ID: cct_adicionais_emp_20260701
Revises: turnover_audit_20260701
"""

from alembic import op

revision = "cct_adicionais_emp_20260701"
down_revision = "turnover_audit_20260701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adicionais POR FUNCIONÁRIO (individuais, dependem do posto/atividade — não do cargo)
    op.execute(
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS insalubridade_percentual NUMERIC(5,2) DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS periculosidade_percentual NUMERIC(5,2) DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS adicional_ronda_percentual NUMERIC(5,2) DEFAULT 0"
    )
    # cct_cargo_id: garante que exista como UUID (converte de INTEGER legado se preciso)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='employees' AND column_name='cct_cargo_id'
            ) THEN
                ALTER TABLE employees ADD COLUMN cct_cargo_id uuid;
            ELSIF (
                SELECT data_type FROM information_schema.columns
                WHERE table_name='employees' AND column_name='cct_cargo_id'
            ) <> 'uuid' THEN
                ALTER TABLE employees ALTER COLUMN cct_cargo_id DROP DEFAULT;
                ALTER TABLE employees ALTER COLUMN cct_cargo_id TYPE uuid USING NULL;
            END IF;
        END $$;
        """
    )
    # FK real employees.cct_cargo_id -> cct_cargos.id (se ainda não existir)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='fk_employees_cct_cargo'
            ) AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='cct_cargos') THEN
                ALTER TABLE employees ADD CONSTRAINT fk_employees_cct_cargo
                    FOREIGN KEY (cct_cargo_id) REFERENCES cct_cargos(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_employees_cct_cargo_id ON employees (cct_cargo_id)")


def downgrade() -> None:
    op.execute("ALTER TABLE employees DROP CONSTRAINT IF EXISTS fk_employees_cct_cargo")
    op.execute("DROP INDEX IF EXISTS ix_employees_cct_cargo_id")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS insalubridade_percentual")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS periculosidade_percentual")
    op.execute("ALTER TABLE employees DROP COLUMN IF EXISTS adicional_ronda_percentual")
