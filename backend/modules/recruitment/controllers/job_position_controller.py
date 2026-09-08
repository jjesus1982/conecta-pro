"""Controller para JobPosition."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-positions", tags=["Recruitment - Vagas"])


