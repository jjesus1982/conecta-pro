"""
My Benefits Controller — Beneficios do funcionario conforme CCT 2026.

Endpoints:
- GET /portal/my-benefits (lista beneficios ativos com valores CCT)
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Beneficios"])


