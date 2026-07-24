"""Prova: justificar-ponto cria um PENDENTE p/ o DP e NÃO altera gp_clock_punches.
Green compartilha o banco vivo => apaga o registro criado no finally."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.ai.conversation.services.orquestrador.engine import OrqScope
from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador import tools_ponto  # noqa: F401 — registra

CELIANE_EMP = "9e9e1678-9988-490c-b59b-b2786bb67e1c"
MOTIVO = "TESTE ORQ — esqueci de bater a saída dia X (apagar)"


async def main() -> None:
    async with async_session_factory() as db:
        jid = None
        try:
            punches_antes = (await db.execute(text(
                "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
            ), {"e": CELIANE_EMP})).scalar()

            tool = tr.get_tool("justificar_ajuste_de_ponto")
            out = await tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
            assert out["status"] == "pendente", out
            jid = out["justification_id"]
            print("OK justificativa criada como PENDENTE:", jid)

            # o registro está 'pendente' e roteado ao DP (reviewed_by NULL)
            row = (await db.execute(text(
                "SELECT status, reviewed_by FROM gp_justifications WHERE justification_id = :j"
            ), {"j": jid})).first()
            assert row.status == "pendente" and row.reviewed_by is None, row
            print("OK status='pendente' e sem revisão (aguarda o DP)")

            # o PONTO não mudou
            punches_depois = (await db.execute(text(
                "SELECT count(*) FROM gp_clock_punches WHERE employee_id = :e"
            ), {"e": CELIANE_EMP})).scalar()
            assert punches_depois == punches_antes, (punches_antes, punches_depois)
            print("OK ponto INALTERADO (nenhuma batida criada/alterada)")

            # idempotência: repetir não duplica
            out2 = await tool.handler(db, None, OrqScope(tier="clt", employee_id=CELIANE_EMP), motivo=MOTIVO)
            assert out2.get("duplicado") is True, out2
            print("OK idempotente (não duplicou)")

            # escopo sem employee_id -> recusa/"aguardando dado" sem gravar nada
            out3 = await tool.handler(db, None, OrqScope(tier="clt", employee_id=None), motivo=MOTIVO)
            assert out3.get("status") == "aguardando dado", out3
            print("OK sem employee_id -> aguardando dado (não grava)")

            count_marcador = (await db.execute(text(
                "SELECT count(*) FROM gp_justifications WHERE reason = :r"
            ), {"r": MOTIVO})).scalar()
            assert count_marcador == 1, count_marcador
            print("OK exatamente 1 pendente do marcador (idempotência + recusa não geraram lixo)")
        finally:
            deleted = []
            if jid:
                # delete por id EXATO (justification_id do registro que ESTE teste criou) — nunca delete amplo.
                deleted = (await db.execute(text(
                    "DELETE FROM gp_justifications WHERE justification_id = :jid RETURNING id"
                ), {"jid": jid})).fetchall()
                await db.commit()
            print(f"cleanup: {len(deleted)} pendente(s) de teste removido(s) por id exato:", [d[0] for d in deleted])

            remanescentes = (await db.execute(text(
                "SELECT count(*) FROM gp_justifications WHERE reason = :r"
            ), {"r": MOTIVO})).scalar()
            assert remanescentes == 0, f"vazamento de teste: {remanescentes} registro(s) remanescente(s)"
            print("OK 0 remanescentes do marcador em gp_justifications")
    print("TEST tools_ponto PASS")


if __name__ == "__main__":
    asyncio.run(main())
