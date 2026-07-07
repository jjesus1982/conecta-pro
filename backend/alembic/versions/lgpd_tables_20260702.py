"""LGPD tables: consents, pia_assessments, erasure_requests, audit_logs.

Idempotente — as 4 tabelas já existem em produção (criadas via models direto).
Esta migration garante o schema em deploys limpos. Guarda com inspector.has_table
antes de cada create_table (op.create_table não tem if_not_exists nativo) e cria
cada ENUM via DO $$ ... EXCEPTION WHEN duplicate_object (os types podem já existir
se os models rodaram create_all(checkfirst) antes do alembic — ex.: `risklevel` é
COMPARTILHADO com risk_profiles/fraud_detection e tem 6 valores em produção).

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
# NB: o type pg `risklevel` é compartilhado com risk_profiles (ai/fraud_detection);
# em produção tem 6 valores (\dT+ risklevel) — superset dos 4 usados pelo model LGPD.
_RISK_LEVEL = ("minimal", "low", "medium", "high", "critical", "blocked")
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

_ENUMS = {
    "consentpurpose": _CONSENT_PURPOSE,
    "legalbasis": _LEGAL_BASIS,
    "consentstatus": _CONSENT_STATUS,
    "assessmentstatus": _ASSESSMENT_STATUS,
    "risklevel": _RISK_LEVEL,
    "erasurescope": _ERASURE_SCOPE,
    "erasurestatus": _ERASURE_STATUS,
    "auditaction": _AUDIT_ACTION,
    "resourcetype": _RESOURCE_TYPE,
    "auditseverity": _AUDIT_SEVERITY,
}


def _enum(name: str) -> postgresql.ENUM:
    """Referencia o type pg SEM emitir CREATE TYPE (já garantido em _ensure_enums)."""
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


def _ensure_enums() -> None:
    """CREATE TYPE idempotente — o type pode já existir (models create_all/checkfirst)."""
    for name, values in _ENUMS.items():
        vals = ", ".join("'" + v + "'" for v in values)
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    _ensure_enums()

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
                _enum("consentpurpose"),
                nullable=False,
            ),
            sa.Column(
                "legal_basis",
                _enum("legalbasis"),
                nullable=False,
            ),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "status",
                _enum("consentstatus"),
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
                _enum("assessmentstatus"),
                nullable=False,
            ),
            sa.Column(
                "risk_level",
                _enum("risklevel"),
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
                _enum("erasurescope"),
                nullable=False,
            ),
            sa.Column(
                "status",
                _enum("erasurestatus"),
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
                _enum("auditaction"),
                nullable=False,
            ),
            sa.Column(
                "resource_type",
                _enum("resourcetype"),
                nullable=False,
            ),
            sa.Column("resource_id", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column(
                "severity",
                _enum("auditseverity"),
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
    # Enums: dropar só se ninguém mais usa — `risklevel` é compartilhado com
    # risk_profiles (fraud_detection); DROP sem guarda falharia em produção.
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
        op.execute(
            f"DO $$ BEGIN DROP TYPE IF EXISTS {enum_name}; "
            "EXCEPTION WHEN dependent_objects_still_exist THEN NULL; END $$;"
        )
