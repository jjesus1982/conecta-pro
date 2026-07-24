"""Registry fail-closed de tools escopadas do orquestrador.

Cada ToolDef declara SEU módulo. Tool sem módulo NÃO registra (fail-closed, mesmo
padrão do TOOL_RISK do conector). O handler executa in-process recebendo
(db, user, scope, **args) — a identidade real do usuário — para o RBAC/escopo barrar na fonte.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


#: Dimensões de escopo válidas de uma tool (m13). "org" = panorama org-wide dentro do
#: módulo (belt); "posto"/"self"/"cliente" = escopadas por scope.post_ids/employee_id/client_id.
VALID_SCOPE_KINDS = frozenset({"org", "posto", "self", "cliente"})

#: Chaves que NUNCA podem aparecer como propriedade no params_schema exposto ao LLM (m3):
#: o handler as recebe do runtime (db/user/scope), jamais do argumento do modelo.
_FORBIDDEN_PROPS = frozenset({"db", "user", "scope"})


@dataclass(frozen=True)
class ToolDef:
    name: str
    module: str  # módulo canônico (belt) OU 'self'/'cliente' (scope-gated, fora do belt)
    description: str
    params_schema: dict[str, Any]  # JSON-Schema OpenAI ({"type":"object","properties":{...},"required":[...]})
    handler: Callable[..., Awaitable[Any]] = field(compare=False, repr=False)
    scope_kind: str = "org"  # dimensão de escopo (m13): "org"|"posto"|"self"|"cliente"


_REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> ToolDef:
    """Registra a tool. FAIL-CLOSED: sem módulo declarado, levanta e NÃO registra."""
    if not tool.module or not tool.module.strip():
        raise ValueError(f"tool '{tool.name}' sem módulo declarado — recusada (fail-closed)")
    if not tool.name or not tool.name.strip():
        raise ValueError("tool sem nome — recusada")
    # m13: scope_kind tem de ser uma das dimensões válidas (fail-closed contra typo/tool futura).
    if tool.scope_kind not in VALID_SCOPE_KINDS:
        raise ValueError(
            f"tool '{tool.name}' com scope_kind inválido {tool.scope_kind!r} — "
            f"esperado um de {sorted(VALID_SCOPE_KINDS)} (fail-closed)"
        )
    # m3: o params_schema exposto ao LLM não pode declarar db/user/scope como propriedade
    # (essas vêm do runtime; expô-las abriria uma via de injeção de identidade/conexão).
    props = (tool.params_schema or {}).get("properties") or {}
    proibidas = _FORBIDDEN_PROPS & set(props)
    if proibidas:
        raise ValueError(
            f"tool '{tool.name}' expõe propriedade(s) reservada(s) {sorted(proibidas)} no params_schema — "
            f"recusada (essas vêm do runtime, nunca do LLM)"
        )
    if tool.name in _REGISTRY:
        raise ValueError(
            f"tool duplicada: {tool.name!r} já registrada (módulo {_REGISTRY[tool.name].module!r})"
        )
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> ToolDef | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolDef]:
    return list(_REGISTRY.values())


def tools_for_modules(mods: set[str]) -> list[ToolDef]:
    """Belt: só as tools cujo módulo ∈ mods (nunca considera 'self'/'cliente')."""
    return [t for t in _REGISTRY.values() if t.module in mods]


def openai_schema(tool: ToolDef) -> dict[str, Any]:
    """Converte a ToolDef no schema de function-tool do OpenAI chat.completions."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.params_schema,
        },
    }
