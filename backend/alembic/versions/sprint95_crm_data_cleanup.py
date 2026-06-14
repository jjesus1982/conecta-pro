"""sprint95: limpeza de dados CRM (leads convertidos + contatos)

Revision ID: sprint95_crm_data_cleanup
Revises: sprint94_proposal_terms
Create Date: 2026-06-14

Correcao de dados encontrada na auditoria CIC:

(BUG 3) 11 leads importados com status invalido 'converted' (NAO existe no enum
LeadStatus; o correto e 'won') e probability=1 (deveria 100). Como
weighted_value = expected_value * probability/100, isso fazia o pipeline ponderado
do Dashboard mostrar 1% do valor real. Normaliza status->won e probability->100.

(BUG 5) Tabela crm_contacts vazia apesar de 11 clientes reais (vindos das NFS-e).
Semeia 1 contato principal por cliente, derivado dos dados reais do proprio cliente
(name/email/phone). Apenas para clientes que ainda nao possuem contato.

Migracao de DADOS (idempotente). Reversivel: downgrade reverte os leads para
'converted'/probability antiga NAO e possivel (valor original perdido), entao o
downgrade apenas remove os contatos semeados (marcados por role='Contato principal'
e is_primary, criados por esta migracao) e deixa os leads como 'won' (estado correto).
rev id curto (<=32 chars; alembic_version e varchar(32)).
"""
from alembic import op

revision = "sprint95_crm_data_cleanup"
down_revision = "sprint94_proposal_terms"
branch_labels = None
depends_on = None


def upgrade():
    # (BUG 3) normaliza leads 'converted' (status invalido) -> 'won' + probability 100
    op.execute(
        """
        UPDATE leads
        SET status = 'won', probability = 100, updated_at = NOW()
        WHERE status = 'converted'
        """
    )

    # (BUG 5) semeia contato principal real por cliente (sem duplicar)
    op.execute(
        """
        INSERT INTO crm_contacts (client_id, name, role, email, phone, is_primary)
        SELECT c.id, c.name, 'Contato principal', LEFT(c.email, 255), LEFT(c.phone, 20), true
        FROM clients c
        WHERE NOT EXISTS (
            SELECT 1 FROM crm_contacts cc WHERE cc.client_id = c.id
        )
        """
    )


def downgrade():
    # Remove apenas os contatos principais semeados por esta migracao.
    # Os leads permanecem 'won' (estado correto; o valor 'converted'/probability=1
    # original era invalido e nao deve ser restaurado).
    op.execute(
        """
        DELETE FROM crm_contacts
        WHERE role = 'Contato principal' AND is_primary = true
        """
    )
