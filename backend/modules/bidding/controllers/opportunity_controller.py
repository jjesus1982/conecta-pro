"""
Controller de Oportunidades — Licitacoes
=========================================
Endpoints para gerenciamento de oportunidades de licitacao
detectadas pelo agente Scout e consolidadas de multiplos portais.
"""

import logging

from fastapi import APIRouter

from modules.bidding.agents.scout_agent import ScoutAgent
from modules.bidding.services.opportunity_service import OpportunityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["Licitacoes - Oportunidades"])

# Instanciar service e agente
opportunity_service = OpportunityService()
scout_agent = ScoutAgent()


