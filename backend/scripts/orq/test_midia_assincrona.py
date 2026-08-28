"""Oráculo — a janela cega da mídia assíncrona (28/08/2026).

Com a análise de foto/vídeo fora do webhook, existe um instante em que a mensagem já está
no histórico e a descrição do anexo ainda não. Responder aí é o pior defeito da obra: o
agente falaria sobre a foto SEM tê-la visto — e diria que viu. Mentira com naturalidade é
pior que demora, e não aparece em log nenhum.

O T6 pediu para testar isto de propósito em vez de assumir. É o que este oráculo faz.

Defende:
  1. Enquanto o contador `jl:midia:conv:*` for > 0, `processar_incoming` NÃO gera resposta.
  2. Contador zerado, o caminho volta ao normal.
  3. A marca de análise existe e é a MESMA nos dois lados (webhook põe, task substitui) —
     se divergirem, a marca fica para sempre na conversa e o agente lê "[analisando…]"
     como se fosse conteúdo.
  4. A task e a rota existem, e a fila é a mesma da resposta: ordem entre elas importa.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

FALHAS: list[str] = []
CONV = 987654321  # conversa que não existe: nada real é tocado


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415 — grafo do servidor

    from celery_app import app
    from core.cache.redis import get_redis
    from modules.integrations.connectors.whatsapp import agent_service as A
    from modules.integrations.connectors.whatsapp import controller as C
    from modules.integrations.connectors.whatsapp import tasks as T

    # 3 · a marca é uma só
    checar(bool(T.MARCA_ANALISE), "a marca de análise existe", repr(T.MARCA_ANALISE))
    fonte = open("/app/modules/integrations/connectors/whatsapp/controller.py",
                 encoding="utf-8").read()
    checar("MARCA_ANALISE as _MARCA_ANALISE" in fonte,
           "o webhook usa a MESMA marca da task (importada, não copiada)",
           "" if "MARCA_ANALISE as _MARCA_ANALISE" in fonte else
           "marca duplicada — se divergirem, '[analisando…]' fica para sempre na conversa")

    # 4 · task e rota
    checar("whatsapp.analisar_midia" in app.tasks, "a task está registrada")
    rota = app.conf.task_routes.get("whatsapp.analisar_midia") or {}
    checar(rota.get("queue") == "webhooks", "roteada para `webhooks`", str(rota))
    checar((app.conf.task_routes.get("whatsapp.processar_incoming") or {}).get("queue")
           == rota.get("queue"), "mídia e resposta na MESMA fila (a ordem entre elas importa)")
    checar(T.analisar_midia.acks_late is True,
           "acks_late: worker que morre no meio devolve o anexo para a fila")

    # 1 · a trava
    redis = await get_redis()
    chave = f"jl:midia:conv:{CONV}"
    await redis.set(chave, "2", ex=60)
    chamou = {"n": 0}

    async def _fake(cid, ph=None):
        chamou["n"] += 1

    orig = A._processar_incoming_inner
    A._processar_incoming_inner = _fake
    try:
        await A.processar_incoming(CONV, "9299999999")
        checar(chamou["n"] == 0,
               "com anexo em análise, o turno NÃO responde",
               f"gerou {chamou['n']} resposta(s) às cegas" if chamou["n"] else "adiou")

        # 2 · zerado, volta ao normal
        await redis.delete(chave)
        await A.processar_incoming(CONV, "9299999999")
        checar(chamou["n"] == 1, "contador zerado, o turno volta a responder",
               f"chamadas={chamou['n']}")
    finally:
        A._processar_incoming_inner = orig
        await redis.delete(chave)
        await redis.delete(f"jl:lock:conv:{CONV}")
        await redis.delete(f"jl:pend:conv:{CONV}")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ o agente não fala de foto que ainda não viu.")
    return 0


sys.exit(asyncio.run(main()))
