"""Controller para Interview."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews", tags=["Recruitment - Entrevistas"])


