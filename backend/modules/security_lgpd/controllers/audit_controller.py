"""
Controller de Auditoria LGPD.
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["LGPD - Auditoria"])


