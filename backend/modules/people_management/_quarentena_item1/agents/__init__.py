"""
Agents de Gestao de Pessoas.
Cada Agent e responsavel por um modulo e seus Skills.
"""

from .base_agent import AgentHealth, AgentState, BaseAgent
from .dp_agent import DPAgent
from .ged_agent import GEDAgent
from .ops_agent import OPSAgent
from .orchestrator import GPOrchestratorAgent
from .ponto_agent import PontoAgent
from .portal_agent import PortalAgent
from .rh_agent import RHAgent
from .sst_agent import SSTAgent

__all__ = [
    "BaseAgent",
    "AgentState",
    "AgentHealth",
    "GPOrchestratorAgent",
    "DPAgent",
    "PontoAgent",
    "GEDAgent",
    "OPSAgent",
    "RHAgent",
    "SSTAgent",
    "PortalAgent",
]
