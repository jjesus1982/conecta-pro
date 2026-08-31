import asyncio, sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401
FALHAS = []
def ok(c, n, d=""):
    print("  %s %s%s" % ("✅" if c else "❌", n, (" — " + d) if d else ""))
    if not c: FALHAS.append(n)

async def main():
    from sqlalchemy import text
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A
    from modules.integrations.connectors.whatsapp import service as _svc

    async def novo_draft():
        r = await A._tool_pedir_cotacao({
            "fornecedor": "Kely", "obra": "The Sun",
            "itens": ["ORACULO A", "ORACULO B"],
            "observacao": "teste de ordem"})
        async with async_session_factory() as db:
            pay = (await db.execute(text("SELECT payload FROM agent_drafts WHERE id::text=:i"),
                                    {"i": str(r["draft_id"])})).scalar()
            await db.execute(text("UPDATE agent_drafts SET status='descartado' WHERE id::text=:i"),
                             {"i": str(r["draft_id"])})
            await db.commit()
        return pay

    print("\n== 1. o número nunca estoura, mesmo com nome gigante ==")
    pay = await novo_draft()
    orig = _svc.send_text_message
    async def falha(*a, **k): raise RuntimeError("WhatsApp fora do ar (simulado)")
    _svc.send_text_message = falha
    try:
        async with async_session_factory() as db:
            saida = await A._exec_pedir_cotacao(db, None, pay)
    finally:
        _svc.send_text_message = orig
    ok("NÃO saiu" in saida or "não saiu" in saida.lower(), "envio falho é RELATADO", saida[:60])

    print("\n== 2. 🎯 o registro SOBREVIVE ao envio quebrado ==")
    async with async_session_factory() as db:
        q = (await db.execute(text(
            "SELECT id::text, number, length(number), status FROM purchase_quotations "
            "ORDER BY created_at DESC LIMIT 1"))).first()
        n = (await db.execute(text(
            "SELECT count(*) FROM purchase_quotation_items WHERE quotation_id::text=:q"),
            {"q": q[0]})).scalar()
    ok(q[3] == "erro_envio", "status = erro_envio", q[3])
    ok(n == 2, "os itens ficaram", f"{n} itens")
    ok(q[2] <= 40, "número cabe na coluna", f"{q[1]} ({q[2]} chars)")
    ok(q[1].startswith("COT-"), "formato fixo, sem nome de fornecedor", q[1])
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM purchase_quotation_items WHERE quotation_id::text=:q"), {"q": q[0]})
        await db.execute(text("DELETE FROM purchase_quotations WHERE id::text=:q"), {"q": q[0]})
        await db.commit()
    print("  🧹 registro de teste removido")

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU: " + " · ".join(FALHAS)))
    if FALHAS: raise SystemExit(1)

asyncio.run(main())
