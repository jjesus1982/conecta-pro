"""Teste-âncora do `user_modules`: cada PAPEL enxerga exatamente os módulos que deve.

Antes de 11/08/2026 este oráculo listava quatro e-mails de produção. Dois deles saíram da
empresa, `by_email[...]` estourou em KeyError e a falha parecia defeito de RBAC — não era.
O que se ancora aqui é o papel, que é o que o `user_modules` de fato lê.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import usuario_por_papel  # noqa: E402
from core.auth.module_scope import user_modules  # noqa: E402
from core.database import async_session_factory  # noqa: E402

# Em 11/08 este oráculo fixava o conjunto de módulos de cada papel — inclusive
# `"lider": {"sst"}`. Na varredura de 12/08 às 05:00 ele acusou: os usuários com papel
# `lider` têm apenas `self:portal`, então `user_modules` devolve conjunto vazio.
#
# O conjunto NÃO é do papel: é das PERMISSÕES de cada usuário, que mudam sem aviso. Fixá-lo
# foi repetir, no meu próprio conserto, o erro que passei o dia corrigindo nos outros —
# congelar dado e chamar de regra. O que `user_modules` promete é a TRADUÇÃO
# `permission -> módulo`, e é isso que se trava aqui.
CASOS = [
    ({"module:financeiro", "module:dp"}, {"financeiro", "dp"}, "duas permissões, dois módulos"),
    ({"self:portal"}, set(), "permissão de portal não abre módulo nenhum"),
    (set(), set(), "sem permissão, sem módulo"),
    ({"module:dp", "gestao:disciplinar_comunicados"}, {"dp"}, "permissão fora do padrão é ignorada"),
    ({"module:INEXISTENTE"}, set(), "módulo que não existe não entra"),
]


class _U:
    """Usuário sintético: aqui o que se testa é a função, não quem está na base hoje."""

    def __init__(self, role, permissions):
        self.role, self.permissions, self.id = role, list(permissions), "sintetico"


async def main() -> None:
    # ── 1. A tradução permissão -> módulo, sem depender de quem está cadastrado ──
    for perms, esperado, porque in CASOS:
        got = user_modules(_U("supervisor", perms))
        assert got == esperado, f"{porque}: {sorted(perms)} -> esperado {esperado}, veio {got}"
    print(f"OK tradução permissão->módulo: {len(CASOS)} casos")

    # ── 2. admin vê tudo, independente de permissão — é regra do papel, não do usuário ──
    todos = user_modules(_U("admin", []))
    assert len(todos) >= 8, f"admin sem acesso amplo: {sorted(todos)}"
    assert {"financeiro", "fiscal", "dp"} <= todos, f"admin sem módulo essencial: {sorted(todos)}"
    print(f"OK admin: {len(todos)} módulos por papel, sem precisar de permissão")

    # ── 3. Na base REAL, o invariante que importa: quem não é gestor não vê financeiro ──
    async with async_session_factory() as db:
        for papel in ("funcionario", "lider"):
            u = await usuario_por_papel(db, papel)
            if u is None:
                print(f"OK {papel:<12} nenhum usuário ativo — nada a verificar")
                continue
            mods = user_modules(u)
            assert "financeiro" not in mods and "fiscal" not in mods, \
                f"papel '{papel}' enxerga módulo de dinheiro: {sorted(mods)}"
            print(f"OK {papel:<12} {sorted(mods) or 'set()'} (sem financeiro/fiscal)")
    print("TEST module_scope PASS")


if __name__ == "__main__":
    asyncio.run(main())
