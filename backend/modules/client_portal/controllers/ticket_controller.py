"""
Controller de Tickets do Portal do Cliente.

Endpoints protegidos por autenticacao do portal para criacao,
listagem, detalhamento, mensagens e fechamento de tickets.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.schemas.ticket import (
    TicketListResponse,
)
from modules.client_portal.services.ticket_service import PortalTicketService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["Portal - Tickets"])


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Offset para paginacao"),
    limit: int = Query(20, ge=1, le=100, description="Registros por pagina"),
    status: str | None = Query(None, description="Filtrar por status do ticket"),
) -> Any:
    """Lista tickets de suporte do cliente autenticado.

    Retorna tickets com paginacao e filtro opcional por status.
    Cada ticket inclui a lista de mensagens.
    """
    service = PortalTicketService(db)
    return await service.list_tickets(
        client_id=client_id,
        skip=skip,
        limit=limit,
        status_filter=status,
    )


