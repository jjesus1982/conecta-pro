"""
My Schedules Controller — Consulta de escalas do funcionario.

Endpoints:
- GET /portal/my-schedules
- GET /portal/my-schedules/current-month
- GET /portal/my-schedules/next-shift
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Escalas"])


