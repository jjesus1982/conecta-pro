"""
Controller de Documentos da Empresa - Licitacoes
================================================
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Licitacoes - Documentos"])


