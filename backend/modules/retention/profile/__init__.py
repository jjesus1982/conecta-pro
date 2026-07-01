"""
Modulo de Perfil Operacional.

Sistema de avaliacao comportamental para funcionarios de seguranca,
permitindo identificar perfil predominante e calcular compatibilidade
com diferentes tipos de postos.

Estrutura:
    - models/: Models SQLAlchemy (OperationalProfile, ProfileQuestion, PostMatch)
    - schemas/: Schemas Pydantic para validacao
    - repositories/: Camada de acesso a dados
    - services/: Logica de negocio (ProfileService, ProfileMatcher)
    - controllers/: Endpoints REST

Uso:
    from modules.retention.profile import router
    app.include_router(router, prefix="/api/v1")

Dimensoes Avaliadas:
    - Vigilancia: Capacidade de observacao e atencao
    - Comunicacao: Habilidades interpessoais
    - Resiliencia: Controle emocional e adaptabilidade
    - Lideranca: Iniciativa e capacidade de gestao

Tipos de Posto Suportados:
    - CFTV: Monitoramento por cameras
    - Portaria: Controle de acesso
    - Recepcao: Atendimento ao publico
    - Ronda: Patrulhamento
    - Evento: Seguranca de eventos
    - Supervisor: Gestao de equipe
    - Controle de Acesso: Controle de acesso e triagem
    - Porteiro: portaria e controle de acesso
"""

from .controllers import router
from .models import (
    PERFIL_IDEAL_POR_TIPO,
    QUESTIONARIO_PERFIL,
    OperationalProfile,
    PostMatch,
    PostTypeProfile,
    ProfileDimension,
    ProfileQuestion,
)
from .repositories import ProfileRepository
from .schemas import (
    DashboardResponse,
    MatchNivelEnum,
    OperationalProfileDetail,
    OperationalProfileResponse,
    PostMatchDetail,
    PostMatchResponse,
    PostTypeEnum,
    ProfileDimensionEnum,
    QuestionnaireResponse,
    SubmitRespostasRequest,
)
from .services import ProfileMatcher, ProfileService

__all__ = [
    # Router
    "router",
    # Models
    "OperationalProfile",
    "ProfileQuestion",
    "PostMatch",
    "ProfileDimension",
    "PostTypeProfile",
    # Constants
    "QUESTIONARIO_PERFIL",
    "PERFIL_IDEAL_POR_TIPO",
    # Schemas principais
    "ProfileDimensionEnum",
    "PostTypeEnum",
    "MatchNivelEnum",
    "SubmitRespostasRequest",
    "OperationalProfileResponse",
    "OperationalProfileDetail",
    "PostMatchResponse",
    "PostMatchDetail",
    "QuestionnaireResponse",
    "DashboardResponse",
    # Services
    "ProfileService",
    "ProfileMatcher",
    # Repository
    "ProfileRepository",
]
