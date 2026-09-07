"""Oráculo — pedir_cotacao ao fornecedor.

Duas provas que o oráculo anterior desta família não deu:
  1. `import main_production` PRIMEIRO. O DONO enxergar não é o SERVIDOR enxergar.
  2. Caminho FELIZ além da recusa: o executor tem de estar registrado, senão
     aprovar na Central devolve "sem executor" e o Renier nunca recebe nada.
"""
import asyncio, sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401  — o grafo de import do servidor, não o meu

FALHAS = []
# ⭐ Todo rascunho que este oráculo cria entra aqui NA HORA em que nasce, e a limpeza roda
# no `finally`. A versão anterior limpava no caminho feliz: o teste quebrou no meio e dois
# rascunhos "ORACULO item A" ficaram na Central do Jordan apontando para o WhatsApp REAL do
# Renier. Rastro de teste que sobra num lugar onde alguém clica não é dado sujo — é mensagem
# saindo da empresa.
CRIADOS: list[str] = []


async def _limpar():
    if not CRIADOS:
        return
    from sqlalchemy import text as _tx
    from core.database import async_session_factory as _sf
    async with _sf() as db:
        await db.execute(_tx("DELETE FROM agent_drafts "
                             "WHERE id::text = ANY(:ids)"), {"ids": CRIADOS})
        await db.commit()
    print("  🧹 %d rascunho(s) de teste apagado(s)" % len(CRIADOS))

def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)

