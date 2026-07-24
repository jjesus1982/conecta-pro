"""Escopo de MÓDULO por usuário (belt do orquestrador escopado — Peça 3).

Reusa `users.role` + `users.permissions[]` (o mesmo que `require_permission` já
enforça no endpoint). NÃO é a fronteira sozinho: é o filtro que decide QUAIS tools
o LLM sequer recebe. A fronteira real continua no handler (require_permission/scope/self).
"""
from __future__ import annotations

# Módulos canônicos do ERP (gates em main_production.py). dev/suporte NÃO têm
# financeiro/fiscal nas permissions → a régua "exceto os 3 sensíveis" cai fora
# naturalmente das permissions, sem hardcode.
CANONICAL_MODULES: frozenset[str] = frozenset(
    {"financeiro", "fiscal", "dp", "ged", "juridico", "crm", "operacional", "sst", "dev"}
)


def user_modules(user) -> set[str]:
    """Conjunto de módulos que o usuário pode ver.

    - role == 'admin' OU '*'/'all' em permissions -> TODOS os canônicos.
    - senão -> os prefixados 'module:X' em permissions, interceptados com os canônicos.
    """
    role = (getattr(user, "role", None) or "").lower()
    perms = getattr(user, "permissions", None) or []
    if role == "admin" or "*" in perms or "all" in perms:
        return set(CANONICAL_MODULES)
    mods = {
        p.split("module:", 1)[1]
        for p in perms
        if isinstance(p, str) and p.startswith("module:")
    }
    return mods & set(CANONICAL_MODULES)


def user_has_module(user, module: str) -> bool:
    """Suspenders in-process: o handler chama isto antes de executar (defesa em profundidade)."""
    return module in user_modules(user)
