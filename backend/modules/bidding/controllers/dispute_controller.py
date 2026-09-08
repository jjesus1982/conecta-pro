"""
Controller de Disputas — Licitacoes
====================================
Endpoints para gerenciamento de disputas de pregao eletronico,
simulacoes de lances e monitoramento de sessoes.
Utiliza o agente Warrior para estrategias e simulacoes.
"""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.bidding.agents.warrior_agent import WarriorAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disputes", tags=["Licitacoes - Disputas"])

# Instanciar agente Warrior
warrior_agent = WarriorAgent()


# ---- Schemas ----


class DisputeSimulationRequest(BaseModel):
    """Parametros para simulacao de disputa."""

    valor_referencia: float = Field(..., gt=0, description="Valor de referencia da licitacao")
    estrategia: str = Field(default="moderado", description="Estrategia: conservador, moderado, agressivo")
    piso_minimo: float | None = Field(None, description="Piso minimo para lances (0 = sem piso)")
    num_rodadas: int = Field(default=10, ge=1, le=50, description="Numero de rodadas da simulacao")
    concorrentes: int = Field(default=3, ge=1, le=10, description="Numero de concorrentes simulados")


class LanceRequest(BaseModel):
    """Dados para lance manual em disputa."""

    valor: float = Field(..., gt=0, description="Valor do lance")
    justificativa: str | None = Field(None, description="Justificativa do lance")


class DisputeStatusUpdate(BaseModel):
    """Atualizacao de status de disputa."""

    status: str = Field(..., description="Novo status (aguardando, em_disputa, encerrada, suspensa)")
    motivo: str | None = Field(None, description="Motivo da alteracao")


# ---- Cache/store temporario ----
_disputes_cache: dict[str, dict[str, Any]] = {}

VALID_STATUSES = {"aguardando", "em_disputa", "encerrada", "suspensa", "cancelada"}
VALID_ESTRATEGIAS = {"conservador", "moderado", "agressivo"}


# ---- Endpoints ----


