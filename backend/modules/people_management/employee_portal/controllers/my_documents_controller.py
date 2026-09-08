"""
My Documents Controller — Documentos e assinatura digital.

Endpoints:
- GET /portal/my-documents
- POST /portal/my-documents/{id}/sign
- GET /portal/my-documents/{id}/verify-signature
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Documentos"])


