"""
Controller MCP do Portal do Cliente.

Gera tokens de longa duração para uso com MCP Servers e retorna
instruções de configuração para ferramentas como Claude Desktop.
"""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["Portal - MCP"])

API_BASE_URL = os.getenv("API_BASE_URL", "https://erp.conectamais.pro")


# ============================================================
# Schemas
# ============================================================


class MCPTokenResponse(BaseModel):
    mcp_token: str
    expires_at: datetime
    api_url: str
    instructions: str
    claude_config: dict


class MCPRevokeResponse(BaseModel):
    revoked: bool


# ============================================================
# Endpoints
# ============================================================


@router.post("/token", response_model=MCPTokenResponse)
async def generate_mcp_token(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera token MCP de 30 dias para uso com Claude Desktop e ferramentas AI."""
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=30)

    # Salvar token no extra_data da sessão do cliente
    try:
        await db.execute(
            text("UPDATE ged_clients SET extra_data = COALESCE(extra_data, '{}') || :patch WHERE id = :cid"),
            {
                "patch": f'{{"mcp_token": "{token}", "mcp_expires": "{expires_at.isoformat()}"}}',
                "cid": client_id,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Falha ao salvar mcp_token em ged_clients: %s — token apenas retornado", exc)

    claude_config = {
        "mcpServers": {
            "conecta-portal": {
                "command": "python3",
                "args": ["/opt/conecta-pro/backend/mcp_portal_server.py"],
                "env": {
                    "PORTAL_TOKEN": token,
                    "API_URL": API_BASE_URL,
                },
            }
        }
    }

    instructions = (
        "1. Copie o token gerado acima.\n"
        "2. Abra o Claude Desktop → Configurações → Developer → Edit Config.\n"
        "3. Cole a configuração JSON mostrada abaixo.\n"
        "4. Reinicie o Claude Desktop.\n"
        "5. Você verá 'conecta-portal' disponível como ferramenta MCP.\n"
        "6. Agora pode perguntar: 'Liste meus kits', 'Abra um chamado', etc."
    )

    return MCPTokenResponse(
        mcp_token=token,
        expires_at=expires_at,
        api_url=API_BASE_URL,
        instructions=instructions,
        claude_config=claude_config,
    )


@router.delete("/token", response_model=MCPRevokeResponse)
async def revoke_mcp_token(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Revoga o token MCP ativo."""
    try:
        await db.execute(
            text("UPDATE ged_clients SET extra_data = extra_data - 'mcp_token' - 'mcp_expires' WHERE id = :cid"),
            {"cid": client_id},
        )
        await db.commit()
        return MCPRevokeResponse(revoked=True)
    except Exception as exc:
        logger.warning("Falha ao revogar mcp_token: %s", exc)
        return MCPRevokeResponse(revoked=False)
