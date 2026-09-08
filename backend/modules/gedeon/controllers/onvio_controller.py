"""
GEDEON Fase 3 — Onvio Sync Controller

Endpoints:
- GET  /onvio/stats        → totais e por_categoria
- GET  /onvio/status       → sessao_valida (conectividade Onvio)
- POST /onvio/sync         → disparar sincronização manual
- GET  /onvio/historico    → últimos N registros de sync
- GET  /onvio/documentos   → lista documentos (filtro por categoria)
"""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onvio", tags=["GEDEON - Onvio Sync"])


# ─── GET /onvio/stats ──────────────────────────────────────────────────────────


