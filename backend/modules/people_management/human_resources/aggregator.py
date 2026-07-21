"""
Agregador principal do modulo de Recursos Humanos.

Combina todos os sub-routers em um unico router com prefixo
/human-resources, centralizando funcionalidades de:
- Recrutamento e Selecao
- Treinamento e Desenvolvimento
- Avaliacao de Desempenho
- Plano de Carreira
- Clima Organizacional
- Predicao de Turnover
- Onboarding Digital
"""

import logging

from fastapi import APIRouter

from modules.people_management.human_resources.controllers.career_controller import (
    router as career_router,
)
from modules.people_management.human_resources.controllers.performance_controller import (
    router as performance_router,
)
from modules.people_management.human_resources.controllers.training_controller import (
    router as training_router,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/human-resources", tags=["Recursos Humanos"])

router.include_router(training_router)
router.include_router(performance_router)
router.include_router(career_router)
logger.info("RH: Routers de treinamento, desempenho e carreira carregados.")

# Re-export: Recrutamento
try:
    from modules.people_management.human_resources.controllers.recruitment_controller import (
        router as recruitment_router,
    )

    router.include_router(recruitment_router)
    logger.info("RH: Router de recrutamento carregado.")
except ImportError:
    logger.warning("RH: Modulo de recrutamento nao disponivel.")

# Re-export: Esteira de candidatos (funil candidato→colaborador, fase 3)
try:
    from modules.people_management.human_resources.controllers.candidatos_esteira_controller import (
        router as candidatos_esteira_router,
    )

    router.include_router(candidatos_esteira_router)
    logger.info("RH: Router de esteira de candidatos carregado.")
except ImportError:
    logger.warning("RH: Modulo de esteira de candidatos nao disponivel.")

# Re-export: Gerador de link de Prestadores PJ (3º trilho)
try:
    from modules.people_management.human_resources.controllers.prestadores_pj_controller import (
        router as prestadores_pj_router,
    )

    router.include_router(prestadores_pj_router)
    logger.info("RH: Router de prestadores PJ (gerador de link) carregado.")
except ImportError:
    logger.warning("RH: Modulo de prestadores PJ nao disponivel.")

# Re-export: Clima Organizacional
try:
    from modules.people_management.human_resources.controllers.climate_controller import (
        router as climate_router,
    )

    router.include_router(climate_router)
    logger.info("RH: Router de clima organizacional carregado.")
except ImportError:
    logger.warning("RH: Modulo de clima nao disponivel.")

# Re-export: Predicao de Turnover
try:
    from modules.people_management.human_resources.controllers.turnover_controller import (
        router as turnover_router,
    )

    router.include_router(turnover_router)
    logger.info("RH: Router de turnover carregado.")
except ImportError:
    logger.warning("RH: Modulo de turnover nao disponivel.")

# Re-export: Onboarding
try:
    from modules.people_management.human_resources.controllers.onboarding_controller import (
        router as onboarding_router,
    )

    router.include_router(onboarding_router)
    logger.info("RH: Router de onboarding carregado.")
except ImportError:
    logger.warning("RH: Modulo de onboarding nao disponivel.")

# Resume Parser (Currículos)
try:
    from modules.people_management.human_resources.controllers.resume_controller import (
        router as resume_router,
    )

    router.include_router(resume_router)
    logger.info("RH: Router de currículos carregado.")
except ImportError:
    logger.warning("RH: Modulo de currículos nao disponivel.")

# Avaliação 360°
try:
    from modules.people_management.human_resources.controllers.evaluation_360_controller import (
        router as evaluation_360_router,
    )

    router.include_router(evaluation_360_router)
    logger.info("RH: Router de avaliação 360° carregado.")
except ImportError:
    logger.warning("RH: Modulo de avaliação 360° nao disponivel.")
