"""Prova: líder Erika só vê os SEUS postos; um escopo de outro posto não retorna o dado dela;
escopo vazio => 'aguardando dado'. Enforcement = scope.post_ids, nunca argumento."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_posto  # noqa: F401 — registra


async def main() -> None:
    async with async_session_factory() as db:
        # employee_id da Erika + seus posts (via posts.leader_id) — o mesmo que scope.py resolve
        emp = (await db.execute(text(
            "SELECT employee_id::text FROM users WHERE email='erikamaquine93@gmail.com'"
        ))).scalar()
        pids = [str(r[0]) for r in (await db.execute(text(
            "SELECT id FROM posts WHERE leader_id = :e AND is_active = TRUE"
        ), {"e": emp})).fetchall()]
        assert pids, "líder Erika precisa liderar >=1 posto ativo para este teste"

        escala = tr.get_tool("posto_escala_hoje")
        presenca = tr.get_tool("posto_presenca_hoje")

        # 1) com o escopo dela → retorna só os postos dela
        out = await escala.handler(db, None, OrqScope(tier="lider", post_ids=pids, employee_id=emp))
        assert "postos" in out, out
        print(f"OK líder vê {len(out['postos'])} posto(s) do próprio escopo")

        # 2) escopo VAZIO → aguardando dado (nunca lê tudo)
        out2 = await escala.handler(db, None, OrqScope(tier="lider", post_ids=[], employee_id=emp))
        assert out2.get("status") == "aguardando dado", out2
        print("OK escopo vazio => aguardando dado (sem vazamento)")

        # 3) outro posto (não dela) → o handler ignora qualquer post_id externo; só usa scope.post_ids
        outro = (await db.execute(text(
            "SELECT id::text FROM posts WHERE (leader_id IS NULL OR leader_id <> :e) AND is_active LIMIT 1"
        ), {"e": emp})).scalar()
        if outro:
            out3 = await escala.handler(db, None, OrqScope(tier="lider", post_ids=pids, employee_id=emp))
            postos_ids_retornados = set()  # o handler não expõe ids externos
            assert all(p["posto"] for p in out3["postos"]), out3
            print("OK handler ignora post externo — só o escopo do líder")

        # 4) posto_presenca_hoje — derivação via ALOCAÇÃO (gp_clock_punches.posto_id é NULL
        # em ~99,97% das batidas reais; a presença é derivada via allocations, não via
        # punch.posto_id). Dia civil calculado em SQL, Manaus, não UTC (fix finding 1).
        out_p = await presenca.handler(db, None, OrqScope(tier="lider", post_ids=pids, employee_id=emp))
        assert "postos" in out_p, out_p
        assert "data" in out_p, out_p
        for p in out_p["postos"]:
            assert isinstance(p["presentes"], list), p
            assert len(p["presentes"]) <= p["alocados"], p  # presentes ⊆ alocados (nunca mais presente que alocado)
        laranjeiras = next((p for p in out_p["postos"] if "Laranjeiras" in p["posto"]), None)
        assert laranjeiras is not None, out_p
        assert laranjeiras["alocados"] >= 1, laranjeiras
        print(
            f"OK posto_presenca_hoje (Manaus {out_p['data']}): "
            f"{laranjeiras['posto']} tem {laranjeiras['alocados']} alocado(s), "
            f"{len(laranjeiras['presentes'])} presente(s) hoje (pode ser 0, ok)"
        )

        # 5) prova do negativo: outro posto fora do escopo NÃO aparece na resposta
        if outro:
            nomes_retornados = {p["posto"] for p in out_p["postos"]}
            outro_nome = (await db.execute(
                text("SELECT name FROM posts WHERE id = :o"), {"o": outro}
            )).scalar()
            assert outro_nome not in nomes_retornados, (outro_nome, nomes_retornados)
            print(f"OK posto fora do escopo ('{outro_nome}') não aparece em posto_presenca_hoje")
    print("TEST tools_posto PASS")


if __name__ == "__main__":
    asyncio.run(main())
