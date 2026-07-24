"""Teste-âncora do user_modules com usuários REAIS de produção (sem pytest)."""
import asyncio

from sqlalchemy import text

from core.auth.module_scope import user_modules
from core.database import async_session_factory


class _U:
    def __init__(self, role, permissions):
        self.role = role
        self.permissions = permissions


async def main() -> None:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT email, role, permissions FROM users "
                    "WHERE email IN ('jjesus@conectamais.pro','egonzaga@conectamais.pro',"
                    "'erikamaquine93@gmail.com','celiane.cg011.garcia@gmail.com')"
                )
            )
        ).fetchall()
        by_email = {r.email: _U(r.role, r.permissions or []) for r in rows}

    esperado = {
        "jjesus@conectamais.pro": {"financeiro", "fiscal", "dp", "ged", "juridico", "crm", "operacional", "sst", "dev"},
        "egonzaga@conectamais.pro": {"ged", "dp", "operacional", "sst"},
        "erikamaquine93@gmail.com": {"sst"},
        "celiane.cg011.garcia@gmail.com": set(),
    }
    for email, exp in esperado.items():
        got = user_modules(by_email[email])
        assert got == exp, f"{email}: esperado {exp}, veio {got}"
        print(f"OK {email}: {sorted(got) or 'set()'}")
    print("TEST module_scope PASS")


if __name__ == "__main__":
    asyncio.run(main())
