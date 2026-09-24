"""Oráculo — um plantão é UM dia trabalhado, ainda que cruze a meia-noite (DGX V1, 24/09/2026).

Por que existe: o motor de benefício da frente 03 (`beneficio_ponto._horas_por_dia`) atribuía
cada par de batidas ao dia civil da ENTRADA. No 12x36 NOTURNO com intervalo — 19:00 → 02:00 ·
03:00 → 07:00 — o plantão vira dois pares em dois dias civis, e o segundo virava um segundo dia
trabalhado. Medido no staging em 24/09: ADAILSON SERRA ALVES com 31 dias trabalhados em 08/2026
para 15 plantões; 15 pessoas de 12x36 noturna somando 226 dias a mais em 08/2026 e 142 em
09/2026. Isso é o `Trabalhado` que a conferência de benefício compara com o `Recebido` — na
entrega por apontamento viraria ajuste de +16 dias por pessoa, errado em dinheiro.

A regra que este oráculo afirma (regra, não fotografia): o dia de um turno noturno é a data de
INÍCIO (`shifts.shift_date`); toda batida entre início−tolerância e fim+tolerância pertence a
ele, nunca ao dia seguinte só por ter ocorrido depois das 00:00. Sem turno que cubra a batida
(escala não lançada, ou lançada no dia errado), vale a continuidade: par que recomeça em até
`INTERVALO_MAX_H` depois do anterior terminar, já do outro lado da meia-noite, é o mesmo plantão.

O que afirma:
  (a) fixture sintética ('FIXTURE DGX V1', apagada ao fim): pessoa 12x36 noturna com 3 plantões
      19:00–07:00 e batidas 19:00 / 02:00 / 03:00 / 07:00 do dia seguinte → Trabalhado == 3 e o
      dia seguinte de cada plantão é folga ('O'), não um segundo dia trabalhado.
  (b) ADAILSON SERRA ALVES em 08/2026: Trabalhado == nº de plantões com batida, RECONTADO por
      SQL próprio (shift_date distinto, não cancelado, com ao menos uma batida na janela do
      turno ±1h) — não pelo serviço.
  (c) paralelo cego: para todo ativo que, pelas BATIDAS, não trabalha à noite em 08 ou
      09/2026, o dia a dia de horas do motor é idêntico ao da régua anterior (par no dia da
      entrada), recomputada aqui — Σ|Δ| = 0. A correção só pode mexer em quem atravessa a
      meia-noite; quem atravessa é contado à parte, não escondido.

Estado medido no nascimento (staging, 24/09/2026, ANTES da correção): (a) Trabalhado 6 ≠ 3;
(b) 31 ≠ 15; (c) verde (o diurno nunca esteve errado). DEPOIS: (a) 3, (b) 15, (c) verde.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
  docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
    -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
    -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_v1_plantao_e_um_dia.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta

MARCA = "FIXTURE DGX V1"
FIX_ID = "11111111-d6c1-4f11-9e11-dc1000000001"
FIX_MES, FIX_ANO = 7, 2026
FIX_DIAS = (date(2026, 7, 2), date(2026, 7, 4), date(2026, 7, 6))

#: Fim da janela noturna da CLT (22:00–05:00). Batida antes disso é gente de plantão noturno.
FIM_NOITE_H = 5

SQL_PLANTOES_COM_BATIDA = """
SELECT count(*) FROM (
  SELECT s.shift_date, min(s.planned_start_time) AS ini, max(s.planned_end_time) AS fim
    FROM shifts s
   WHERE s.employee_id = CAST(:e AS uuid) AND s.shift_date BETWEEN CAST(:i AS date) AND CAST(:f AS date)
     AND lower(coalesce(s.status,'')) <> 'cancelled' AND NOT coalesce(s.is_off_day,false)
   GROUP BY s.shift_date) s
 WHERE EXISTS (SELECT 1 FROM gp_clock_punches c
                WHERE c.employee_id = CAST(:e AS uuid)
                  AND coalesce(c.status,'') <> 'facial_reprovado'
                  AND c.punch_timestamp >= (s.shift_date + s.ini - interval '1 hour')
                  AND c.punch_timestamp <= (s.shift_date
                        + CASE WHEN s.fim < s.ini THEN interval '1 day' ELSE interval '0' END
                        + s.fim + interval '1 hour'))
"""

#: Todo ativo — quem entra na conta do item (c) é decidido pelas BATIDAS, não pela escala
#: (ver `_horas_por_dia_antes`): escala e realidade discordam em gente demais aqui para a
#: escala servir de critério.
SQL_ATIVOS = """
SELECT id::text, nome FROM employees
 WHERE lower(coalesce(status,'')) = 'ativo' AND coalesce(is_homologacao,false) = false ORDER BY nome
