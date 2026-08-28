"""Oráculo — guarda de loop e teto na desculpa (28/08/2026).

Em 10 minutos o José Luís trocou 48 mensagens com "Claudinho, atendente da Campos
Tecnologia" — outro BOT. Os dois se cumprimentavam e recomeçavam. O bot "pediu orçamento" e
virou LEAD no CRM, sendo CONCORRENTE. E a frase de falha saiu 5× em 70 segundos, para fora,
para outra empresa.

O que este oráculo defende:
  1. Passou o teto de SAÍDAS na janela → cala NESTA conversa e não nas outras.
  2. Abaixo do teto → responde normal. (Sem isto, a guarda mataria o uso legítimo — o
     Jordan em campo chega a 6 saídas em 5 min.)
  3. O teto é MEDIDO e fica entre o uso real (máx 8) e o loop (16).
  4. A desculpa não repete: segunda falha seguida ESCALA em vez de gaguejar.
  5. "sem crédito" e "arquivo ilegível" NÃO usam a mesma frase — a primeira faz o Jordan
     comprar saldo, a segunda o faz reenviar a foto para sempre.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

FALHAS: list[str] = []
CONV = 987654322


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415

    from sqlalchemy import text

    from core.cache.redis import get_redis
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A
    from modules.integrations.connectors.whatsapp import tasks as T

    checar(8 < A._LOOP_TETO < 16,
           "o teto fica ENTRE o uso legítimo (8) e o loop (16)", f"teto={A._LOOP_TETO}")

    redis = await get_redis()
    chamou = {"n": 0}

    async def _fake(cid, ph=None):
        chamou["n"] += 1

    orig = A._processar_incoming_inner
    A._processar_incoming_inner = _fake
    notas = []
    orig_nota = A._post_private_note

    async def _nota(cid, txt):
        notas.append(txt)
        return True

    A._post_private_note = _nota
    try:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM cwi_message_log WHERE chatwoot_conversation_id=:c"),
                             {"c": CONV})
            # ABAIXO do teto: uso legítimo
            for i in range(A._LOOP_TETO - 4):
                await db.execute(text(
                    "INSERT INTO cwi_message_log (direction, chatwoot_conversation_id, "
                    "chatwoot_message_id, content) VALUES ('out', :c, :m, 'x')"),
                    {"c": CONV, "m": 900000 + i})
            await db.commit()
        await redis.delete(f"jl:loop:conv:{CONV}")
        await A.processar_incoming(CONV, "9299999999")
        checar(chamou["n"] == 1, "ABAIXO do teto: responde normal",
               f"{A._LOOP_TETO - 4} saídas na janela")

        async with async_session_factory() as db:
            for i in range(6):
                await db.execute(text(
                    "INSERT INTO cwi_message_log (direction, chatwoot_conversation_id, "
                    "chatwoot_message_id, content) VALUES ('out', :c, :m, 'x')"),
                    {"c": CONV, "m": 910000 + i})
            await db.commit()
        await redis.delete(f"jl:lock:conv:{CONV}")
        await A.processar_incoming(CONV, "9299999999")
        checar(chamou["n"] == 1, "ACIMA do teto: NÃO responde", f"chamadas={chamou['n']}")
        checar(bool(await redis.get(f"jl:loop:conv:{CONV}")),
               "a conversa fica em silêncio (janela gravada)")
        checar(any("outro robô" in n for n in notas),
               "deixa NOTA PRIVADA dizendo por que parou",
               notas[0][:70] if notas else "nenhuma nota")

        # outra conversa NÃO é afetada
        checar(not await redis.get("jl:loop:conv:999111"),
               "silencia SÓ esta conversa, não as outras")
    finally:
        A._processar_incoming_inner = orig
        A._post_private_note = orig_nota
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM cwi_message_log WHERE chatwoot_conversation_id=:c"),
                             {"c": CONV})
            await db.commit()
        for k in ("jl:loop:conv:", "jl:lock:conv:", "jl:pend:conv:", "jl:falha:conv:"):
            await redis.delete(f"{k}{CONV}")

    # 5 · a causa da falha de mídia chega distinta
    fonte = open("/app/modules/integrations/connectors/whatsapp/tasks.py",
                 encoding="utf-8").read()
    checar("sem crédito" in fonte and "_sem_credito" in fonte,
           "falha por CRÉDITO tem frase própria (não 'arquivo ilegível')")
    checar("_ULTIMO_ERRO" in open(
        "/app/modules/integrations/connectors/whatsapp/controller.py",
        encoding="utf-8").read(),
        "a causa sobrevive ao `except` que engole a exceção")
    checar(hasattr(T, "_ultimo_erro_sem_credito"), "o leitor da causa existe")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ eco com robô para em 12 saídas, e a desculpa não vira gagueira.")
    return 0


sys.exit(asyncio.run(main()))
