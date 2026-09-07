"""Serviços do analytics — só o que está VIVO.

07/09/2026: o pacote `modules/analytics` foi apagado na limpeza (33 rotas com 0 requisições,
modelos de ML sem dado) e os workers `priority` e `sefaz` entraram em crash-loop com
`ModuleNotFoundError: No module named 'modules.analytics'` no recreate do bake: o
`celery_app` inclui `modules.analytics.tasks`, e a task `analytics.recalcular_kpis` (06:15)
é quem escreve `executive_kpis` — lida pelo redesign, pelo CFO e pelo consultor CEO todo
dia. O boot de prova só cobriu `main_production`, não `celery_app`. Restaurado o mínimo:
esta task e `kpi_recalc_service`. O dashboard executivo e os modelos de ML continuam fora.
"""
from .kpi_recalc_service import recalcular_kpis  # noqa: F401

__all__ = ["recalcular_kpis"]
