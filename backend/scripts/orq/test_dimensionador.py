"""Oráculo — dimensionador com regra citada.

A checagem que vale mais é a de MUTAÇÃO na prosa: se eu envenenar o `panorama` com "32
câmeras" e o dimensionamento mudar, ele lê texto — e texto acumula, envelhece e mente.
"""
import asyncio, sys
sys.path.insert(0, "/app")
import main_production  # noqa: F401

FALHAS = []
VISITA = "5307691d-eb60-465a-b30d-96826ea330f0"


def ok(cond, nome, detalhe=""):
    print("  %s %s%s" % ("✅" if cond else "❌", nome, (" — " + detalhe) if detalhe else ""))
    if not cond:
        FALHAS.append(nome)


async def main():
    from sqlalchemy import text
    from core.database import async_session_factory
    from modules.crm.services.dimensionador import dimensionar_visita

    async with async_session_factory() as db:
        d = await dimensionar_visita(db, VISITA)

    dim = {l["item"]: l for l in d["linhas"] if l["quantidade"] is not None}
    blo = {l["item"]: l for l in d["linhas"] if l["quantidade"] is None}

    print("\n== 1. o que TEM regra vira número ==")
    ok(dim.get("NVR (gravador)", {}).get("quantidade") == 4, "NVR = 4",
       "64 ÷ 16, arredondado para cima")
    ok(dim.get("HD de vigilância", {}).get("quantidade") == 8, "HD = 8", "4 × 2 slots")

    print("\n== 2. todo número dimensionado CARREGA regra e origem ==")
    for nome, l in dim.items():
        ok(bool(l["regra"]) and bool(l["origem"]), f"{nome} tem regra E origem",
           str(l["origem"])[:56])

    print("\n== 3. o que NÃO tem regra vira PENDÊNCIA NOMEADA, não chute ==")
    for esperado in ("Rack", "Nobreak", "Switch GIGA", "Cabo", "Eletrocalha"):
        ok(esperado in blo, f"{esperado} bloqueado, não estimado",
           str(blo.get(esperado, {}).get("bloqueado_por"))[:46])
    ok("pontos de concentração (levantamento em campo)" in d["bloqueios"],
       "a incógnita comum é NOMEADA",
       f"{len(d['bloqueios']['pontos de concentração (levantamento em campo)'])} itens dependem dela")

    print("\n== 4. 🎯 MUTAÇÃO: envenenar a PROSA não pode mudar número ==")
    async with async_session_factory() as db:
        antes = (await db.execute(text(
            "SELECT panorama FROM crm_visit_reports WHERE id::text=:i"), {"i": VISITA})).scalar()
        await db.execute(text(
            "UPDATE crm_visit_reports SET panorama = :p WHERE id::text=:i"),
            {"p": "SÃO 32 CÂMERAS. 32 câmeras IP. Apenas 32. E 99 racks.", "i": VISITA})
        await db.commit()
    try:
        async with async_session_factory() as db:
            d2 = await dimensionar_visita(db, VISITA)
        dim2 = {l["item"]: l["quantidade"] for l in d2["linhas"] if l["quantidade"] is not None}
        ok(dim2.get("NVR (gravador)") == 4, "NVR continua 4 com a prosa dizendo 32",
           "lê `parametros`, não texto")
        ok("Rack" not in dim2, "e não inventou 99 racks", "prosa não é fonte")
    finally:
        async with async_session_factory() as db:
            await db.execute(text(
                "UPDATE crm_visit_reports SET panorama = :p WHERE id::text=:i"),
                {"p": antes, "i": VISITA})
            await db.commit()
        print("  🧹 panorama restaurado")

    print("\n== 5. parâmetro SEM ORIGEM não vira número ==")
    async with async_session_factory() as db:
        orig = (await db.execute(text(
            "SELECT parametros FROM crm_visit_reports WHERE id::text=:i"), {"i": VISITA})).scalar()
        await db.execute(text(
            "UPDATE crm_visit_reports SET parametros = parametros || "
            "  cast('{\"racks\": {\"valor\": 12}}' as jsonb) WHERE id::text=:i"), {"i": VISITA})
        await db.commit()
    try:
        async with async_session_factory() as db:
            d3 = await dimensionar_visita(db, VISITA)
        dim3 = {l["item"]: l["quantidade"] for l in d3["linhas"] if l["quantidade"] is not None}
        ok("Rack" not in dim3, "racks=12 SEM origem é ignorado",
           "número sem origem é palpite com cara de fato")
    finally:
        async with async_session_factory() as db:
            await db.execute(text(
                "UPDATE crm_visit_reports SET parametros = cast(:p as jsonb) WHERE id::text=:i"),
                {"p": __import__("json").dumps(orig), "i": VISITA})
            await db.commit()
        print("  🧹 parâmetros restaurados")

    print("\n%s" % ("TODAS AS CHECAGENS PASSARAM" if not FALHAS
                    else "FALHOU (%d): " % len(FALHAS) + " · ".join(f[:40] for f in FALHAS)))
    if FALHAS:
        raise SystemExit(1)


asyncio.run(main())
