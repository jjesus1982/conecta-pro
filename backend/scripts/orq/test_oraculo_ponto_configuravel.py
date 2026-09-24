"""Oráculo — ponto CONFIGURÁVEL por escopo, feriados com escopo, ausências e cartão em lote
(DGX F7, 24/09/2026).

Por que existe: a tolerância (15 min) e o raio (150 m) do ponto eram constantes em três arquivos
(`coorte_ponto`, `presence_controller`, `mapa_de_ponto`). A DGX aplica configuração por pessoa /
contrato / vaga / função / escala. Trocar constante por tabela é o jeito clássico de mudar o
comportamento sem querer — este oráculo afirma que, com a semente, NADA muda, e que a cascata
faz o que promete.

O que afirma:
  a. `config_ponto()` sem linha específica devolve exatamente 15 / 150 (a semente = o código).
  b. Linha de COLABORADOR vence a de POSTO; a de posto vence a empresa (fixture 'FIXTURE DGX F7',
     apagada ao fim, mesmo em falha).
  c. `mapa_do_dia` do último dia fechado produz os MESMOS estados que a régua com as constantes
     antigas (15 min, raio 150) — recomputado aqui com `classificar`/`posto_do_geofence` puras,
     sem passar pelo resolvedor.
  d. Feriado com escopo=cliente aparece para o seu condomínio e NÃO aparece para outro nem para
     "todos" (fixture apagada ao fim).
  e. Dashboard de ausências: `lancados` == count(shifts) do mês por SQL próprio; Σ planejados
     por cliente == planejados; planejados == trabalhados + faltas + pendentes; a tela carrega
     o mesmo número em `_meta`.
  f. Cartão em lote de 3 pessoas com espelho calculado gera UM PDF com 3+ páginas.

Estado medido no nascimento (staging, 24/09/2026): `config_ponto` não existia → ImportError →
VERMELHO. `cct_feriados` sem `escopo`; `ponto_configuracoes` inexistente.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import io
import sys
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

FIX = "FIXTURE DGX F7"

_SQL_ULTIMO_DIA_COM_BATIDA = """
SELECT max(punch_timestamp::date) FROM gp_clock_punches
 WHERE punch_timestamp::date < CAST(:dia AS date) AND coalesce(status,'') <> 'facial_reprovado'
"""
_SQL_LANCADOS = """
SELECT count(*) FROM shifts WHERE shift_date >= CAST(:de AS date) AND shift_date < CAST(:ate AS date)
   AND employee_id IS NOT NULL AND is_off_day = FALSE AND status <> 'cancelled' AND is_active = TRUE
