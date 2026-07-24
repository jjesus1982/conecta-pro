"""Bridge do Portal do Cliente para o engine escopado. Roda com a identidade do portal
(client_id de get_current_portal_client). user=None (identidade externa = client_id)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .engine import OrqScope, run_engine
from .tools_cliente import CLIENTE_TOOLS

_SYSTEM_CLIENTE = (
    "Você é o assistente da Área do Cliente da Conecta Mais, falando com o responsável de UM "
    "condomínio. Responda usando SOMENTE as tools (todas já escopadas ao condomínio deste cliente). "
    "NUNCA invente valores nem fale de outro condomínio. Você pode LOCALIZAR e ENTREGAR um documento "
    "existente do próprio condomínio (nota/boleto), mas NUNCA emite documento novo. Tom simples e cordial."
)


async def responder_cliente(db: AsyncSession, client_id: str, pergunta: str) -> dict[str, Any]:
    scope = OrqScope(tier="cliente", client_id=client_id)
    return await run_engine(
        db, None, scope, list(CLIENTE_TOOLS), pergunta,
        system_prompt=_SYSTEM_CLIENTE, origem="consultor_cliente", max_tokens=900,
    )
