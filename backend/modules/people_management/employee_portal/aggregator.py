"""
Employee Portal Aggregator — Router principal do portal do funcionario.

Inclui todos os sub-routers sob o prefixo /portal.
"""

import logging

from fastapi import APIRouter

from .controllers import (
    my_benefits_router,
    my_cct_router,
    my_comunicados_router,
    my_data_router,
    my_documents_router,
    my_notifications_router,
    my_payslips_router,
    my_ponto_router,
    my_profile_router,
    my_schedules_router,
    my_trainings_router,
    my_vacations_router,
    portal_auth_router,
    self_service_router,
    homologacao_router,
    candidato_router,
    pj_autocadastro_router,
    primeiro_acesso_router,
    login_facial_router,
    portal_docs_router,
    ouvidoria_admin_router,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Portal do Funcionario"])

# Auth, me, dashboard
router.include_router(portal_auth_router)

# Perfil e contrato
router.include_router(my_profile_router)

# Escalas
router.include_router(my_schedules_router)

# Contracheques (historico + detalhado + PDF)
router.include_router(my_payslips_router)

# Ponto eletronico e banco de horas
router.include_router(my_ponto_router)

# Beneficios (com CCT)
router.include_router(my_benefits_router)

# CCT — Direitos do trabalhador
router.include_router(my_cct_router)

# Documentos e assinatura digital
router.include_router(my_documents_router)

# Dados pessoais
router.include_router(my_data_router)

# Ferias
router.include_router(my_vacations_router)

# Treinamentos
router.include_router(my_trainings_router)

# Notificacoes
router.include_router(my_notifications_router)

# Comunicados
router.include_router(my_comunicados_router)

# Self-service (login Google / JWT principal — role='funcionario')
router.include_router(self_service_router)
router.include_router(homologacao_router)

# Funil de candidato (autocadastro público de vaga — fase 1)
router.include_router(candidato_router)
router.include_router(pj_autocadastro_router)
router.include_router(primeiro_acesso_router)
router.include_router(login_facial_router)
router.include_router(portal_docs_router)
router.include_router(ouvidoria_admin_router)
