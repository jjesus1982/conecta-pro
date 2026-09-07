"""
AI Contract Analysis Module - Sprint 44

Analise inteligente de contratos usando NLP.
Funcionalidades:
- Extracao automatica de clausulas
- Identificacao de partes
- Deteccao de datas importantes
- Analise de risco
- Alertas de vencimento
- Score de conformidade
"""

from modules.ai.contract_analysis.controllers.contract_controller import router

__all__ = ["router"]
