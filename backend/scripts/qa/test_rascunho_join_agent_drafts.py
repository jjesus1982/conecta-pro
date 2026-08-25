"""Prova mínima do conserto da chave órfã, SEM acionar turno de conversa.

Não roda o José Luís de ponta a ponta de propósito: o loop responde ao lead ao
final de cada turno (agent_service.py:4603) e o handoff dispara WhatsApp para o
RESPONSÁVEL cadastrado (2414). Testar pela conversa usaria o telefone de um
colega como aparelho de teste. Chamo o adaptador direto, que é o teste mínimo
que responde a pergunta.

Verifica AS DUAS METADES, porque o defeito original era exatamente uma metade
sem a outra: rascunho apagado com notificação viva.

Desmonta na ENTRADA e na SAÍDA, por PREFIXO — regra da casa de hoje. Execução
morta não deixa lista de ids para a seguinte; só o prefixo alcança órfão.
"""
import asyncio
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

MARCA = "ZZTESTE_JL_JOIN"


async def _limpar(db):
    await db.execute(text(
        "DELETE FROM communication_notifications WHERE reference_type = 'agent_draft'"
        "   AND reference_id::text IN (SELECT id::text FROM agent_drafts WHERE titulo LIKE :m)"),
        {"m": f"%{MARCA}%"})
    await db.execute(text("DELETE FROM agent_drafts WHERE titulo LIKE :m"), {"m": f"%{MARCA}%"})
    await db.commit()


async def main() -> int:
    from types import SimpleNamespace

    from modules.ai.conversation.services.orquestrador.acoes.base import ROLES_COMERCIAL
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    falhas = []
    async with async_session_factory() as db:
        await _limpar(db)
        try:
            agente = SimpleNamespace(id=None, nome="José Luís (WhatsApp)")
            comum = dict(tipo="crm_proposta", modulo="crm", gate="🔴", requires_otp=False,
                         roles_aprovador=ROLES_COMERCIAL,
                         titulo=f"{MARCA} — proposta de teste",
                         resumo="prova do JOIN com agent_drafts",
                         payload={"origem": "whatsapp_jose_luis", "marca": MARCA})

            r1 = await criar_rascunho(db, agente, **comum)
            did = r1.get("draft_id") or r1.get("id")
            print(f"  1) criou rascunho .......... {r1.get('status')} · id={str(did)[:8]}")
            if not did:
                falhas.append(f"1) não devolveu draft_id: {r1}")

            # METADE A — o rascunho existe
            n_d = (await db.execute(text("SELECT count(*) FROM agent_drafts WHERE titulo LIKE :m"),
                                    {"m": f"%{MARCA}%"})).scalar()
            print(f"  2) rascunho em agent_drafts  {n_d}")
            if n_d != 1:
                falhas.append(f"2) esperava 1 rascunho, achei {n_d}")

            # METADE B — a notificação nasceu junto. É o irmão do mesmo defeito:
            # provar só o JOIN e deixar a notificação falhar calada refaz o buraco.
            n_n = (await db.execute(text(
                "SELECT count(*) FROM communication_notifications "
                " WHERE reference_type = 'agent_draft' AND reference_id::text = :d"),
                {"d": str(did)})).scalar()
            # Quantos DEVERIAM ser avisados. Uma notificação por destinatário — os 5
            # observados são 5 admins ativos, não ruído. Comparar com >= 1 deixaria
            # o teste verde no dia em que o fan-out quebrasse e nascesse uma só.
            esperado = (await db.execute(text(
                "SELECT count(*) FROM users WHERE role = ANY(:r) AND is_active IS TRUE"),
                {"r": list(ROLES_COMERCIAL)})).scalar()
            print(f"  3) notificação nasceu junto  {n_n} (aprovadores ativos: {esperado})")
            if n_n < 1:
                falhas.append("3) NOTIFICAÇÃO NÃO NASCEU — rascunho existe e ninguém é avisado; "
                              "é o mesmo defeito pelo outro lado")
            elif n_n != esperado:
                falhas.append(f"3) FAN-OUT INCOMPLETO: {n_n} notificações para {esperado} "
                              "aprovadores ativos — alguém que devia aprovar não foi avisado")

            # 4) O CONSERTO: apago só o rascunho, deixando a notificação viva.
            #    É exatamente o estado que gerava a chave órfã. Com o JOIN, a chave
            #    NÃO pode mais bloquear — tem que criar de novo.
            await db.execute(text("DELETE FROM agent_drafts WHERE titulo LIKE :m"), {"m": f"%{MARCA}%"})
            await db.commit()
            r2 = await criar_rascunho(db, agente, **comum)
            did2 = r2.get("draft_id") or r2.get("id")
            print(f"  4) com órfã, recriou ....... {r2.get('status')} · id={str(did2)[:8]}")
            if r2.get("duplicado") or not did2:
                falhas.append(f"4) CHAVE ÓRFÃ AINDA BLOQUEIA: {r2} — o JOIN não pegou")
        finally:
            await _limpar(db)

    for f in falhas:
        print(f"  FALHA: {f}")
    print("\n" + ("PASSOU — o JOIN não bloqueia por órfã, e as duas metades nascem"
                  if not falhas else f"{len(falhas)} FALHA(S)"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
