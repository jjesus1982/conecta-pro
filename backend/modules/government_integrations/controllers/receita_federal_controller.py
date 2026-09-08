"""
Controller para integrações com Receita Federal.
"""

import logging

from fastapi import APIRouter



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receita", tags=["Receita Federal"])


