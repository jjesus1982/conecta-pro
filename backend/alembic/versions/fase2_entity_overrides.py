"""Fase 2 (2.A): auto-preenche entity_client_override por match DETERMINÍSTICO de CNPJ.

Resolve a fratura de identidade (pré-mortem A3) SEM fabricar: liga por documento.
- condominiums (EN, órfãos) → clients por CNPJ (10/10 casaram).
- nfses (órfãs) → clients por tomador_cpf_cnpj (26 casaram).
Idempotente (ON CONFLICT DO NOTHING). Em env limpo sem dados, insere 0.
Aging→cliente e processo→cliente continuam quebrados na ORIGEM (dado ausente) — não
inventados; ficam para o Jordan resolver no fluxo operacional do ERP.

Revision ID: fase2_entity_overrides
Revises: fase4_feedback_consultas
Create Date: 2026-07-21
"""

from alembic import op

revision = "fase2_entity_overrides"
down_revision = "fase4_feedback_consultas"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO entity_client_override (satellite_type, satellite_id, client_key, cnpj, nota)
        SELECT 'condominium_en', cd.id::text, c.id, c.document_number,
               'auto: match CNPJ condominiums<->clients'
        FROM condominiums cd JOIN clients c
          ON regexp_replace(coalesce(c.document_number,''),'[^0-9]','','g')
           = regexp_replace(coalesce(cd.cnpj,''),'[^0-9]','','g')
        WHERE nullif(trim(cd.cnpj),'') IS NOT NULL
        ON CONFLICT (satellite_type, satellite_id) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO entity_client_override (satellite_type, satellite_id, client_key, cnpj, nota)
        SELECT DISTINCT 'nfse', n.id::text, c.id, c.document_number,
               'auto: match tomador_cpf_cnpj<->clients'
        FROM nfses n JOIN clients c
          ON regexp_replace(coalesce(c.document_number,''),'[^0-9]','','g')
           = regexp_replace(coalesce(n.tomador_cpf_cnpj,''),'[^0-9]','','g')
        WHERE nullif(trim(n.tomador_cpf_cnpj),'') IS NOT NULL
        ON CONFLICT (satellite_type, satellite_id) DO NOTHING;
        """
    )


def downgrade():
    op.execute("DELETE FROM entity_client_override WHERE nota LIKE 'auto:%';")
