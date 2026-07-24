"""Registry fail-closed de tools escopadas do orquestrador.

Cada ToolDef declara SEU módulo. Tool sem módulo NÃO registra (fail-closed, mesmo
padrão do TOOL_RISK do conector). O handler executa in-process recebendo
(db, user, scope, **args) — a identidade real do usuário — para o RBAC/escopo barrar na fonte.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDef:
    name: str
    module: str  # módulo canônico (belt) OU 'self'/'cliente' (scope-gated, fora do belt)
    description: str
    params_schema: dict[str, Any]  # JSON-Schema OpenAI ({"type":"object","properties":{...},"required":[...]})
    handler: Callable[..., Awaitable[Any]] = field(compare=False, repr=False)


_REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> ToolDef:
    """Registra a tool. FAIL-CLOSED: sem módulo declarado, levanta e NÃO registra."""
    if not tool.module or not tool.module.strip():
        raise ValueError(f"tool '{tool.name}' sem módulo declarado — recusada (fail-closed)")
    if not tool.name or not tool.name.strip():
        raise ValueError("tool sem nome — recusada")
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
