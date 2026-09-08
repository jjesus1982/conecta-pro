"""Controller para Application."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["Recruitment - Candidaturas"])


