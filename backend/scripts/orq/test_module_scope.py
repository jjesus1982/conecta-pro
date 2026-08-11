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

# Medido em 11/08/2026 contra a base real. Mudar um destes conjuntos é decisão de RBAC,
# não conserto de teste: alguém passou a ver (ou deixou de ver) um módulo inteiro.
ESPERADO = {
    "admin": {"financeiro", "fiscal", "dp", "ged", "juridico", "crm", "operacional", "sst", "dev"},
    "supervisor": {"ged", "dp", "operacional", "sst"},
    "lider": {"sst"},
    "funcionario": set(),
}


async def main() -> None:
    async with async_session_factory() as db:
        achados = {papel: await usuario_por_papel(db, papel) for papel in ESPERADO}

    ausentes = [p for p, u in achados.items() if u is None]
    assert not ausentes, f"papéis sem usuário ativo na base: {ausentes}"

    for papel, esperado in ESPERADO.items():
        got = user_modules(achados[papel])
        assert got == esperado, f"papel '{papel}': esperado {esperado}, veio {got}"
        print(f"OK {papel:<12} {sorted(got) or 'set()'}")
    print("TEST module_scope PASS")


if __name__ == "__main__":
    asyncio.run(main())
