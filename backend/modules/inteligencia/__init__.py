"""
Módulo INTELIGÊNCIA — Agregador (esvaziado em 06/09/2026)

`analytics`, `reports` e `monitoring` foram APAGADOS: 81 rotas, 0 requisições em 15 dias,
tabelas com 0 linhas, último commit em julho. `main_production.py` (zona proibida) ainda
importa estes quatro nomes — ficam como routers VAZIOS até alguém com autorização remover
o bloco de lá. Ver auditoria/MAPA_CONECTA_PRO_20260906.md.
"""
from fastapi import APIRouter

analytics_router = APIRouter()
# Busca global (`GET /api/v1/search?q=`): a caixa de busca do topo (GlobalSearch.tsx, montada em
# todas as telas pelo ProductivityProvider) chama esta rota desde sempre e `modules.search`
# NUNCA foi montado por main_production — 0 requisições na vida, 404 para quem tentou. Este
# agregador é incluído sem prefixo pelo entry point, então a rota nasce aqui (07/09/2026).
try:
    from modules.search.controller import router as _search_router
    analytics_router.include_router(_search_router)
except Exception as _exc:  # noqa: BLE001 — sem busca é melhor do que sem servidor
    import logging
    logging.getLogger(__name__).error("busca global não montou: %s", _exc)
executive_dashboard_router = APIRouter()
report_router = APIRouter()
monitoring_router = APIRouter()

__all__ = ["executive_dashboard_router", "analytics_router", "report_router", "monitoring_router"]
