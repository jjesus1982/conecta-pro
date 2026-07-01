"""Retention: cria schema `retention` + tabelas de turnover/onboarding/profile.

As 3 telas (turnover/onboarding/profile) estavam 100% down porque as tabelas nunca
foram criadas. Migration DIRIGIDA PELOS MODELS (create_all scoped, checkfirst) — zero
transcricao, ordem de FK automatica, idempotente. NAO toca climate_* (ja existem).

Revision ID: retention_schema_20260701
Revises: ponto_closing_uuid_20260701
"""

from alembic import op

revision = "retention_schema_20260701"
down_revision = "ponto_closing_uuid_20260701"
branch_labels = None
depends_on = None

_ALVOS = {
    "turnover_predictions",
    "turnover_risk_factors",
    "turnover_risk_alerts",
    "operational_profiles",
    "profile_questions",
    "post_matches",
    "onboarding_checklists",
    "onboarding_steps",
    "onboarding_progress",
}


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE SCHEMA IF NOT EXISTS retention")

    # importa os models p/ registrar as tabelas na metadata
    import modules.retention.onboarding.models.onboarding_models  # noqa: F401
    import modules.retention.profile.models.profile_models  # noqa: F401
    import modules.retention.turnover.models.turnover_models  # noqa: F401
    from core.models import Base

    # NAO usar sorted_tables/create_all (o sort global quebra num FK pre-existente
    # de outro modulo: documentos_fiscais_diaristas -> diaristas inexistente).
    # Cria cada tabela individualmente, em ordem manual de dependencia (pai antes do filho).
    ordem = [
        "turnover_predictions",
        "turnover_risk_factors",
        "turnover_risk_alerts",
        "operational_profiles",
        "profile_questions",
        "post_matches",
        "onboarding_checklists",
        "onboarding_steps",
        "onboarding_progress",
    ]
    by_name = {t.name: t for t in Base.metadata.tables.values() if t.name in _ALVOS}
    for name in ordem:
        t = by_name.get(name)
        if t is not None:
            t.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS retention.onboarding_progress, retention.onboarding_steps, "
        "retention.onboarding_checklists CASCADE"
    )
    op.execute(
        "DROP TABLE IF EXISTS post_matches, profile_questions, operational_profiles, "
        "turnover_risk_alerts, turnover_risk_factors, turnover_predictions CASCADE"
    )
    op.execute("DROP SCHEMA IF EXISTS retention CASCADE")
