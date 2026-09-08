"""
Controller para integrações com SEFAZ (NFe/NFCe).
"""

import logging

from fastapi import APIRouter



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sefaz", tags=["SEFAZ"])