async def main():
    from sqlalchemy import text
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A

    print("\n== 1. o SERVIDOR enxerga a tool ==")
    dono = {(t.get("function") or {}).get("name") for t in A._tools_ativas(owner=True)}
    cli = {(t.get("function") or {}).get("name") for t in A._tools_ativas(owner=False)}
    ok("pedir_cotacao" in dono, "dono tem pedir_cotacao")
    ok("pedir_cotacao" not in cli, "cliente NÃO tem", "falar com fornecedor é do dono")

    print("\n== 2. o executor está registrado NESTE processo ==")
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import EXECUTORES
    fn = EXECUTORES.get("pedir_cotacao")
    ok(fn is not None, "executor de pedir_cotacao registrado",
       "sem ele, aprovar devolve 'sem executor' e a msg nunca sai")

    print("\n== 3. as recusas ==")
    # ⚠️ Cada recusa afirma o MOTIVO, não só a presença de `erro`. Contra o código
    # anterior — onde a tool não existia — um `ok("erro" in r)` passava verde, que é o
    # atalho do oráculo cúmplice: testar só o "não" prova que a porta fecha, nunca que
    # ela é a porta certa.
    r = await A._exec_manager_tool("pedir_cotacao", {"fornecedor": "NAO EXISTE SA", "itens": ["x"]}, 76)
    ok("fornecedor" in str(r.get("erro", "")).lower(), "fornecedor inexistente recusa POR ISSO",
       str(r.get("erro"))[:60])
    r = await A._exec_manager_tool("pedir_cotacao", {"fornecedor": "HAWK EYE", "itens": []}, 76)
    ok("cotar" in str(r.get("erro", "")).lower(), "lista vazia recusa POR ISSO",
       "pedido sem item é ruído para o fornecedor")

    print("\n== 3b. achar fornecedor pela PESSOA — como o Jordan fala ==")
    # 31/08 13:13: ele pediu "cotação pro Renier" e ouviu "não achei no cadastro",
    # com HAWK EYE (Renier Souza) cadastrado. A query lia contact_name para cumprimentar
    # e não para achar.
    for apelido, esperado in (("Renier", "HAWK EYE"), ("Kely", "FUTURA")):
        r = await A._exec_manager_tool("pedir_cotacao",
                                       {"fornecedor": apelido, "itens": ["ORACULO x"]}, 76)
        if r.get("draft_id"):
            CRIADOS.append(str(r["draft_id"]))
        achou = esperado.lower() in str(r.get("fornecedor", "")).lower()
        ok(achou, f"'{apelido}' resolve para {esperado}",
           str(r.get("fornecedor") or r.get("erro"))[:60])

    print("\n== 3c. ambiguidade NÃO escolhe sozinha ==")
    # termo que casa com muitos: a tool tem de devolver as opções, não eleger uma.
    r = await A._exec_manager_tool("pedir_cotacao", {"fornecedor": "a", "itens": ["ORACULO x"]}, 76)
    if r.get("draft_id"):
        CRIADOS.append(str(r["draft_id"]))
    # `"erro" in r` seria verde no código anterior pelo motivo ERRADO: 'a' casava com
    # "CEF - FGTS Digital" e a recusa vinha de falta de telefone, não de ambiguidade.
    # A asserção exige a LISTA DE OPÇÕES — é ela que prova que a tool viu mais de um.
    ok(len(r.get("opcoes") or []) > 1, "termo ambíguo devolve as OPÇÕES",
       f"{len(r.get('opcoes') or [])} opções · {str(r.get('erro'))[:44]}")
    ok(not r.get("draft_id"), "e não nasce rascunho para destino incerto")

    print("\n== 3d. não achou → conferir, NUNCA oferecer cadastro ==")
    r = await A._exec_manager_tool("pedir_cotacao",
                                   {"fornecedor": "ZZQQ INEXISTENTE", "itens": ["x"]}, 76)
    # a asserção afirma o que a instrução DIZ, não a ausência de uma palavra: procurar
    # "cadastr" casava dentro da própria proibição ("NÃO ofereça cadastrar").
    instr = str(r.get("instrucao", "")).lower()
    ok("não ofereça cadastrar" in instr, "a instrução PROÍBE cadastrar", instr[:64])
    ok(bool(r.get("fornecedores_com_whatsapp")), "devolve a lista para ele conferir",
       f"{len(r.get('fornecedores_com_whatsapp') or [])} fornecedores")

    print("\n== 4. o caminho feliz — e ele NÃO ENVIA ==")
    async with async_session_factory() as db:
        antes = (await db.execute(text(
            "SELECT count(*) FROM agent_drafts WHERE tipo='pedir_cotacao'"))).scalar()
    r = await A._exec_manager_tool("pedir_cotacao", {
        "fornecedor": "HAWK EYE", "itens": ["ORACULO — item de teste, não enviar"]}, 76)
    if r.get("draft_id"):
        CRIADOS.append(str(r["draft_id"]))          # ANTES de qualquer asserção
    ok(r.get("status") == "rascunho", "nasce rascunho", str(r.get("status")))
    ok(bool(r.get("draft_id")), "devolve o draft_id", "sem id a Central não é referenciável")
    async with async_session_factory() as db:
        row = (await db.execute(text(
            "SELECT status, gate, resumo, payload::text FROM agent_drafts WHERE id::text=:i"),
            {"i": str(r.get("draft_id"))})).first()
    ok(row is not None, "o rascunho existe no banco")
    if row:
        ok(row[0] == "rascunho", "status=rascunho (INERTE)", row[0])
        ok(row[1] == "🟡", "gate 🟡", row[1])
        ok("ORACULO" in (row[2] or ""), "o resumo carrega o TEXTO que vai sair",
           "quem aprova precisa ler a mensagem, não o nome da função")
        ok("5592" in (row[2] or ""), "o resumo NOMEIA o número de destino")

    print("\n== 5. APROVAR envia E registra — o caminho feliz COM NÚMERO ==")
    # ⚠️ o envio real fica interceptado: fornecedor de verdade não recebe mensagem de teste.
    from modules.integrations.connectors.whatsapp import service as _svc
    enviados = []
    _orig = _svc.send_text_message

    async def _fake(numero, texto, *a, **k):
        enviados.append((numero, texto))
        return {"ok": True, "interceptado": True}

    _svc.send_text_message = _fake
    try:
        r = await A._exec_manager_tool("pedir_cotacao", {
            "fornecedor": "HAWK EYE",
            "itens": ["ORACULO item A", "ORACULO item B", "ORACULO item C"]}, 76)
        did = r.get("draft_id")
        if did:
            CRIADOS.append(str(did))                # ANTES de qualquer asserção
        async with async_session_factory() as db:
            pay = (await db.execute(text(
                "SELECT payload FROM agent_drafts WHERE id::text=:i"), {"i": str(did)})).scalar()
            antes = (await db.execute(text(
                "SELECT count(*) FROM purchase_quotations WHERE status='enviada'"))).scalar()
            saida = await A._exec_pedir_cotacao(db, None, pay)
        ok(len(enviados) == 1, "aprovar ENVIA a mensagem", "1 disparo interceptado")
        ok(enviados and enviados[0][0].startswith("5592"),
           "foi para o número do fornecedor", enviados[0][0] if enviados else "-")
        async with async_session_factory() as db:
            depois = (await db.execute(text(
                "SELECT count(*) FROM purchase_quotations WHERE status='enviada'"))).scalar()
            q = (await db.execute(text(
                "SELECT id::text, number, supplier_id::text FROM purchase_quotations "
                "WHERE status='enviada' ORDER BY created_at DESC LIMIT 1"))).first()
            n = (await db.execute(text(
                "SELECT count(*) FROM purchase_quotation_items WHERE quotation_id::text=:q"),
                {"q": q[0]})).scalar() if q else 0
        ok(depois == antes + 1, "nasceu UMA cotação `enviada`", f"{antes} → {depois}")
        ok(n == 3, "os 3 itens ficaram vinculados", f"{n} itens")
        ok(bool(q and q[2]), "a cotação aponta o fornecedor", (q[1] if q else "-"))
        # limpa o rastro do oráculo
        if q:
            async with async_session_factory() as db:
                await db.execute(text(
                    "DELETE FROM purchase_quotation_items WHERE quotation_id::text=:q"), {"q": q[0]})
                await db.execute(text("DELETE FROM purchase_quotations WHERE id::text=:q"), {"q": q[0]})
                await db.commit()
    finally:
        _svc.send_text_message = _orig

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU: " + " · ".join(FALHAS)))
    if FALHAS:
        raise SystemExit(1)

async def _run():
    try:
        await main()
    finally:
        await _limpar()   # roda mesmo quando o oráculo estoura no meio


asyncio.run(_run())
