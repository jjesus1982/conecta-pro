"""
Controller de Certidoes - Licitacoes
====================================
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["Licitacoes - Certidoes"])


