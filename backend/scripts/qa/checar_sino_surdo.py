#!/usr/bin/env python3
"""Origem do sino que NINGUÉM lê: alarme que toca sempre é alarme que virou papel de parede.

Medido em 06/09/2026, 30 dias de `communication_notifications`:

    proativo          2.650 enviados ·  12 lidos
    shift             1.582          · 441
    oraculos_diarios    100          ·   0
    trava_qa             72          ·   0
    ─────────────────────────────────────────
    total             5.387 · o dono do sistema abriu 19

Foi assim que os 3 agentes do GEDEON passaram 3 dias mortos "à vista de todos": o aviso
estava lá, no meio de 2.650 outros. A regra da casa ("limpar o ruído vale mais que qualquer
conserto isolado") não tinha trava. Esta é a trava: por ORIGEM, quantos foram enviados e
quantos alguém abriu. Origem com volume e leitura ≈ zero é SURDA — ou o destinatário está
errado, ou o conteúdo não merece o sino, ou o sino não é o canal. Qualquer das três é
decisão de produto; o que a trava faz é impedir que fique invisível.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_sino_surdo.py
        --instalar            instala o gatilho de corte (sql/sino_corte.sql) — uma vez
        --cortar <origem>     corta agora (decisão humana)
        --religar <origem>    volta a entregar
        --cortadas            lista o que está cortado

E ELE DECIDE, por regra (pedido do Jordan em 06/09/2026: "que ele faça também"): origem
surda em DIAS_PARA_CORTE medições consecutivas é cortada sozinha, com UM aviso no sino
dizendo o que cortou e como religar. Nunca corta as origens do próprio arsenal nem o
digest (o digest é o lugar para onde a informação continua indo). A memória da surdez
fica em system_configs (`qa.sino_surdez`); o corte, em `sino.origens_cortadas`, lido por
um gatilho BEFORE INSERT — um lugar só, todos os produtores obedecem sem mexer em nenhum.

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> origem(ns) surda(s)`.
Surda = ≥ 30 envios em 30 dias e menos de 2% lidos. Exit 1 quando há alguma NÃO cortada.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

MIN_ENVIOS = 30
TAXA_MINIMA = 0.02
DIAS_PARA_CORTE = 14
PROTEGIDAS = {"oraculos_diarios", "trava_qa", "vigia_oraculos", "task_falha", "sino_corte",
              "proativo_digest", "digest_central"}
CHAVE_CORTE = "sino.origens_cortadas"
CHAVE_SURDEZ = "qa.sino_surdez"
SQL_TRIGGER = pathlib.Path(__file__).resolve().parent / "sql" / "sino_corte.sql"


async def _cfg(db, chave: str):
    from sqlalchemy import text  # noqa: PLC0415
    bruto = (await db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"), {"c": chave})).scalar()
    try:
        return json.loads(bruto) if bruto else None
    except json.JSONDecodeError:
        return None


async def _gravar_cfg(db, chave: str, valor, descricao: str) -> None:
    from sqlalchemy import text  # noqa: PLC0415
    await db.execute(text("""
        INSERT INTO system_configs (id, chave, valor, descricao, grupo)
        VALUES (gen_random_uuid(), :c, :v, :d, 'sino')
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()"""),
        {"c": chave, "v": json.dumps(valor), "d": descricao})
    await db.commit()


async def _trigger_instalado(db) -> bool:
    from sqlalchemy import text  # noqa: PLC0415
    return bool((await db.execute(text(
        "SELECT 1 FROM pg_trigger WHERE tgname = 'sino_corte_bi' AND NOT tgisinternal"))).scalar())


async def _instalar(db) -> None:
    from sqlalchemy import text  # noqa: PLC0415
    sql = SQL_TRIGGER.read_text()
    # três statements; o corpo da função tem ';' dentro — separar pelo fim do $$ e pelas linhas
    partes = [sql.split("$$;")[0] + "$$;"] + [p.strip() + ";" for p in sql.split("$$;")[1].split(";") if p.strip()]
    for stmt in partes:
        await db.execute(text(stmt))
    await db.commit()


def _avisar(titulo: str, corpo: str) -> None:
    try:
        from modules.notifications.tasks_oraculos import avisar  # noqa: PLC0415
        avisar(titulo, corpo, chave="sino_corte")
    except Exception as exc:  # noqa: BLE001
        print(f"  (não consegui avisar no sino: {exc})")


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        cortadas: list[str] = await _cfg(db, CHAVE_CORTE) or []
        if "--instalar" in sys.argv:
            await _instalar(db)
            print("gatilho sino_corte_bi instalado" if await _trigger_instalado(db) else "FALHOU: gatilho não apareceu")
            return 0
        if "--cortadas" in sys.argv:
            print("cortadas:", cortadas or "(nenhuma)")
            return 0
        for flag, acao in (("--cortar", "cortar"), ("--religar", "religar")):
            if flag in sys.argv:
                origem = sys.argv[sys.argv.index(flag) + 1]
                if acao == "cortar" and origem in PROTEGIDAS:
                    print(f"RECUSO: {origem} é protegida (arsenal/digest)")
                    return 2
                novas = sorted((set(cortadas) | {origem}) if acao == "cortar" else (set(cortadas) - {origem}))
                await _gravar_cfg(db, CHAVE_CORTE, novas, "Origens do sino cortadas (gatilho sino_corte_bi)")
                print(f"{acao}: {origem} → cortadas agora: {novas or '(nenhuma)'}")
                return 0
        if not await _trigger_instalado(db):
            print("AVISO: gatilho sino_corte_bi NÃO instalado — cortes não têm efeito. Rode --instalar.\n")
        origens = (await db.execute(text("""
            SELECT coalesce(extra_data->>'origem', reference_type, '?') AS origem,
                   count(*) AS enviados, count(read_at) AS lidos,
                   count(DISTINCT user_id) AS destinatarios, max(read_at)::date AS ultima_leitura
            FROM communication_notifications
            WHERE created_at > now() - interval '30 days'
            GROUP BY 1 ORDER BY 2 DESC"""))).all()
        pessoas = (await db.execute(text("""
            SELECT u.email, count(*) AS recebidos, count(n.read_at) AS lidos
            FROM communication_notifications n JOIN users u ON u.id = n.user_id
            WHERE n.created_at > now() - interval '30 days'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""))).all()

        # memória da surdez: dias consecutivos por origem (zera quando deixa de ser surda)
        surdez: dict[str, int] = await _cfg(db, CHAVE_SURDEZ) or {}
        surdas_hoje = {r.origem for r in origens
                       if r.enviados >= MIN_ENVIOS and (r.lidos / r.enviados) < TAXA_MINIMA}
        surdez = {o: (surdez.get(o, 0) + 1) for o in surdas_hoje}
        cortar_agora = sorted(o for o, d in surdez.items()
                              if d >= DIAS_PARA_CORTE and o not in PROTEGIDAS and o not in cortadas)
        await _gravar_cfg(db, CHAVE_SURDEZ, surdez, "Dias consecutivos de surdez por origem (checar_sino_surdo)")
        if cortar_agora and "--sem-cortar" not in sys.argv:
            novas = sorted(set(cortadas) | set(cortar_agora))
            await _gravar_cfg(db, CHAVE_CORTE, novas, "Origens do sino cortadas (gatilho sino_corte_bi)")
            cortadas = novas
            detalhe = "; ".join(f"{o} ({surdez[o]} dias surda)" for o in cortar_agora)
            _avisar(f"Sino: cortei {len(cortar_agora)} origem(ns) que ninguém abria",
                    f"{detalhe}. Volume sem leitura afunda o aviso que importa. Religar: "
                    f"checar_sino_surdo.py --religar <origem>")
            print(f"  CORTEI: {detalhe}")

    total = sum(r.enviados for r in origens)
    print(f"sino nos últimos 30 dias: {total} enviados, {sum(r.lidos for r in origens)} lidos\n")
    print(f"{'origem':<24}{'enviados':>9}{'lidos':>7}{'taxa':>7}{'dest.':>6}  última leitura")
    surdas = []
    for r in origens:
        taxa = r.lidos / r.enviados if r.enviados else 0
        surda = r.enviados >= MIN_ENVIOS and taxa < TAXA_MINIMA and r.origem not in cortadas
        if surda:
            surdas.append(r.origem)
        marca = "c " if r.origem in cortadas else ("x " if surda else "  ")
        dias = f"  surda há {surdez[r.origem]}d" if r.origem in surdez else ""
        print(f"{marca}{r.origem:<22}{r.enviados:>9}{r.lidos:>7}{taxa:>7.0%}{r.destinatarios:>6}  {r.ultima_leitura or '—'}{dias}")
    print("\nquem recebe (30 dias):")
    for p in pessoas:
        print(f"   {p.email:<44}{p.recebidos:>6} recebidos · {p.lidos:>4} lidos")
    if cortadas:
        print(f"\ncortadas (gatilho): {cortadas}")
    print(f"\nTOTAL: {len(surdas)} origem(ns) surda(s)")
    if surdas:
        print(f"Surda = volume e ninguém abre. Com {DIAS_PARA_CORTE} medições seguidas, corta sozinha "
              f"(menos arsenal e digest). Agora: --cortar <origem>.")
    return 1 if surdas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
