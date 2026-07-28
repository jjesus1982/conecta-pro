"""fase5.6a — cria fraud_risk_profiles (tabela faltante do modulo dormente)

O modulo `backend/modules/ai/fraud_detection/` tem 4 models: FraudAlert,
FraudPattern, FraudRule, RiskProfile. As 3 primeiras ja tem tabela no banco
(fraud_alerts/fraud_patterns/fraud_rules, sprint45_create_fraud_detection_tables).
RiskProfile (models/risk_profile.py, __tablename__ = "fraud_risk_profiles")
NAO tem — o sprint45 criou uma tabela `risk_profiles` (sem prefixo `fraud_`)
com um shape DIFERENTE (entity_type enum "usuario/morador/visitante/..." do
dominio condominio) que segue viva e em uso; nao mexer nela.

Esta migration cria a tabela NOVA `fraud_risk_profiles` com o shape EXATO
que o model RiskProfile atual espera (entity_type enum
"user/customer/supplier/employee/device/..." — dominio ERP generico).

GOTCHA verificado empiricamente na bancada throwaway: `Column(Enum(EntityType))`
e `Column(Enum(RiskLevel))` no model NAO passam `values_callable` — o
SQLAlchemy 2.0 entao usa por padrao o `.name` (MAIUSCULO) de cada membro como
valor persistido, NUNCA o `.value` (minusculo), mesmo os enums sendo StrEnum
e mesmo passando a string minuscula diretamente (o truque de igualdade/hash
de StrEnum resolve "customer" -> chave EntityType.CUSTOMER -> valor "CUSTOMER").
Confirmado com `sa.Enum(EntityType)._db_value_for_elem("customer") == "CUSTOMER"`.
Por isso os DOIS enums PG desta tabela usam rotulos EM MAIUSCULO (nomes dos
membros), não os valores minusculos do StrEnum — e por isso NAO reaproveitamos
o `risklevel` ja existente (compartilhado com a tabela `risk_profiles` antiga,
que usa rotulos minusculos): criamos `fraud_risk_level`, novo e distinto.
Isso e' um bug pre-existente do modulo dormente (afeta tambem FraudRule/
FraudPattern, que tem o mesmo padrao sem values_callable) — fora do escopo
desta migration consertar o model; aqui so garantimos que a tabela funciona
com o model TAL COMO ELE E' HOJE.

100% aditivo: guard checkfirst, nunca toca em tabela/enum existente.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fase56a_fraud_risk_profiles"
down_revision: str | None = "fase55_mem_curadoria"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "fraud_risk_profiles"
ENTITY_TYPE_ENUM_NAME = "fraud_risk_entity_type"
RISK_LEVEL_ENUM_NAME = "fraud_risk_level"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Enum de entity_type — rotulos EM MAIUSCULO (nomes dos membros de
    # EntityType), pois e' isso que Column(Enum(EntityType)) sem
    # values_callable de fato persiste. Nome distinto de `entitytype`
    # (ja existe em producao, dominio condominio, outros valores).
    entity_type_enum = postgresql.ENUM(
        "USER",
        "CUSTOMER",
        "SUPPLIER",
        "EMPLOYEE",
        "DEVICE",
        "IP_ADDRESS",
        "ACCOUNT",
        "CARD",
        "TRANSACTION",
        "SESSION",
        "EMAIL",
        "PHONE",
        "DOCUMENT",
        "OTHER",
        name=ENTITY_TYPE_ENUM_NAME,
        create_type=False,
    )
    entity_type_enum.create(bind, checkfirst=True)

    # Enum de risk_level — rotulos EM MAIUSCULO (nomes dos membros de
    # RiskLevel), mesmo motivo acima. NAO reaproveita o `risklevel`
    # existente (rotulos minusculos, compartilhado com a tabela antiga
    # `risk_profiles`) — tipo novo e distinto.
    risk_level_enum = postgresql.ENUM(
        "MINIMAL",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
        "BLOCKED",
        name=RISK_LEVEL_ENUM_NAME,
        create_type=False,
    )
    risk_level_enum.create(bind, checkfirst=True)

    if TABLE_NAME in inspector.get_table_names():
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Entidade
        sa.Column("entity_type", entity_type_enum, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_identifier", sa.String(200)),
        sa.Column("entity_name", sa.String(300)),
        # Nivel de risco
        sa.Column("risk_level", risk_level_enum, nullable=False, default="LOW"),
        sa.Column("risk_score", sa.Float, nullable=False, default=0),
        sa.Column("previous_risk_score", sa.Float),
        sa.Column("risk_score_change", sa.Float, default=0),
        # Scores detalhados
        sa.Column("behavior_score", sa.Float, default=0),
        sa.Column("transaction_score", sa.Float, default=0),
        sa.Column("velocity_score", sa.Float, default=0),
        sa.Column("identity_score", sa.Float, default=0),
        sa.Column("network_score", sa.Float, default=0),
        sa.Column("historical_score", sa.Float, default=0),
        # Fatores de risco / indicadores de confianca
        sa.Column("risk_factors", postgresql.JSONB, default=[]),
        sa.Column("trust_indicators", postgresql.JSONB, default=[]),
        # Historico de alertas
        sa.Column("total_alerts", sa.Integer, default=0),
        sa.Column("confirmed_frauds", sa.Integer, default=0),
        sa.Column("false_positives", sa.Integer, default=0),
        sa.Column("last_alert_at", sa.DateTime),
        sa.Column("last_fraud_at", sa.DateTime),
        # Historico de transacoes
        sa.Column("total_transactions", sa.Integer, default=0),
        sa.Column("total_transaction_value", sa.Float, default=0),
        sa.Column("avg_transaction_value", sa.Float, default=0),
        sa.Column("max_transaction_value", sa.Float, default=0),
        sa.Column("suspicious_transactions", sa.Integer, default=0),
        # Comportamento de acesso
        sa.Column("total_logins", sa.Integer, default=0),
        sa.Column("failed_logins", sa.Integer, default=0),
        sa.Column("unique_ips", sa.Integer, default=0),
        sa.Column("unique_devices", sa.Integer, default=0),
        sa.Column("unique_locations", sa.Integer, default=0),
        sa.Column("last_login_at", sa.DateTime),
        sa.Column("last_ip", sa.String(45)),
        sa.Column("last_device", sa.String(200)),
        sa.Column("last_location", sa.String(200)),
        # Padroes conhecidos
        sa.Column("known_ips", postgresql.ARRAY(sa.String), default=[]),
        sa.Column("known_devices", postgresql.ARRAY(sa.String), default=[]),
        sa.Column("known_locations", postgresql.ARRAY(sa.String), default=[]),
        sa.Column("typical_hours", postgresql.JSONB, default={}),
        sa.Column("typical_days", postgresql.ARRAY(sa.Integer), default=[]),
        # Restricoes
        sa.Column("is_blocked", sa.Boolean, default=False),
        sa.Column("blocked_at", sa.DateTime),
        sa.Column("blocked_by", postgresql.UUID(as_uuid=True)),
        sa.Column("blocked_reason", sa.Text),
        sa.Column("unblock_at", sa.DateTime),
        sa.Column("is_whitelisted", sa.Boolean, default=False),
        sa.Column("whitelisted_at", sa.DateTime),
        sa.Column("whitelisted_by", postgresql.UUID(as_uuid=True)),
        sa.Column("whitelist_reason", sa.Text),
        sa.Column("is_watchlisted", sa.Boolean, default=False),
        sa.Column("watchlist_reason", sa.Text),
        sa.Column("watchlist_expires", sa.DateTime),
        # Limites
        sa.Column("transaction_limit_daily", sa.Float),
        sa.Column("transaction_limit_monthly", sa.Float),
        sa.Column("transaction_count_limit_daily", sa.Integer),
        sa.Column("requires_approval_above", sa.Float),
        # Verificacao
        sa.Column("identity_verified", sa.Boolean, default=False),
        sa.Column("identity_verified_at", sa.DateTime),
        sa.Column("document_verified", sa.Boolean, default=False),
        sa.Column("phone_verified", sa.Boolean, default=False),
        sa.Column("email_verified", sa.Boolean, default=False),
        sa.Column("address_verified", sa.Boolean, default=False),
        # ML
        sa.Column("ml_risk_score", sa.Float),
        sa.Column("ml_confidence", sa.Float),
        sa.Column("ml_model_version", sa.String(50)),
        sa.Column("ml_last_scored", sa.DateTime),
        sa.Column("ml_features", postgresql.JSONB, default={}),
        # Relacionamentos externos
        sa.Column("linked_profiles", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), default=[]),
        sa.Column("shared_attributes", postgresql.JSONB, default={}),
        # Periodo de analise
        sa.Column("analysis_start_date", sa.Date),
        sa.Column("analysis_end_date", sa.Date),
        sa.Column("days_analyzed", sa.Integer, default=0),
        # Metadados
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
        sa.Column("last_calculated_at", sa.DateTime),
        # Flags
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("needs_review", sa.Boolean, default=False),
        sa.Column("auto_updated", sa.Boolean, default=True),
        # Notas
        sa.Column("notes", sa.Text),
        sa.Column("review_notes", sa.Text),
        sa.Column("tags", postgresql.ARRAY(sa.String), default=[]),
    )

    op.create_index(
        "ix_fraud_risk_profiles_entity_type",
        TABLE_NAME,
        ["entity_type"],
    )
    op.create_index(
        "ix_fraud_risk_profiles_entity_id",
        TABLE_NAME,
        ["entity_id"],
    )
    op.create_index(
        "ix_fraud_risk_profiles_entity_identifier",
        TABLE_NAME,
        ["entity_identifier"],
    )
    op.create_index(
        "ix_fraud_risk_profiles_risk_level",
        TABLE_NAME,
        ["risk_level"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE_NAME in inspector.get_table_names():
        op.drop_table(TABLE_NAME)

    # NAO derruba `risklevel` — compartilhado com a tabela `risk_profiles`
    # (sprint45, dominio condominio) que segue viva.
    op.execute(f"DROP TYPE IF EXISTS {ENTITY_TYPE_ENUM_NAME}")
