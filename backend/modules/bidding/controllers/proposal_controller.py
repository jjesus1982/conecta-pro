"""
Controller de Propostas - Licitacoes
====================================
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proposals", tags=["Licitacoes - Propostas"])


