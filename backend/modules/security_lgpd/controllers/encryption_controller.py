"""
Controller de Criptografia LGPD.
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/encryption", tags=["LGPD - Criptografia"])


