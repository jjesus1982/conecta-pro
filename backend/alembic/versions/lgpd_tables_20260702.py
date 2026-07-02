"""LGPD tables: consents, pia_assessments, erasure_requests, audit_logs.

Idempotente — as 4 tabelas já existem em produção (criadas via models direto).
Esta migration garante o schema em deploys limpos. Guarda com inspector.has_table
antes de cada create_table (op.create_table não tem if_not_exists nativo).

Revision ID: lgpd_tables_20260702
Revises: cct_adicionais_emp_20260701
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "lgpd_tables_20260702"
down_revision = "cct_adicionais_emp_20260701"
branch_labels = None
depends_on = None


# Enum value lists (espelham os StrEnum dos models; values_callable usa .value)
_CONSENT_STATUS = ("active", "revoked", "expired", "pending")
_CONSENT_PURPOSE = (
    "marketing",
    "analytics",
    "personalization",
    "service_provision",
    "legal_obligation",
    "vital_interest",
    "public_interest",
    "legitimate_interest",
)
_LEGAL_BASIS = (
    "consent",
    "contract",
    "legal_obligation",
    "vital_interest",
    "public_policy",
    "research",
    "legitimate_interest",
    "credit_protection",
)
_RISK_LEVEL = ("low", "medium", "high", "critical")
_ASSESSMENT_STATUS = ("draft", "in_review", "approved", "rejected", "archived")
_ERASURE_STATUS = ("pending", "in_progress", "completed", "rejected", "partial")
_ERASURE_SCOPE = ("all", "personal", "marketing", "analytics")
_AUDIT_ACTION = (
    "create",
    "read",
    "update",
    "delete",
    "export",
    "consent",
    "login",
    "logout",
    "encrypt",
    "decrypt",
    "mask",
    "erasure",
)
_AUDIT_SEVERITY = ("debug", "info", "warning", "error", "critical")
_RESOURCE_TYPE = ("user", "document", "consent", "data", "system", "audit")


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    # ------------------------------------------------------------------
    # lgpd_consents
    # ------------------------------------------------------------------
    if not insp.has_table("lgpd_consents"):
        op.create_table(
            "lgpd_consents",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("titular_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("titular_email", sa.String(length=255), nullable=False),
            sa.Column(
                "purpose",
                sa.Enum(*_CONSENT_PURPOSE, name="consentpurpose"),
                nullable=False,
            ),
            sa.Column(
                "legal_basis",
                sa.Enum(*_LEGAL_BASIS, name="legalbasis"),
                nullable=False,
            ),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(*_CONSENT_STATUS, name="consentstatus"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revocation_reason", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("version", sa.String(length=20), nullable=False),
            sa.Column("consent_hash", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_lgpd_consents_titular_id", "lgpd_consents", ["titular_id"])

    # ------------------------------------------------------------------
    # lgpd_pia_assessments
    # ------------------------------------------------------------------
    if not insp.has_table("lgpd_pia_assessments"):
        op.create_table(
            "lgpd_pia_assessments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("project_name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(*_ASSESSMENT_STATUS, name="assessmentstatus"),
                nullable=False,
            ),
            sa.Column(
                "risk_level",
                sa.Enum(*_RISK_LEVEL, name="risklevel"),
                nullable=True,
            ),
            sa.Column("requires_dpia", sa.Boolean(), nullable=True),
            sa.Column("data_categories", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("processing_purposes", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("data_subjects", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("risk_factors", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("risk_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("recommendations", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("mitigations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("reviewed_by", sa.String(length=255), nullable=True),
            sa.Column("approved_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("version", sa.String(length=20), nullable=False),
        )

    # ------------------------------------------------------------------
    # lgpd_erasure_requests
    # ------------------------------------------------------------------
    if not insp.has_table("lgpd_erasure_requests"):
        op.create_table(
            "lgpd_erasure_requests",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("titular_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("titular_email", sa.String(length=255), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column(
                "scope",
                sa.Enum(*_ERASURE_SCOPE, name="erasurescope"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.Enum(*_ERASURE_STATUS, name="erasurestatus"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("deadline_at", sa.DateTime(), nullable=True),
            sa.Column("processed_by", sa.String(length=255), nullable=True),
            sa.Column("processing_notes", sa.Text(), nullable=True),
            sa.Column("affected_systems", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("erasure_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("request_hash", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_lgpd_erasure_requests_titular_id", "lgpd_erasure_requests", ["titular_id"]
        )

    # ------------------------------------------------------------------
    # lgpd_audit_logs
    # ------------------------------------------------------------------
    if not insp.has_table("lgpd_audit_logs"):
        op.create_table(
            "lgpd_audit_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "action",
                sa.Enum(*_AUDIT_ACTION, name="auditaction"),
                nullable=False,
            ),
            sa.Column(
                "resource_type",
                sa.Enum(*_RESOURCE_TYPE, name="resourcetype"),
                nullable=False,
            ),
            sa.Column("resource_id", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column(
                "severity",
                sa.Enum(*_AUDIT_SEVERITY, name="auditseverity"),
                nullable=False,
            ),
            sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("event_hash", sa.String(length=64), nullable=False),
            sa.Column("previous_hash", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_lgpd_audit_logs_action", "lgpd_audit_logs", ["action"])
        op.create_index(
            "ix_lgpd_audit_logs_resource_type", "lgpd_audit_logs", ["resource_type"]
        )
        op.create_index("ix_lgpd_audit_logs_resource_id", "lgpd_audit_logs", ["resource_id"])
        op.create_index("ix_lgpd_audit_logs_user_id", "lgpd_audit_logs", ["user_id"])
        op.create_index("ix_lgpd_audit_logs_created_at", "lgpd_audit_logs", ["created_at"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lgpd_audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS lgpd_erasure_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS lgpd_pia_assessments CASCADE")
    op.execute("DROP TABLE IF EXISTS lgpd_consents CASCADE")
    # Enums (só existem se as tabelas foram criadas por esta migration)
    for enum_name in (
        "consentpurpose",
        "legalbasis",
        "consentstatus",
        "assessmentstatus",
        "risklevel",
        "erasurescope",
        "erasurestatus",
        "auditaction",
        "resourcetype",
        "auditseverity",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
