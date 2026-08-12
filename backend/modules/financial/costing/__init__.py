"""Módulo de Custeio ABC - Activity-Based Costing.

Este módulo implementa:
- Cost Drivers: Direcionadores de custo
- Cost Activities: Atividades que consomem recursos
- Cost Pools: Pools de custos indiretos
- Cost Objects: Objetos de custo (produtos, serviços, clientes)
- Cost Allocations: Alocações/rateios de custos
- Cost Analysis: Análises com IA

Metodologia ABC de duas etapas:
1. Pool → Activity (via drivers de recurso)
2. Activity → Object (via drivers de atividade)
"""

from modules.financial.costing.controllers import router
from modules.financial.costing.models import (
    CostActivity,
    CostAllocation,
    CostAnalysis,
    CostDriver,
    CostObject,
    CostPool,
)
from modules.financial.costing.repositories import (
    CostActivityRepository,
    CostAllocationRepository,
    CostAnalysisRepository,
    CostDriverRepository,
    CostObjectRepository,
    CostPoolRepository,
)
from modules.financial.costing.services import (
    ABCService,
    AllocationService,
    CostAIService,
)

__all__ = [
    # Router
    "router",
    # Models
    "CostDriver",
    "CostActivity",
    "CostPool",
    "CostObject",
    "CostAllocation",
    "CostAnalysis",
    # Repositories
    "CostDriverRepository",
    "CostActivityRepository",
    "CostPoolRepository",
    "CostObjectRepository",
    "CostAllocationRepository",
    "CostAnalysisRepository",
    # Services
    "ABCService",
    "AllocationService",
    "CostAIService",
]
