"""T7 — prova NO BANCO: lead criado com marcador ganha a origem certa.

Exercita a função real (_criar_lead_para_conversa) contra o banco real, com uma
conversa sintética. Limpa tudo que criou no final.
"""

import asyncio
import sys

from sqlalchemy import text

from core.database import async_session_factory
from modules.integrations.connectors.whatsapp.agent_service import _criar_lead_para_conversa
from modules.integrations.connectors.whatsapp.controller import _match_or_create_lead

# Caminho REAL de criação (webhook, 1ª mensagem) — é por onde nasce quase todo lead.
CASOS_WEBHOOK = [
    ("5592900000781", "Ola! quero saber sobre Portaria Remota", "landing_portaria_remota"),
    ("5592900000782", "Preciso de agentes de portaria", "landing_agentes_portaria"),
    ("5592900000783", "Quero MONITORAMENTO pro predio", "landing_monitoramento"),
    ("5592900000784", "vim pelo instagram de voces", "instagram_linktree"),
    ("5592900000785", "Oi, bom dia", "whatsapp"),
]

CASOS = [
    (99900771, "5592900000771", "Ol%C3%A1%21+quero+saber+sobre+Portaria+Remota", "landing_portaria_remota"),
    (99900772, "5592900000772", "Quero AGENTES DE PORTARIA pro condominio", "landing_agentes_portaria"),
    (99900773, "5592900000773", "Interesse em monitoramento 24h", "landing_monitoramento"),
    (99900774, "5592900000774", "Vim pelo Instagram", "instagram_linktree"),
    (99900775, "5592900000775", "Bom dia, preciso de um orcamento", "whatsapp"),
]


async def main(limpar: bool = True) -> int:
    falhas = 0
    async with async_session_factory() as db:
        print("=== caminho WEBHOOK (_match_or_create_lead) ===")
        for phone, texto, esperado in CASOS_WEBHOOK:
            lid = await _match_or_create_lead(db, phone, f"T7 verificacao {phone}", texto)
            await db.commit()
            src = (await db.execute(text("SELECT source FROM leads WHERE id=:i"), {"i": lid})).scalar()
            ok = src == esperado
            falhas += 0 if ok else 1
            print(f"{'OK ' if ok else 'FALHA'} {texto[:34]!r} -> source={src!r} (esperado {esperado!r})")

        print("\n=== caminho AUTO-CURA (_criar_lead_para_conversa) ===")
        for conv, phone, texto, esperado in CASOS:
            await db.execute(
                text(
                    "INSERT INTO cwi_message_log (direction,phone_canonical,chatwoot_conversation_id,"
                    "chatwoot_message_id,content,status) VALUES ('in',:p,:c,:c,:t,'ok') "
                    "ON CONFLICT (chatwoot_message_id) DO NOTHING"
                ),
                {"p": phone, "c": conv, "t": texto},
            )
            await db.commit()
            lid = await _criar_lead_para_conversa(db, conv, f"T7 verificacao {conv}")
            src = (await db.execute(text("SELECT source FROM leads WHERE id=:i"), {"i": lid})).scalar()
            ok = src == esperado
            falhas += 0 if ok else 1
            print(f"{'OK ' if ok else 'FALHA'} conv={conv} texto={texto[:34]!r} -> source={src!r} (esperado {esperado!r})")

        print("\n--- leads criados hoje por origem (últimas 24h) ---")
        for row in (
            await db.execute(
                text(
                    "SELECT source, count(*) FROM leads WHERE created_at > now()-interval '1 day' "
                    "GROUP BY source ORDER BY 2 DESC"
                )
            )
        ).all():
            print(f"  {row[0]:<28} {row[1]}")

        if limpar:
            convs = [c for c, *_ in CASOS]
            phones = [p for _, p, *_ in CASOS] + [p for p, *_ in CASOS_WEBHOOK]
            await db.execute(
                text("DELETE FROM cwi_message_log WHERE chatwoot_conversation_id = ANY(:c)"), {"c": convs}
            )
            await db.execute(
                text("DELETE FROM leads WHERE regexp_replace(coalesce(phone,''),'\\D','','g') = ANY(:p)"),
                {"p": phones},
            )
            await db.commit()
            print("\nlimpeza: leads/logs sintéticos removidos")
    return falhas


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main(limpar="--keep" not in sys.argv)) else 0)
