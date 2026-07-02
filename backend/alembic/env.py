"""
Alembic environment configuration.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.models import Base

# Campo models
from modules.campo.models import (  # noqa: F401
    AccessLog,
    CampoTecnico,
    EquipmentStatus,
)
from modules.campo.models.checklist import (  # noqa: F401
    ChecklistItem,
    ChecklistPreenchido,
    ChecklistResposta,
    ChecklistTemplate,
)

# Campo - OS, Visitas, Checklists
from modules.campo.models.ordem_servico import OrdemServico  # noqa: F401
from modules.campo.models.visita import Visita  # noqa: F401

# Import all models for autogenerate
from modules.crm.models import (  # noqa: F401
    Lead,
    MarketingContentDraft,
    Opportunity,
    Proposal,
    ProposalApproval,
    ProposalItem,
    ProposalTemplate,
)

# GED - Onvio Sync models (GEDEON Fase 3 — fonte canônica em modules.gedeon.models)
from modules.gedeon.models.onvio_models import (  # noqa: F401
    FgtsGuia,
    InssGuia,
    OnvioDocument,
    OnvioSyncLog,
)

# Diaristas models
from modules.operacional.diaristas.models import (  # noqa: F401
    Diarist,
    DiaristAssignment,
    DiaristEvaluation,
    DiaristPayment,
    DiaristSchedule,
)

# Diaristas fiscal models
from modules.operacional.diaristas.models.documento_fiscal import (  # noqa: F401
    DocumentoFiscal,
    EventoESocial,
    RetencaoFiscal,
    TabelaINSS,
    TabelaIRRF,
)
from modules.operacional.models import (  # noqa: F401
    Allocation,
    Post,
    Scale,
    Shift,
    Substitution,
    TimeBank,
)

# People Management - CCT DB models
from modules.people_management.cct.models.cct_models import (  # noqa: F401
    CCTBeneficio,
    CCTCargo,
    CCTConvencao,
    CCTFeriado,
)

# People Management - Portal models
from modules.people_management.employee_portal.models import (  # noqa: F401
    PortalAccess,
    PortalDigitalSignature,
    PortalNotification,
    PortalPreference,
)

# People Management - DP models
from modules.people_management.hr.models import (  # noqa: F401
    AdmissionProcess,
    EmployeeBenefit,
    EmploymentContract,
    TerminationProcess,
)

# People Management - RH models
from modules.people_management.human_resources.models import (  # noqa: F401
    CareerPlan,
    PerformanceReview,
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingEnrollment,
)

# Security LGPD models
from modules.security_lgpd.models.audit_log import AuditLog  # noqa: F401
from modules.security_lgpd.models.consent import Consent  # noqa: F401
from modules.security_lgpd.models.erasure_request import ErasureRequest  # noqa: F401
from modules.security_lgpd.models.pia_assessment import PIAAssessment  # noqa: F401

# Alembic Config object
config = context.config

# Override sqlalchemy.url with our settings
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("+asyncpg", ""),  # Use sync driver for migrations
)

# Interpret config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add model's MetaData for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
