"""Tools CONDOMÍNIO-SCOPED (tier cliente externo). Filtram por scope.client_id (=ged_clients.id),
NUNCA por argumento — o cliente jamais alcança outro condomínio. Reusam os services do portal
(portal_financeiro_service / portal_operacao_service), que já resolvem o escopo por client_id."""
from __future__ import annotations

from typing import Any

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _cid(scope) -> str | None:
    return getattr(scope, "client_id", None) if scope else None


async def _notas(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.notas(db, cid)


async def _contrato(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.contrato(db, cid)


async def _boletos(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.boletos(db, cid)


async def _equipe(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_operacao_service
    return await portal_operacao_service.equipe(db, cid)


CLIENTE_TOOLS: list[ToolDef] = [
    register(ToolDef("notas_condominio", "cliente",
                     "Notas fiscais (NFS-e) do MEU condomínio.", _NO_ARGS, _notas)),
    register(ToolDef("contrato_condominio", "cliente",
                     "O contrato vigente do MEU condomínio.", _NO_ARGS, _contrato)),
    register(ToolDef("boletos_condominio", "cliente",
                     "Os boletos/cobranças do MEU condomínio.", _NO_ARGS, _boletos)),
    register(ToolDef("equipe_condominio", "cliente",
                     "A equipe/funcionários alocados no MEU condomínio.", _NO_ARGS, _equipe)),
]
