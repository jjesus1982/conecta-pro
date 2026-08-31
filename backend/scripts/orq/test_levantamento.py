"""Oráculo — entrevista + dimensionador como UMA peça.

O dimensionador nomeia a incógnita; a entrevista a resolve; a resposta volta e destrava.
As checagens que valem são as de mutação: perguntar de novo o que já foi respondido, e
item que some da lista quando destrava.
"""
import asyncio, json, sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401

FALHAS = []
V = "5307691d-eb60-465a-b30d-96826ea330f0"


def ok(c, n, d=""):
    print("  %s %s%s" % ("✅" if c else "❌", n, (" — " + d) if d else ""))
    if not c:
        FALHAS.append(n)


async def main():
    from sqlalchemy import text
    from core.database import async_session_factory
    from modules.crm.services.dimensionador import dimensionar_visita
    from modules.crm.services.levantamento import (
        placar, proxima_pergunta, registrar_resposta,
    )
    from modules.integrations.connectors.whatsapp import agent_service as A

    async with async_session_factory() as db:
        orig = (await db.execute(text(
            "SELECT parametros FROM crm_visit_reports WHERE id::text=:i"), {"i": V})).scalar()
    try:
        print("\n== 1. a fila é por VALOR DE DESTRAVE, não pela ordem da lista ==")
        async with async_session_factory() as db:
            q = await proxima_pergunta(db, V)
        ok(q["param"] == "racks", "a primeira é a que destrava mais",
           f"{len(q['destrava'])} itens: {', '.join(q['destrava'])}")
        ok(q["dono"] == "campo", "e sabe DE QUEM é a resposta", q["dono"])

        print("\n== 2. responder DESTRAVA e nenhum item some ==")
        async with async_session_factory() as db:
            antes = len((await dimensionar_visita(db, V))["linhas"])
            await registrar_resposta(db, V, "racks", 5, "ORACULO")
            await registrar_resposta(db, V, "nobreak_rack_administracao", True, "ORACULO")
            d = await dimensionar_visita(db, V)
        dim = {l["item"]: l["quantidade"] for l in d["linhas"] if l["quantidade"] is not None}
        ok(len(d["linhas"]) == antes, "a lista tem o MESMO tamanho", f"{antes} → {len(d['linhas'])}")
        ok("Switch GIGA" in {l["item"] for l in d["linhas"]},
           "Switch GIGA continua listado", "item que some é pior que item bloqueado")
        ok(dim.get("Rack") == 4, "Rack = 4", "5 pontos − 1 já existente (o da administração)")
        ok(dim.get("Nobreak") == 4, "Nobreak = 4", "5 racks − 1 que já tem nobreak")

        print("\n== 3. 🎯 NUNCA repergunta o que já foi respondido ==")
        async with async_session_factory() as db:
            q2 = await proxima_pergunta(db, V)
        ok(q2 is not None and q2["param"] not in ("racks", "nobreak_rack_administracao"),
           "a próxima é OUTRA pergunta", q2["param"] if q2 else "-")
        ok(q2["dono"] == "síndica", "e reconhece que a resposta não é do Jordan", q2["dono"])

        print("\n== 4. resposta SEM origem é recusada ==")
        async with async_session_factory() as db:
            r = await registrar_resposta(db, V, "metragem_cabo", 800, "")
        ok("erro" in r, "sem origem, não grava", str(r.get("erro"))[:50])
        async with async_session_factory() as db:
            r = await registrar_resposta(db, V, "parametro_inventado", 1, "x")
        ok("erro" in r, "parâmetro fora do questionário é recusado",
           "senão o agente inventa campo e o dimensionador nunca lê")

        print("\n== 5. a tool do DONO, e só dele ==")
        n = {(t.get("function") or {}).get("name") for t in A._tools_ativas(True)}
        c = {(t.get("function") or {}).get("name") for t in A._tools_ativas(False, "sdr")}
        ok({"levantamento_projeto", "registrar_levantamento"} <= n, "o dono tem as duas")
        ok(not (c & {"levantamento_projeto", "registrar_levantamento"}),
           "o cliente não tem nenhuma")
        r = await A._exec_manager_tool("levantamento_projeto", {"obra": "The Sun"}, 76)
        ok(r.get("proxima_pergunta") is not None, "a tool devolve UMA pergunta")
        ok(len(r.get("dimensionado") or []) >= 4, "e o que já está dimensionado",
           f"{len(r.get('dimensionado') or [])} itens com regra e origem")
        ok(all(x.get("origem") for x in r["dimensionado"]),
           "todo item dimensionado carrega ORIGEM")
    finally:
        async with async_session_factory() as db:
            await db.execute(text(
                "UPDATE crm_visit_reports SET parametros = cast(:p as jsonb) WHERE id::text=:i"),
                {"p": json.dumps(orig), "i": V})
            await db.commit()
        print("  🧹 parâmetros restaurados ao estado real")

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU (%d): " % len(FALHAS) + " · ".join(f[:38] for f in FALHAS)))
    if FALHAS:
        raise SystemExit(1)


asyncio.run(main())
