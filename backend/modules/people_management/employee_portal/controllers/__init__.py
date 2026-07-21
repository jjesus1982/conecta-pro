"""
Employee Portal Controllers — Routers do portal do funcionario.
"""

from .my_benefits_controller import router as my_benefits_router
from .my_cct_controller import router as my_cct_router
from .my_comunicados_controller import router as my_comunicados_router
from .my_data_controller import router as my_data_router
from .my_documents_controller import router as my_documents_router
from .my_notifications_controller import router as my_notifications_router
from .my_payslips_controller import router as my_payslips_router
from .my_ponto_controller import router as my_ponto_router
from .my_profile_controller import router as my_profile_router
from .my_schedules_controller import router as my_schedules_router
from .my_trainings_controller import router as my_trainings_router
from .my_vacations_controller import router as my_vacations_router
from .portal_controller import router as portal_auth_router
from .self_service_controller import router as self_service_router
from .homologacao_controller import router as homologacao_router
from .candidato_controller import router as candidato_router
from .pj_autocadastro_controller import router as pj_autocadastro_router
from .primeiro_acesso_controller import router as primeiro_acesso_router
from .primeiro_acesso_controller import router_auth as login_facial_router
from .portal_docs_ouvidoria_controller import router as portal_docs_router
from .portal_docs_ouvidoria_controller import router_admin as ouvidoria_admin_router

__all__ = [
    "portal_auth_router",
    "self_service_router",
    "homologacao_router",
    "candidato_router",
    "pj_autocadastro_router",
    "primeiro_acesso_router",
    "login_facial_router",
    "portal_docs_router",
    "ouvidoria_admin_router",
    "my_profile_router",
    "my_schedules_router",
    "my_payslips_router",
    "my_ponto_router",
    "my_benefits_router",
    "my_cct_router",
    "my_documents_router",
    "my_data_router",
    "my_vacations_router",
    "my_trainings_router",
    "my_notifications_router",
    "my_comunicados_router",
]
