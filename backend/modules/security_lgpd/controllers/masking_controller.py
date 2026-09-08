"""
Controller de Mascaramento LGPD.
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/masking", tags=["LGPD - Mascaramento"])


