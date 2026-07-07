"""
Services do modulo de Recursos Humanos.

Exporta todos os services de treinamento, desempenho, carreira
e re-exporta services de recrutamento, clima, turnover e onboarding.
"""

from modules.people_management.human_resources.services.career_service import CareerService
from modules.people_management.human_resources.services.evaluation_360_service import (
    Evaluation360Service,
)
from modules.people_management.human_resources.services.integrated_performance_service import (
    IntegratedPerformanceService,
)
from modules.people_management.human_resources.services.performance_service import (
    PerformanceService,
)
from modules.people_management.human_resources.services.resume_parser_service import (
    ResumeParserService,
)
from modules.people_management.human_resources.services.training_service import TrainingService

# Re-exports com try/except
try:
    from modules.people_management.human_resources.services.recruitment_service import (
        CandidateService,
    )
except ImportError:
    CandidateService = None  # type: ignore[assignment, misc]

try:
    from modules.people_management.human_resources.services.climate_service import (
        ClimateService,
    )
except ImportError:
    ClimateService = None  # type: ignore[assignment, misc]

try:
    from modules.people_management.human_resources.services.turnover_service import (
        TurnoverService,
    )
except ImportError:
    TurnoverService = None  # type: ignore[assignment, misc]

try:
    from modules.people_management.human_resources.services.onboarding_service import (
        OnboardingService,
    )
except ImportError:
    OnboardingService = None  # type: ignore[assignment, misc]

__all__ = [
    "TrainingService",
    "PerformanceService",
    "CareerService",
    "CandidateService",
    "ClimateService",
    "TurnoverService",
    "OnboardingService",
    "Evaluation360Service",
    "IntegratedPerformanceService",
    "ResumeParserService",
]
