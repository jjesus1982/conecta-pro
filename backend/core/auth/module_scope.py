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
    mods = {p.split("module:", 1)[1] for p in perms if isinstance(p, str) and p.startswith("module:")}
    return mods & set(CANONICAL_MODULES)


def user_has_module(user, module: str) -> bool:
    """Suspenders in-process: o handler chama isto antes de executar (defesa em profundidade)."""
    return module in user_modules(user)


def exigir_dono(user, employee_id, *, modulo: str = "dp") -> None:
    """Documento de UMA pessoa: quem não tem o módulo só alcança o PRÓPRIO cadastro.

    24/09/2026 (DGX Y5, medido no sandbox): `GET /api/v1/redesign/ferias/{id}/recibo/pdf`,
    `.../aviso/pdf` e `GET /api/v1/redesign/crachas/pdf?ids=` devolviam 200 e `%PDF` com o
    documento de OUTRA pessoa para o token de qualquer colaborador — as rotas pediam só
    `CurrentActiveUser`, que prova que você entrou, não que o papel é seu.

    404 de propósito, e não 403: um 403 confirmaria que aquele documento existe.
    """
    if user_has_module(user, modulo):
        return
    meu = str(getattr(user, "employee_id", "") or "")
    if not meu or meu != str(employee_id or ""):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Documento não encontrado.")