"""


async def _limpar(db):
    await db.execute(text("DELETE FROM ponto_configuracoes WHERE origem_regra = :f"), {"f": FIX})
    await db.execute(text("DELETE FROM cct_feriados WHERE observacao = :f"), {"f": FIX})
    await db.commit()


async def main() -> int:
    from core.database import async_session_factory
    from modules.people_management.ponto import ausencias as aus
    from modules.people_management.ponto import cartao_lote
    from modules.people_management.ponto import config_ponto as cfg
    from modules.people_management.ponto import mapa_de_ponto as regua

    falhas: list[str] = []
    async with async_session_factory() as db:
        await cfg._ensure(db)
        await _limpar(db)

        # ── a) sem linha específica: 15 / 150 ───────────────────────────────────────────
        c = await cfg.config_ponto(db)
        if (c["tolerancia_entrada_min"], c["raio_metros"]) != (15, 150):
            falhas.append(
                f"(a) empresa sem regra específica devolveu {c['tolerancia_entrada_min']}/{c['raio_metros']}, esperado 15/150"
            )
        emp_qq = (
            await db.execute(
                text(
                    "SELECT id::text FROM employees WHERE lower(status)='ativo' AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 1"
                )
            )
        ).scalar()
        c2 = await cfg.config_ponto(db, employee_id=emp_qq)
        if (c2["tolerancia_entrada_min"], c2["raio_metros"]) != (15, 150):
            falhas.append(
                f"(a) colaborador sem regra devolveu {c2['tolerancia_entrada_min']}/{c2['raio_metros']}, esperado 15/150"
            )
        n_semente = (
            await db.execute(text("SELECT count(*) FROM ponto_configuracoes WHERE escopo='empresa' AND aplicado"))
        ).scalar()
        if n_semente != 1:
            falhas.append(f"(a) esperava 1 linha-semente de empresa aplicada, há {n_semente}")

        # ── b) colaborador > posto > empresa (fixture) ──────────────────────────────────
        posto = (await db.execute(text("SELECT id::text FROM posts WHERE is_active ORDER BY name LIMIT 1"))).scalar()
        emp_a, emp_b = [
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT id::text FROM employees WHERE lower(status)='ativo' AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 2"
                    )
                )
            ).all()
        ]
        await db.execute(
            text(
                "INSERT INTO ponto_configuracoes (escopo, escopo_id, tolerancia_entrada_min, raio_metros, origem_regra) VALUES "
                "('posto', :p, 20, 200, :f), ('colaborador', :e, 25, NULL, :f)"
            ),
            {"p": posto, "e": emp_a, "f": FIX},
        )
        await db.commit()
        try:
            cp = await cfg.config_ponto(db, post_id=posto)
            if (cp["tolerancia_entrada_min"], cp["raio_metros"]) != (20, 200):
                falhas.append(
                    f"(b) posto com regra devolveu {cp['tolerancia_entrada_min']}/{cp['raio_metros']}, esperado 20/200"
                )
            ce = await cfg.config_ponto(db, employee_id=emp_a, post_id=posto)
            if ce["tolerancia_entrada_min"] != 25:
                falhas.append(
                    f"(b) colaborador com regra devolveu tolerância {ce['tolerancia_entrada_min']}, esperado 25 (colaborador vence posto)"
                )
            if ce["raio_metros"] != 200:
                falhas.append(
                    f"(b) colaborador sem raio próprio devolveu {ce['raio_metros']}, esperado 200 (herda do posto)"
                )
            if not ce["origem"]["tolerancia_entrada_min"].startswith("colaborador:"):
                falhas.append(
                    f"(b) origem da tolerância = {ce['origem']['tolerancia_entrada_min']!r}, esperado colaborador:…"
                )
            cb = await cfg.config_ponto(db, employee_id=emp_b, post_id=posto)
            if cb["tolerancia_entrada_min"] != 20:
                falhas.append(
                    f"(b) outro colaborador no mesmo posto devolveu {cb['tolerancia_entrada_min']}, esperado 20 (regra do posto)"
                )
        finally:
            await _limpar(db)

        # ── c) mapa do último dia fechado == régua com as constantes antigas ──────────
        hoje = regua.agora_manaus().date()
        fechado = (await db.execute(text(_SQL_ULTIMO_DIA_COM_BATIDA), {"dia": hoje})).scalar() or (
            hoje - timedelta(days=1)
        )
        depois = datetime.combine(fechado + timedelta(days=1), time(12, 0))
        m = await regua.mapa_do_dia(db, dia=fechado, agora=depois)
        por_shift = {i["shift_id"]: i["estado"] for i in m["itens"]}
        turnos, batidas, geo, tol, _regras = await regua._carregar(db, fechado, fechado)
        geo_150 = [{k: v for k, v in p.items() if k != "raio_padrao"} for p in geo]  # sem cascata → 150
        bat_const: dict[str, list[dict]] = {}
        for eid, bs in batidas.items():
            for b0 in bs:
                b1 = dict(b0)
                b1["posto_geofence"], b1["dist_geofence"] = regua.posto_do_geofence(b1, geo_150)
                bat_const.setdefault(eid, []).append(b1)
        medidos = 0
        for t in turnos:
            tol_const = tol.get(t["post_id"], 15)
            esperado, _b = regua.classificar(t, bat_const.get(t["employee_id"], []), tol_const, depois)
            medidos += esperado is not None
            if por_shift.get(t["shift_id"], "∅") != esperado:
                falhas.append(
                    f"(c) [{fechado:%d/%m}] {t['nome']} ({t['posto']} {t['planned_start_time']:%H:%M}): "
                    f"resolvedor diz {por_shift.get(t['shift_id'])!r}, constante diz {esperado!r}"
                )
        if m["tolerancia_padrao_min"] != 15:
            falhas.append(f"(c) tolerância padrão do mapa = {m['tolerancia_padrao_min']}, esperado 15")
        if not medidos:
            falhas.append(f"(c) nada medido: o dia fechado {fechado:%d/%m} não tem turno com estado")

        # ── d) feriado de CLIENTE vale só para o seu condomínio ────────────────────────
        cond_a, cond_b = [
            r[0]
            for r in (
                await db.execute(text("SELECT id::text FROM condominios WHERE ativo ORDER BY nome LIMIT 2"))
            ).all()
        ]
        conv = (
            await db.execute(text("SELECT id FROM cct_convencoes ORDER BY is_vigente DESC NULLS LAST LIMIT 1"))
        ).scalar()
        d_fix = date(hoje.year, 3, 14)  # data neutra: não coincide com nenhum feriado cadastrado
        await db.execute(
            text(
                "INSERT INTO cct_feriados (id, convencao_id, data_feriado, nome, tipo, ano, is_active, escopo, condominio_id, observacao) "
                "VALUES (gen_random_uuid(), :conv, :d, :n, 'cliente', :ano, true, 'cliente', CAST(:c AS uuid), :f)"
            ),
            {"conv": conv, "d": d_fix, "n": FIX, "ano": d_fix.year, "c": cond_a, "f": FIX},
        )
        await db.commit()
        try:
            fa = [f["nome"] for f in await cfg.feriados_do_dia(db, d_fix, cond_a)]
            fb = [f["nome"] for f in await cfg.feriados_do_dia(db, d_fix, cond_b)]
            fn = [f["nome"] for f in await cfg.feriados_do_dia(db, d_fix, None)]
            if FIX not in fa:
                falhas.append("(d) feriado de cliente NÃO apareceu para o próprio condomínio")
            if FIX in fb:
                falhas.append("(d) feriado de cliente apareceu para OUTRO condomínio")
            if FIX in fn:
                falhas.append("(d) feriado de cliente apareceu na leitura sem condomínio (todos)")
            natal = await cfg.feriados_do_dia(db, date(hoje.year, 12, 25), cond_b)
            if not any(f["escopo"] == "nacional" for f in natal):
                falhas.append("(d) 25/12 nacional não apareceu para o condomínio B")
            n_escopo = (
                await db.execute(
                    text("SELECT count(*) FROM cct_feriados WHERE tipo IN ('estadual','municipal') AND escopo <> tipo")
                )
            ).scalar()
            if n_escopo:
                falhas.append(
                    f"(d) {n_escopo} feriado(s) estadual/municipal ainda com escopo ≠ tipo (semente não correu)"
                )
        finally:
            await _limpar(db)

        # ── e) ausências: bruto por SQL próprio e soma fecha ───────────────────────────
        ano, mes = hoje.year, hoje.month
        a = await aus.ausencias_do_mes(db, ano, mes)
        de = date(ano, mes, 1)
        ate = date(ano + (mes == 12), mes % 12 + 1, 1)
        lanc_sql = (await db.execute(text(_SQL_LANCADOS), {"de": de, "ate": ate})).scalar()
        if a["lancados"] != lanc_sql:
            falhas.append(f"(e) dashboard diz {a['lancados']} turnos lançados; SQL próprio conta {lanc_sql}")
        soma = sum(c["planejados"] for c in a["por_cliente"].values())
        if soma != a["planejados"]:
            falhas.append(f"(e) Σ planejados por cliente = {soma} ≠ planejados {a['planejados']}")
        for cli, c in a["por_cliente"].items():
            if c["planejados"] != c["trabalhados"] + c["faltas"] + c["pendentes"]:
                falhas.append(
                    f"(e) {cli}: planejados {c['planejados']} ≠ trabalhados {c['trabalhados']} + faltas {c['faltas']} + pendentes {c['pendentes']}"
                )
        if not a["planejados"]:
            falhas.append(f"(e) nada medido: {mes:02d}/{ano} sem turno cobrado")
        # o controller primeiro: é ele quem descobre os builders; importar o builder antes dele
        # fecha o ciclo (departamento_pessoal → _dgx_f7_ponto.router) e a tela "falha" só aqui.
        import modules.operacional.controllers.redesign_data_controller  # noqa: F401
        from modules.operacional.controllers.redesign_builders import _dgx_f7_ponto as f7

        telas = await f7.telas(db, {})
        meta = (telas.get("ausencias-dashboard") or {}).get("_meta") or {}
        if meta.get("lancados") != a["lancados"]:
            falhas.append(f"(e) tela carrega lancados={meta.get('lancados')} e o serviço diz {a['lancados']}")
        for tid in ("ponto-configuracoes", "relogios-ponto", "feriados", "cartao-ponto-lote", "ausencias-dashboard"):
            if "FALHOU" in str((telas.get(tid) or {}).get("title", "FALHOU")):
                falhas.append(f"(e) tela {tid} não montou: {(telas.get(tid) or {}).get('sub')}")

        # ── f) cartão em lote: 3 pessoas → 3+ páginas ───────────────────────────────────
        comp = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM time_sheets WHERE coalesce(is_deleted,false)=false "
                    "GROUP BY 1,2 ORDER BY count(*) DESC, 1 DESC, 2 DESC LIMIT 1"
                )
            )
        ).first()
        ids = [
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT DISTINCT employee_id FROM time_sheets WHERE coalesce(is_deleted,false)=false AND reference_year=:a AND reference_month=:m "
                        "ORDER BY 1 LIMIT 3"
                    ),
                    {"a": comp[0], "m": comp[1]},
                )
            ).all()
        ]
    if len(ids) < 3:
        falhas.append(f"(f) staging não tem 3 espelhos calculados em {comp[1]:02d}/{comp[0]} — nada medido")
    else:
        from PyPDF2 import PdfReader

        from core.database.session import SyncSessionLocal

        with SyncSessionLocal() as s:
            pdf, relato = cartao_lote.montar_cartao_lote(s, comp[1], comp[0], ids)
        paginas = len(PdfReader(io.BytesIO(pdf)).pages) if pdf else 0
        com = sum(1 for r in relato if "paginas" in r)
        if com != 3 or paginas < 3:
            falhas.append(
                f"(f) lote de 3 pessoas em {comp[1]:02d}/{comp[0]}: {com} espelho(s), {paginas} página(s) — esperado 3 e ≥ 3"
            )
        print(f"cartão em lote {comp[1]:02d}/{comp[0]}: {com} espelhos · {paginas} páginas · {len(pdf or b'')} bytes")

    print(
        f"config: empresa 15/150 · fixture posto 20/200, colaborador 25 · mapa {fechado:%d/%m}: {medidos} turno(s) comparados"
    )
    print(
        f"ausências {mes:02d}/{ano}: {a['lancados']} lançados · {a['planejados']} cobrados · {len(a['por_cliente'])} cliente(s)"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no ponto configurável")
    print(
        "OK ponto configurável: semente = código, cascata resolve, feriado de cliente fica no cliente, ausências fecham, lote concatena"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
