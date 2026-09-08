"""Dashboard Fiscal-Financeiro — Conecta PRO"""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from core.auth.dependencies import CurrentActiveUser

router = APIRouter(prefix="/fiscal-dashboard", tags=["Dashboard Fiscal"])


@router.get("/atual", summary="Dashboard do mês atual")
async def get_dashboard_atual(_: CurrentActiveUser):
    from modules.financial.services.fiscal_dashboard_service import get_dashboard_fiscal

    now = datetime.now()
    try:
        return get_dashboard_fiscal(now.month, now.year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
