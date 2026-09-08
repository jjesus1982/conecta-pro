"""
My Comunicados Controller — Comunicados e avisos do DP.

Endpoints:
- GET /portal/comunicados (avisos do DP para o funcionario)
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Comunicados"])


