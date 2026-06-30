"""
Controller de Tickets do Portal do Cliente.

Endpoints protegidos por autenticacao do portal para criacao,
listagem, detalhamento, mensagens e fechamento de tickets.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.schemas.ticket import (
    TicketCreate,
    TicketListResponse,
    TicketResponse,
    TicketUpdate,
)
from modules.client_portal.services.ticket_service import PortalTicketService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["Portal - Tickets"])


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(
    data: TicketCreate,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo ticket de suporte.

    O cliente pode vincular o ticket a um kit documental especifico
    ou abrir um chamado geral. A primeira mensagem e criada
    automaticamente a partir da descricao do ticket.
    """
    service = PortalTicketService(db)
    try:
        result = await service.create_ticket(client_id=client_id, data=data)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um ticket especifico com mensagens."""
    service = PortalTicketService(db)
    try:
        return await service.get_ticket(client_id=client_id, ticket_id=ticket_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{ticket_id}/messages", response_model=TicketResponse, status_code=201)
async def add_message(
    ticket_id: str,
    data: TicketUpdate,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Adiciona uma mensagem a um ticket existente.

    Nao e possivel adicionar mensagens a tickets fechados.
    Se o ticket estava respondido ou em andamento, o status
    volta para aberto apos a nova mensagem do cliente.
    """
    service = PortalTicketService(db)
    try:
        result = await service.add_message(
            client_id=client_id,
            ticket_id=ticket_id,
            data=data,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{ticket_id}/close", response_model=TicketResponse)
async def close_ticket(
    ticket_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Fecha um ticket de suporte.

    O cliente pode fechar seus proprios tickets a qualquer momento,
    exceto se ja estiver fechado.
    """
    service = PortalTicketService(db)
    try:
        result = await service.close_ticket(client_id=client_id, ticket_id=ticket_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
