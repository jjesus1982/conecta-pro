"""
Módulo INTELIGÊNCIA — Agregador (esvaziado em 06/09/2026)

`analytics`, `reports` e `monitoring` foram APAGADOS: 81 rotas, 0 requisições em 15 dias,
tabelas com 0 linhas, último commit em julho. `main_production.py` (zona proibida) ainda
importa estes quatro nomes — ficam como routers VAZIOS até alguém com autorização remover
o bloco de lá. Ver auditoria/MAPA_CONECTA_PRO_20260906.md.
"""
from fastapi import APIRouter

analytics_router = APIRouter()
executive_dashboard_router = APIRouter()
report_router = APIRouter()
monitoring_router = APIRouter()

__all__ = ["executive_dashboard_router", "analytics_router", "report_router", "monitoring_router"]
