"""
My Profile Controller — Perfil e contrato do funcionario.

Endpoints:
- GET /portal/perfil (dados pessoais, cargo, admissao, escala)
- GET /portal/contrato (tipo vinculo, carga horaria, local)
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Perfil"])


