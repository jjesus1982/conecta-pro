"""Amarra a cotação de compra à VISITA que originou o projeto.

31/08/2026. O Jordan disse, olhando a tela de aprovação: *"da forma como tá hoje não
adianta nada"*. A cotação existia solta — uma lista de palavras sem projeto. "cabo" não
sabia que era para 64 câmeras IP PoE em topologia descentralizada, mesmo com isso escrito
no relatório da visita, no mesmo banco.

O contexto já existia e estava DESLIGADO. Esta coluna é o fio.

Nullable de propósito: cotação de material de estoque não nasce de visita, e exigir o
vínculo quebraria as que já existem.

Revision ID: cotacao_visita_20260831
"""
from alembic import op
import sqlalchemy as sa

revision = "cotacao_visita_20260831"
down_revision = "empresa_id_catalogo_20260828"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    ja = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='purchase_quotations' AND column_name='visit_report_id'")).scalar()
    if not ja:
        op.add_column("purchase_quotations",
                      sa.Column("visit_report_id", sa.dialects.postgresql.UUID(as_uuid=False),
                                nullable=True))
        op.create_foreign_key("fk_pq_visit_report", "purchase_quotations",
                              "crm_visit_reports", ["visit_report_id"], ["id"],
                              ondelete="SET NULL")
        op.create_index("ix_pq_visit_report", "purchase_quotations", ["visit_report_id"])

    # Backfill nominal e NARROW: só a cotação do The Sun, cujo vínculo é conhecido — a
    # mensagem saiu para o Renier a partir do escopo dessa visita. Não infiro vínculo de
    # nenhuma outra: cotação antiga sem visita fica sem visita, que é a verdade.
    conn.execute(sa.text(
        "UPDATE purchase_quotations SET visit_report_id = v.id "
        "FROM crm_visit_reports v "
        "WHERE purchase_quotations.number = 'HAWKEYE-202608311512' "
        "  AND v.id::text LIKE '5307691d%' "
        "  AND purchase_quotations.visit_report_id IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_pq_visit_report", table_name="purchase_quotations")
    op.drop_constraint("fk_pq_visit_report", "purchase_quotations", type_="foreignkey")
    op.drop_column("purchase_quotations", "visit_report_id")
