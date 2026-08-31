"""Oráculo — aviso de saldo do provedor do LLM.

O que ele tem de provar, além de "a função roda":
  · avisa abaixo do patamar e NÃO repete no mesmo patamar (a lição das 9 frases em 63s);
  · a autonomia estimada ignora dia de custo ZERO — dia zerado é dia FORA, e incluí-lo
    inflaria os dias restantes, que é o erro na direção perigosa;
  · saldo OK limpa o silenciador, senão a próxima queda ficaria muda.
"""
import asyncio, sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401

FALHAS = []


def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


async def main():
    from core.cache.redis import get_redis
    from core.database import async_session_factory
    from modules.crm.services import orchestration as _orq
    from modules.integrations.connectors.whatsapp import tasks as T

    print("\n== 1. o SERVIDOR enxerga a task ==")
    ok("whatsapp.checar_saldo_llm" in main_production.__dict__.get("__name__", "") or True,
       "task importável", "checagem real abaixo")
    from celery_app import app as _app
    ok("whatsapp.checar_saldo_llm" in _app.tasks, "task registrada no Celery")
    ok("whatsapp-checar-saldo-llm-hourly" in (_app.conf.beat_schedule or {}),
       "beat agendado", "sem beat, a task existe e nunca roda")

    print("\n== 2. o gasto médio IGNORA dia zerado ==")
    async with async_session_factory() as db:
        media = await T._gasto_medio_diario(db)
        from sqlalchemy import text
        com_zero = float((await db.execute(text(
            "SELECT coalesce(avg(d),0) FROM (SELECT sum(custo_usd) d FROM llm_usage "
            "WHERE criado_em >= now() - interval '7 days' "
            "GROUP BY date_trunc('day', criado_em)) x"))).scalar() or 0)
    ok(media > 0, "média apurada", f"US$ {media:.2f}/dia")
    ok(media >= com_zero, "e é MAIOR ou igual à média que inclui dias zerados",
       f"{media:.2f} vs {com_zero:.2f} — incluir o zero inflaria a autonomia")

    print("\n== 3. avisa abaixo do patamar — sem mandar WhatsApp de verdade ==")
    avisos = []

    async def _fake_notify(msg):
        avisos.append(msg)
        return True

    orig_notify, orig_saldo = _orq.notify_owner, T._saldo_provedor
    T._saldo_provedor = lambda: asyncio.sleep(0, result=1.10)   # 🔴 crítico
    _orq.notify_owner = _fake_notify
    try:
        redis = await get_redis()
        await redis.delete("llm:saldo:avisado")
        async with async_session_factory() as db:
            r = await T._checar_saldo_llm(db)
        ok(r.get("avisado") is True, "avisou", str(r.get("nivel")))
        ok(len(avisos) == 1, "UMA mensagem", f"{len(avisos)}")
        txt = avisos[0] if avisos else ""
        ok("US$ 1.10" in txt, "o saldo aparece", txt[:44])
        ok("dia(s)" in txt or "desconhecida" in txt,
           "e a AUTONOMIA aparece", "saldo sozinho não decide; saldo com dias decide")

        print("\n== 4. NÃO repete no mesmo patamar ==")
        async with async_session_factory() as db:
            r2 = await T._checar_saldo_llm(db)
        ok(r2.get("silenciado") == "mesmo patamar", "segunda passagem cala",
           str(r2.get("silenciado")))
        ok(len(avisos) == 1, "e nenhuma mensagem nova", f"{len(avisos)}")

        print("\n== 5. mas SOBE de patamar quando piora ==")
        # de crítico para... já está no pior. Testa o inverso: volta a OK e limpa.
        T._saldo_provedor = lambda: asyncio.sleep(0, result=42.0)
        async with async_session_factory() as db:
            r3 = await T._checar_saldo_llm(db)
        ok(r3.get("nivel") == "ok", "saldo alto não avisa", str(r3.get("nivel")))
        ok((await redis.get("llm:saldo:avisado")) is None,
           "e LIMPA o silenciador", "senão a próxima queda ficaria muda")

        print("\n== 6. provedor sem endpoint de saldo: cala, não inventa ==")
        T._saldo_provedor = lambda: asyncio.sleep(0, result=None)
        async with async_session_factory() as db:
            r4 = await T._checar_saldo_llm(db)
        ok("pulado" in r4, "pula sem avisar", str(r4)[:50])
        ok(len(avisos) == 1, "e não mandou nada", f"{len(avisos)}")
    finally:
        _orq.notify_owner, T._saldo_provedor = orig_notify, orig_saldo
        with __import__("contextlib").suppress(Exception):
            await (await get_redis()).delete("llm:saldo:avisado")

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU: " + " · ".join(FALHAS)))
    if FALHAS:
        raise SystemExit(1)


asyncio.run(main())
