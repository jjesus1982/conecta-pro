"""
Controller de Editais - Licitacoes
==================================
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenders", tags=["Licitacoes - Editais"])


