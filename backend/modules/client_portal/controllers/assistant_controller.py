"""
Controller do Assistente IA para o Portal do Cliente.

Endpoints protegidos por autenticacao do portal que permitem ao cliente
conversar com o assistente IA restrito ao seu contexto.
"""

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.services.portal_assistant_service import PortalAssistantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistente", tags=["Portal - Assistente IA"])


# =============================================================================
# Schemas
# =============================================================================


class SendMessageRequest(BaseModel):
    """Requisicao para enviar mensagem ao assistente."""

    message: str = Field(..., min_length=1, max_length=1000, description="Mensagem do cliente")
    session_id: str = Field(..., min_length=1, max_length=100, description="ID da sessao de chat")


class SendMessageResponse(BaseModel):
    """Resposta do assistente."""

    response: str
    suggestions: list[str]
    session_id: str
    message_id: str


class GreetingResponse(BaseModel):
    """Saudacao inicial do assistente."""

    greeting: str
    suggestions: list[str]


class FeedbackRequest(BaseModel):
    """Feedback sobre uma resposta do assistente."""

    message_id: str = Field(..., description="ID da mensagem avaliada")
    rating: Literal["positive", "negative"] = Field(..., description="Avaliacao da resposta")


class FeedbackResponse(BaseModel):
    """Confirmacao de feedback recebido."""

    ok: bool


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    body: SendMessageRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia mensagem ao assistente IA do portal — agora via orquestrador ESCOPADO ao
    condomínio (client_id). Só lê/entrega dados do próprio cliente; nunca emite documento."""
    from modules.ai.conversation.services.orquestrador.portal_cliente import responder_cliente

    out = await responder_cliente(db, client_id, body.message)
    suggestions = [
        "Quais são meus boletos em aberto?",
        "Me manda a última nota fiscal do condomínio",
        "Quem está alocado no meu condomínio?",
    ]
    return {
        "response": out.get("resposta", "(sem resposta)"),
        "suggestions": suggestions,
        "session_id": body.session_id,
        "message_id": out.get("origem", "consultor_cliente"),
    }


@router.get("/greeting", response_model=GreetingResponse)
async def get_greeting(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retorna saudacao personalizada para o cliente.

    Inclui sugestoes contextuais de perguntas comuns.
    """
    service = PortalAssistantService(db)
    return await service.get_greeting(client_id=client_id)


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Registra feedback do cliente sobre uma resposta do assistente.

    Ajuda a melhorar a qualidade das respostas ao longo do tempo.
    """
    service = PortalAssistantService(db)
    ok = await service.record_feedback(
        client_id=client_id,
        message_id=body.message_id,
        rating=body.rating,
    )
    return {"ok": ok}
