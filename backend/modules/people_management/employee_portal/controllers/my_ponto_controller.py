"""
My Ponto Controller — Ponto eletronico e banco de horas do funcionario.

Endpoints:
- GET /portal/ponto/historico (registros de ponto do mes)
- GET /portal/banco-horas (saldo atual do banco de horas)
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Ponto e Banco de Horas"])


