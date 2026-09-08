"""Controller para estatísticas gerais consolidadas do GED."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

# Sem prefix aqui - será adicionado no include_router
router = APIRouter(tags=["GED - Estatísticas"])


