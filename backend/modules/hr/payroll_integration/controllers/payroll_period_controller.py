"""Controller para períodos de folha de pagamento."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/periods", tags=["Payroll Periods"])


