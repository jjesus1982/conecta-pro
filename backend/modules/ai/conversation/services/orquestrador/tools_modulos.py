"""Tools de MÓDULO (gestor/dev): panoramas org-wide DENTRO do módulo permitido.

Cada tool carrega seu módulo canônico (belt em user_modules). Suspenders: o handler
re-checa user_has_module(user, <mod>) e levanta PermissionError se faltar (o engine
converte em 'fora do seu escopo'). Reusa os panoramas existentes — sem lógica nova.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _gate(user, module: str) -> None:
    if not user_has_module(user, module):
        raise PermissionError(module)


async def _op(db, user, scope, **_):
    _gate(user, "operacional")
    from modules.operacional.services import consultor_coo_service
    return await consultor_coo_service.panorama(db)


async def _dp(db, user, scope, **_):
    _gate(user, "dp")
    from modules.people_management.services import consultor_chro_service
    return await consultor_chro_service.panorama(db)


async def _fiscal(db, user, scope, **_):
    _gate(user, "fiscal")
    from modules.fiscal.services import consultor_fiscal_service
    return await consultor_fiscal_service.panorama(db)


async def _ged(db, user, scope, **_):
    _gate(user, "ged")
    from modules.gedeon.services import consultor_service as _ged_svc
    return await _ged_svc.panorama(db)


async def _comercial(db, user, scope, **_):
    _gate(user, "crm")
    from modules.crm.services import consultor_cmo_service
    return await consultor_cmo_service.panorama(db)


async def _financeiro(db, user, scope, **_) -> dict[str, Any]:
    _gate(user, "financeiro")
    from modules.financial.services import caixa_service
    return await caixa_service.caixa_por_cnpj(db)


register(ToolDef("panorama_operacional", "operacional",
                 "Panorama operacional org-wide: postos, escalas, cobertura, presença.", _NO_ARGS, _op))
register(ToolDef("panorama_dp", "dp",
                 "Panorama de DP/RH org-wide: colaboradores, ponto, folha, CCT.", _NO_ARGS, _dp))
register(ToolDef("panorama_fiscal", "fiscal",
                 "Panorama fiscal/contábil org-wide: notas, guias, certidões.", _NO_ARGS, _fiscal))
register(ToolDef("panorama_ged", "ged",
                 "Panorama documental (GED/GEDEON): kits, panorama de documentos.", _NO_ARGS, _ged))
register(ToolDef("panorama_comercial", "crm",
                 "Panorama comercial/CRM org-wide: funil, propostas, clientes.", _NO_ARGS, _comercial))
register(ToolDef("panorama_financeiro", "financeiro",
                 "Caixa por CNPJ (Inter/Eletrônica e Cora/Patrimonial), saldo e folha.", _NO_ARGS, _financeiro))
