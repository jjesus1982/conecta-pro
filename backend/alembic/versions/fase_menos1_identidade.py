"""Fase -1 (Task 1): views de resolucao de identidade + entity_client_override.

Fecha o risco no1 do pre-mortem (2026-07-21): IDs nao-joinable / entidade fraturada.
- v_employee: normaliza employee_id (uuid em 72 tabelas, varchar em 11) via id_text.
  JOIN por e.id_text = <tabela>.employee_id::text nunca estoura tipo.
- v_condominio_kind: classifica condominio_id em sentinela/escritorio/real/orfao
  (o mesmo condominio_id vale 4 coisas; agregacao futura exclui sentinela/escritorio).
- entity_client_override: costura MANUAL dos orfaos (condominiums EN, nfses) - Jordan
  preenche depois; nada adivinhado.
- entity_client: cliente canonico (clients <- condominios <- customers) + overrides.

SQL pre-validado em transacao com ROLLBACK: v_employee=83(=employees),
entity_client=31, join gp_monthly_closings x v_employee = 50 (uuid x varchar OK).

Revision ID: fase_menos1_identidade
Revises: multicnpj_e8_server_defaults
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase_menos1_identidade"
down_revision = "multicnpj_e8_server_defaults"
branch_labels = None
depends_on = None

_ESCRITORIO = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_SENTINELA = "00000000-0000-0000-0000-000000000001"


def upgrade():
    op.execute(
        "CREATE OR REPLACE VIEW v_employee AS "
        "SELECT id, id::text AS id_text, nome, cpf, empresa_id, cargo, status FROM employees;"
    )
    op.execute(
        f"""
        CREATE OR REPLACE VIEW v_condominio_kind AS
          SELECT DISTINCT condominio_id,
            CASE
              WHEN condominio_id = '{_SENTINELA}' THEN 'sentinela'
              WHEN condominio_id = '{_ESCRITORIO}' THEN 'escritorio'
              WHEN condominio_id IN (SELECT id FROM condominios) THEN 'real'
              ELSE 'orfao'
            END AS kind
          FROM (
            SELECT condominio_id FROM receivable_accounts
            UNION SELECT condominio_id FROM employee_alocacoes
            UNION SELECT condominio_id FROM hr_payslips
          ) s WHERE condominio_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_client_override (
          id bigserial PRIMARY KEY,
          satellite_type text NOT NULL,
          satellite_id   text NOT NULL,
          client_key uuid, cnpj text, nota text,
          created_at timestamptz DEFAULT now(),
          UNIQUE (satellite_type, satellite_id)
        );
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW entity_client AS
          SELECT c.id AS client_key, c.document_number AS cnpj,
                 cd.id AS condominio_id, cu.id AS customer_id, NULL::uuid AS condominium_id
          FROM clients c
          LEFT JOIN condominios cd ON cd.client_id = c.id
          LEFT JOIN customers cu   ON cu.condominio_id = cd.id
          UNION ALL
          SELECT o.client_key, o.cnpj, NULL::uuid, NULL::uuid,
                 CASE WHEN o.satellite_type = 'condominium_en' THEN o.satellite_id::uuid END
          FROM entity_client_override o;
        """
    )


def downgrade():
    op.execute("DROP VIEW IF EXISTS entity_client;")
    op.execute("DROP TABLE IF EXISTS entity_client_override;")
    op.execute("DROP VIEW IF EXISTS v_condominio_kind;")
    op.execute("DROP VIEW IF EXISTS v_employee;")
