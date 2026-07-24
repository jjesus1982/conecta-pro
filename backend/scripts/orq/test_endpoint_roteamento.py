"""Prova o roteamento por tier (sem chamar o LLM): cada identidade real recebe o tier
e o conjunto de tools corretos. Gestor NUNCA recebe tool de financeiro."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.controllers.consultor_escopado_controller import _resolver_tier_e_tools


class _U:
    def __init__(self, id, role, permissions):
        self.id, self.role, self.permissions = id, role, permissions


async def _user(db, email):
    r = (await db.execute(text(
        "SELECT id::text, role, permissions FROM users WHERE email = :e"
    ), {"e": email})).first()
    return _U(r[0], r.role, r.permissions or [])


async def main() -> None:
    async with async_session_factory() as db:
        # GESTOR
        gonzaga = await _user(db, "egonzaga@conectamais.pro")
        scope, tools = await _resolver_tier_e_tools(db, gonzaga)
        nomes = {t.name for t in tools}
        assert scope.tier == "gestor", scope
        assert "panorama_operacional" in nomes and "panorama_financeiro" not in nomes, nomes
        assert not any(t.module == "self" for t in tools), "gestor não deve ter tools self"
        print("OK gestor: tier=gestor, módulos org-wide, SEM financeiro/self")

        # LÍDER
        erika = await _user(db, "erikamaquine93@gmail.com")
        scope, tools = await _resolver_tier_e_tools(db, erika)
        nomes = {t.name for t in tools}
        assert scope.tier == "lider" and scope.post_ids, scope
        assert "posto_escala_hoje" in nomes and "meu_ponto" in nomes and "justificar_ajuste_de_ponto" in nomes, nomes
        print("OK líder: tier=lider, posto-scoped + self + justificar")

        # CLT
        celiane = await _user(db, "celiane.cg011.garcia@gmail.com")
        scope, tools = await _resolver_tier_e_tools(db, celiane)
        nomes = {t.name for t in tools}
        assert scope.tier == "clt" and scope.employee_id, scope
        assert nomes == {"meu_ponto", "meu_holerite", "minha_escala", "justificar_ajuste_de_ponto"}, nomes
        assert not any(t.module in ("operacional", "financeiro", "dp") for t in tools), nomes
        print("OK CLT: tier=clt, só self + justificar (nenhum panorama de módulo)")
    print("TEST endpoint_roteamento PASS")


if __name__ == "__main__":
    asyncio.run(main())
