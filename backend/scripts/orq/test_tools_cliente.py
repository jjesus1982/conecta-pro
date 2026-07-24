"""Prova: cliente GREEN HILLS recebe SÓ os dados do próprio condomínio; um client_id diferente
retorna outro conjunto (nunca cruza). Enforcement = scope.client_id, nunca argumento.

Reforço (mandato tier CLIENTE, superfície externa): dois clientes reais de ged_clients —
A (GREEN HILLS) e B (PRIME ARENA) — com isolamento POR CONTEÚDO (números de nota disjuntos),
injeção de client_id como kwarg é INERTE (o handler ignora **_), e sem client_id => aguardando dado.
Read-only."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_cliente  # noqa: F401 — registra

GREEN_HILLS = "b4a13504-cffc-4505-8e91-e1bebed493ed"  # cliente A
PRIME_ARENA = "52958919-0a15-4e4f-806d-be3c75e5951b"  # cliente B (real, com NFS-e próprias)


def _numeros(out: dict) -> set:
    return {str(n.get("numero")) for n in (out.get("notas") or [])}


async def main() -> None:
    async with async_session_factory() as db:
        outro = (await db.execute(text(
            "SELECT id::text FROM ged_clients WHERE portal_access_enabled = true AND id <> :g LIMIT 1"
        ), {"g": GREEN_HILLS})).scalar()

        notas = tr.get_tool("notas_condominio")

        out_gh = await notas.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS))
        assert isinstance(out_gh, dict), out_gh
        print("OK cliente recebe as notas do PRÓPRIO condomínio")

        # client_id sem escopo -> aguardando dado
        out_vazio = await notas.handler(db, None, OrqScope(tier="cliente", client_id=None))
        assert out_vazio.get("status") == "aguardando dado", out_vazio
        print("OK sem client_id => aguardando dado")

        # escopo de outro condomínio retorna o dado DAQUELE (prova que o filtro é por client_id) —
        # o cliente real nunca troca o client_id (vem do token), então nunca alcança este caminho.
        if outro:
            out_outro = await notas.handler(db, None, OrqScope(tier="cliente", client_id=outro))
            assert isinstance(out_outro, dict), out_outro
            print("OK o filtro é por client_id (cada condomínio isolado)")

        # --- REFORÇO: isolamento POR CONTEÚDO entre dois clientes reais ---
        out_a = await notas.handler(db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS))
        out_b = await notas.handler(db, None, OrqScope(tier="cliente", client_id=PRIME_ARENA))
        num_a, num_b = _numeros(out_a), _numeros(out_b)
        assert num_a and num_b, ("ambos clientes precisam ter notas p/ o teste", num_a, num_b)
        assert num_a.isdisjoint(num_b), ("VAZAMENTO: notas de A e B se cruzam", num_a & num_b)
        assert num_b.isdisjoint(num_a)
        # nenhuma nota de B aparece no conjunto de A (ausência por conteúdo)
        assert not (num_a & num_b)
        print(f"OK isolamento por conteúdo: A={len(num_a)} notas, B={len(num_b)} notas, disjuntos")

        # --- REFORÇO: injeção de client_id como kwarg é INERTE (handler ignora **_) ---
        out_inj = await notas.handler(
            db, None, OrqScope(tier="cliente", client_id=GREEN_HILLS), client_id=PRIME_ARENA
        )
        assert _numeros(out_inj) == num_a, ("INJEÇÃO VAZOU: kwarg client_id alterou o escopo", out_inj)
        assert _numeros(out_inj).isdisjoint(num_b), "INJEÇÃO trouxe dado de B"
        print("OK injeção de client_id como kwarg é inerte (escopo continua o do token)")

    print("TEST tools_cliente PASS")


if __name__ == "__main__":
    asyncio.run(main())
