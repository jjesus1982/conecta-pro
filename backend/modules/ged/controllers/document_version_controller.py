"""Controller para DocumentVersion."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-versions", tags=["GED - Versões"])


