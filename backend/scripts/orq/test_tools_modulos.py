"""Prova: gestor Gonzaga (perms {ged,dp,operacional,sst}) recebe as tools desses módulos
e NUNCA a de financeiro/fiscal/comercial (belt); e o suspenders barra execução fora do módulo."""
import asyncio

from sqlalchemy import text

from core.auth.module_scope import user_modules
from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador import tools_modulos  # noqa: F401 — registra
from modules.ai.conversation.services.orquestrador import tool_registry as tr


class _U:
    def __init__(self, role, permissions):
        self.role, self.permissions, self.id = role, permissions, "x"


async def main() -> None:
    async with async_session_factory() as db:
        r = (await db.execute(text(
            "SELECT role, permissions FROM users WHERE email='egonzaga@conectamais.pro'"
        ))).first()
        gonzaga = _U(r.role, r.permissions or [])

        # BELT: tools que Gonzaga recebe
        mods = user_modules(gonzaga)
        nomes = {t.name for t in tr.tools_for_modules(mods)}
        assert "panorama_operacional" in nomes and "panorama_dp" in nomes and "panorama_ged" in nomes, nomes
        assert "panorama_financeiro" not in nomes, f"VAZAMENTO: financeiro no escopo do gestor! {nomes}"
        assert "panorama_fiscal" not in nomes and "panorama_comercial" not in nomes, nomes
        print("OK belt: gestor recebe {operacional,dp,ged}, sem financeiro/fiscal/comercial")

        # SUSPENDERS: mesmo se a tool de financeiro chegasse ao handler, ele barra
        barrou = False
        try:
            await tr.get_tool("panorama_financeiro").handler(db, gonzaga, None)
        except PermissionError:
            barrou = True
        assert barrou, "suspenders deveria barrar panorama_financeiro para o gestor"
        print("OK suspenders: handler de financeiro barra o gestor")

        # A tool permitida executa e devolve dado real
        out = await tr.get_tool("panorama_operacional").handler(db, gonzaga, None)
        assert isinstance(out, dict), out
        print("OK panorama_operacional executou para o gestor")
    print("TEST tools_modulos PASS")


if __name__ == "__main__":
    asyncio.run(main())
