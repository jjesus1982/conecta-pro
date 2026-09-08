"""
Controller de Contratos Publicos - Licitacoes
=============================================
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contracts", tags=["Licitacoes - Contratos"])


