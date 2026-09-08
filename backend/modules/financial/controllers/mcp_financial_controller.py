"""Controller MCP Financial — expõe as 8 ferramentas MCP via HTTP REST."""

from fastapi import APIRouter, Depends

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/mcp/financial", tags=["MCP Financial"])


@router.get("/tools", summary="Lista as 8 ferramentas MCP financeiras")
async def list_mcp_tools(current_user=Depends(get_current_user)):
    """Lista todas as ferramentas MCP disponíveis com schema de entrada."""
    from financial_mcp_server import MCP_TOOLS_SCHEMA

    return {"tools": MCP_TOOLS_SCHEMA, "total": len(MCP_TOOLS_SCHEMA)}