"""


async def _horas_por_dia_antes(db, employee_id: str, ano: int, mes: int) -> tuple[dict[date, float], bool]:
    """A régua ANTERIOR, recomputada aqui: o par conta no dia civil da ENTRADA.

    Cópia deliberada do `beneficio_ponto._horas_por_dia` da árvore-base (commit d76e1df3d) —
    num oráculo a referência tem de ser independente do código medido, senão os dois erram junto.

    Devolve também se a pessoa TRABALHA A NOITE no mês — o critério de quem a correção pode
    mexer, tirado das BATIDAS e não da escala (CARLOS EDUARDO DA SILVA FAÇANHA tem `shifts`
    06:00–18:00 em 09/2026 e bate 17:47 → 05:53; ELEN XAVIER NUNES trabalha a noite inteira
    sem nenhum `shifts` lançado). Duas assinaturas, porque a meia-noite tanto pode cair DENTRO
    de um par (17:47 → 05:53) quanto no intervalo ENTRE dois (ANILSON: 18:56 → 23:08 ·
    00:09 → 06:56): par que troca de data, ou qualquer batida na madrugada (antes das 05:00,
    o fim da janela noturna da CLT). Um diurno não bate às 00:09.
    """
    from modules.people_management.ponto.services.horas_service import MAX_TURNO_H, SQL_BATIDAS, params_batidas

    p = params_batidas(employee_id, mes, ano)
    rows = (await db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})).fetchall()
    ini, fim = p["_ini_mes"], p["_fim_mes"]
    horas: dict[date, float] = {}
    noturno = any(ini <= ts < fim and ts.hour < FIM_NOITE_H for _t, ts in rows)
    i = 0
    while i < len(rows) - 1:
        entrada, saida = rows[i][1], rows[i + 1][1]
        dur = (saida - entrada).total_seconds() / 3600.0
        if not (0 < dur <= MAX_TURNO_H):
            i += 1
            continue
        i += 2
        if ini <= entrada < fim:
            horas[entrada.date()] = horas.get(entrada.date(), 0.0) + dur
            noturno = noturno or entrada.date() != saida.date()
    for _t, ts in rows:
        if ini <= ts < fim:
            horas.setdefault(ts.date(), 0.0)
    return horas, noturno


async def _semear(db) -> None:
    from sqlalchemy import text

    await _limpar(db)
    await db.execute(
        text(
            "INSERT INTO employees (id, nome, status, escala_padrao, data_admissao, is_homologacao) "
            "VALUES (CAST(:id AS uuid), :nome, 'ativo', '12x36', CAST(:adm AS date), false)"
        ),
        {"id": FIX_ID, "nome": f"{MARCA} NOTURNO", "adm": date(2026, 6, 1)},
    )
    ref = (await db.execute(text("SELECT scale_id::text, post_id::text FROM shifts LIMIT 1"))).first()
    if ref is None:
        raise RuntimeError("sandbox sem nenhum shift — não há scale_id/post_id para a fixture")
    for d in FIX_DIAS:
        await db.execute(
            text(
                "INSERT INTO shifts (id, scale_id, post_id, employee_id, status, shift_date, "
                "planned_start_time, planned_end_time, is_night_shift, notes) "
                "VALUES (gen_random_uuid(), CAST(:sc AS uuid), CAST(:po AS uuid), CAST(:e AS uuid), "
                "'scheduled', CAST(:d AS date), TIME '19:00', TIME '07:00', true, :m)"
            ),
            {"sc": ref[0], "po": ref[1], "e": FIX_ID, "d": d, "m": MARCA},
        )
        for n, (delta_d, hhmm, tipo) in enumerate(
            ((0, "19:00", "entrada"), (1, "02:00", "saida"), (1, "03:00", "entrada"), (1, "07:00", "saida"))
        ):
            ts = datetime.combine(d + timedelta(days=delta_d), datetime.strptime(hhmm, "%H:%M").time())
            await db.execute(
                text(
                    "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, "
                    "status, posto_nome) VALUES (:pid, CAST(:e AS uuid), :t, :ts, 'approved', :m)"
                ),
                {"pid": f"fixv1-{d.isoformat()}-{n}", "e": FIX_ID, "t": tipo, "ts": ts, "m": MARCA},
            )
    await db.commit()


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM gp_clock_punches WHERE posto_nome = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM shifts WHERE notes = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
    await db.commit()


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.people_management.folha.services import beneficio_ponto as bp

    falhas: list[str] = []
    resumo: list[str] = []
    async with async_session_factory() as db:
        par = await bp.parametros(db)

        # ───────── (a) fixture sintética: 3 plantões noturnos com intervalo = 3 dias ─────────
        try:
            await _semear(db)
            m = await bp.mapa_frequencia(db, FIX_ID, FIX_ANO, FIX_MES, par.horas_minimas)
            antes, _ = await _horas_por_dia_antes(db, FIX_ID, FIX_ANO, FIX_MES)
            trab = m["trabalhado"]["VT"]
            resumo.append(f"(a) fixture 3 plantões noturnos: Trabalhado {trab} (régua anterior daria {len(antes)})")
            if trab != len(FIX_DIAS):
                falhas.append(f"(a) 3 plantões com intervalo deram {trab} dias trabalhados — o plantão virou 2 dias")
            for d in FIX_DIAS:
                if m["mapa"].get(d.isoformat()) != "T":
                    falhas.append(f"(a) {d:%d/%m} é dia de plantão e o mapa diz {m['mapa'].get(d.isoformat())!r}")
                seg = (d + timedelta(days=1)).isoformat()
                if m["mapa"].get(seg) != "O":
                    falhas.append(
                        f"(a) {seg}: dia seguinte ao plantão marcado {m['mapa'].get(seg)!r} — "
                        "o segmento pós-intervalo virou um dia trabalhado à parte"
                    )
        finally:
            await _limpar(db)

        # ───────── (b) ADAILSON 08/2026 == plantões com batida, recontados por SQL ─────────
        r = (
            await db.execute(
                text("SELECT id::text, nome FROM employees WHERE nome ILIKE :n LIMIT 1"), {"n": "%ADAILSON SERRA%"}
            )
        ).first()
        if r is None:
            falhas.append("(b) ADAILSON SERRA ALVES não existe no sandbox — o caso medido sumiu")
        else:
            ini, fim = date(2026, 8, 1), date(2026, 8, 31)
            m = await bp.mapa_frequencia(db, r[0], 2026, 8, par.horas_minimas)
            plant = (await db.execute(text(SQL_PLANTOES_COM_BATIDA), {"e": r[0], "i": ini, "f": fim})).scalar() or 0
            antes = len((await _horas_por_dia_antes(db, r[0], 2026, 8))[0])
            resumo.append(
                f"(b) {r[1]} 08/2026: Trabalhado {m['trabalhado']['VT']} × plantões com batida {plant} (antes: {antes} dias)"
            )
            if m["trabalhado"]["VT"] != plant:
                falhas.append(f"(b) {r[1]} 08/2026: Trabalhado {m['trabalhado']['VT']} ≠ {plant} plantões com batida")

        # ───────── (c) paralelo cego: quem NÃO cruza a meia-noite não muda nada ─────────
        ativos = (await db.execute(text(SQL_ATIVOS))).fetchall()
        comparados = 0
        pulados = 0
        soma_delta = 0.0
        for ano, mes in ((2026, 8), (2026, 9)):
            for eid, nome in ativos:
                anterior, noturno = await _horas_por_dia_antes(db, eid, ano, mes)
                if noturno:  # é exatamente a população que a correção existe para mexer
                    pulados += 1
                    continue
                depois = await bp._horas_por_dia(db, eid, ano, mes)
                comparados += 1
                for d in sorted(set(depois) | set(anterior)):
                    if d not in depois or d not in anterior:
                        soma_delta += 1.0
                        falhas.append(
                            f"(c) {nome} {d:%d/%m/%Y}: dia apareceu/sumiu em quem não trabalha à noite — "
                            f"antes {anterior.get(d)} × depois {depois.get(d)}"
                        )
                        continue
                    dif = abs(depois[d] - anterior[d])
                    if dif > 0.0001:
                        soma_delta += dif
                        falhas.append(f"(c) {nome} {d:%d/%m/%Y}: {anterior[d]:.4f}h → {depois[d]:.4f}h")
        resumo.append(
            f"(c) pessoa×mês que não trabalham à noite: {comparados} · Σ|Δ| horas: {soma_delta:.4f} "
            f"· pessoa×mês noturnas (fora da conta, é o alvo): {pulados}"
        )
        await db.rollback()

    for lin in resumo:
        print(lin)
    for f in falhas[:40]:
        print("FALHOU:", f)
    if len(falhas) > 40:
        print(f"... e mais {len(falhas) - 40} desvio(s)")
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) — um plantão não está valendo um dia trabalhado")
    print("OK plantão é um dia: noturno com intervalo conta 1, ADAILSON bate com os plantões, diurno intacto")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
