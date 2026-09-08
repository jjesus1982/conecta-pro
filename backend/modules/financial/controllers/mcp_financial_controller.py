"""Controller MCP Financial — expõe as 8 ferramentas MCP via HTTP REST."""

from fastapi import APIRouter, Depends

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/mcp/financial", tags=["MCP Financial"])


