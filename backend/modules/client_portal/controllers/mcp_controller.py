"""
Controller MCP do Portal do Cliente.

Gera tokens de longa duração para uso com MCP Servers e retorna
instruções de configuração para ferramentas como Claude Desktop.
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel


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


