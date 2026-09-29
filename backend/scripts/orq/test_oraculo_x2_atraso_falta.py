"""Oráculo X2 — atraso e falta justificada: o ponto mede, a folha nunca vê (24/09/2026).

## Por que existe

O motor de folha não produz `atraso` nem `falta_justificada` (`DGX_W5_mapa_evento_rubrica.md` §7).
A frente X2 mede os dois lados e grava numa tabela própria, `ponto_folha_conferencia`, **sem
mudar um centavo**. Este oráculo é a trava dos dois riscos dessa medição:

  1. que a conferência passe a MEXER na folha (o paralelo deixa de ser cego);
  2. que ela meça errado — minuto inventado ou R$ chutado vira decisão de descontar salário.

## O que afirma

(a) **Paralelo cego** — a soma dos holerites da competência é idêntica ANTES e DEPOIS de `apurar`:
    Σ|Δ| = R$ 0,00 em `total_earnings`, `total_deductions` e `net_salary`, e a contagem de verbas
    1051/1053 não muda. Nenhuma linha de `hr_payslips` é tocada.
(b) **Idempotência** — `apurar` duas vezes na mesma competência não duplica linha nenhuma
    (chave (competencia, tipo, employee_id)) e não muda os números.
(c) **Os minutos são os do ponto** — `ponto_qtd`/`ponto_qtd_util` de cada pessoa recontados aqui
    por SQL PRÓPRIO, que reimplementa a régua da frente 04 (janela de presença, primeira batida,
    geofence por haversine, tolerância) em vez de chamar o serviço. Tolerância zero: R$ 0,00 de
    folga, o minuto tem de bater.
(d) **A estimativa em R$ sai do HOLERITE** — `valor_hora` == `base_salary ÷ divisor da escala` do
    holerite próprio da pessoa, e `valor_estimado` == minutos além da tolerância × valor-hora.
    Nunca um valor-hora médio, nunca o piso da CCT genérico.
(e) **Toda falta descontada com abono aparece como divergente** — fixture: uma justificativa
    APROVADA para quem levou 1051 na competência tem de fazer a linha virar
    `divergente=true, sentido='passivo'`. A fixture é apagada ao fim, mesmo em falha.
(f) **Fiação** — o build do DP chama a frente e as três abas estão em `_dp_grupos`.

## Estado medido no nascimento (sandbox, 24/09/2026)

    09/2026 · atraso: 28 pessoas · 7.294 min contados (5.434 além da tolerância de 15 min) ≈
              R$ 698,71 + 12.986 min descartados como batida de entrada faltando
    08/2026 · atraso: 23 pessoas · 23.042 min (17.957 além da tolerância) ≈ R$ 2.378,86
              + 7.459 min descartados. Descontado na folha nas duas competências: R$ 0,00
              (não existe rubrica de atraso em `rubricas_folha`)
    09/2026 · faltas descontadas: 19 pessoas em 1051 (R$ 2.575,28) + 12 em 1053 (R$ 2.018,58)
    09/2026 · justificativas APROVADAS: 0 (as 13 do banco estão todas `pendente`, desde 21/07)
              afastamentos com atestado na competência: 2, nenhum descontado · passivo: R$ 0,00
    08/2026 · faltas descontadas: R$ 0,00 — a trava de cobertura de `calculo_service` segurou

## Como roda

    WT=$(git rev-parse --show-toplevel)
    ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
           | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x2_atraso_falta.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

MARCA = "FIXTURE DGX X2"
DESVIOS: list[str] = []


def falhou(msg: str) -> None:
    DESVIOS.append(msg)
    print(f"FALHOU: {msg}")


def _r(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── a régua da frente 04, reimplementada em SQL (não é o serviço quem responde) ───────────────
#
# Janela de presença: [início − 2h, fim] no diurno; [início − 2h, D+1 07:00] quando o início é
# >= 15:00 (`presence_controller.HORA_CORTE_NOTURNO`). Primeira batida válida da janela decide.
# Batida que caiu no geofence de OUTRO posto é `atendido_posto_incorreto`, não atraso — por isso
# o haversine está aqui (mesma fórmula de `punch_service._haversine`, r=6.371.000 m).
_DIST = (
    "6371000 * 2 * asin(sqrt(0.5 - cos((geo.la - b.latitude) * pi()/180)/2 "
    "+ cos(b.latitude * pi()/180) * cos(geo.la * pi()/180) "
    "* (1 - cos((geo.lo - b.longitude) * pi()/180))/2))"
)

SQL_ATRASO = """
WITH postos_geo AS (
  SELECT id::text AS pid, latitude AS la, longitude AS lo,
         coalesce(geofence_raio_metros, 150)::double precision AS raio
    FROM posts WHERE is_active AND latitude IS NOT NULL AND longitude IS NOT NULL),
turnos AS (
  -- ⭐ 29/09/2026 — ESTE ORÁCULO OBSERVAVA A COISA ERRADA, e por isso reprovou uma tela boa.
  -- A verdade do horário não é `shifts` cru: quando existe linha em `ponto_horario_vigencia` na
  -- data, ela é o horário que vale — foi escrita à mão, com AUTOR e MOTIVO, porque o cadastro
  -- estava errado. A CELIANE tem cadastro 08:00 e entra 09:00; medindo pelo cru, este oráculo
  -- via 241 minutos de atraso que não existem (4 dias × 60) e acusava a conferência de errar.
  -- ⚠️ Não é copiar a query do código: é expressar a REGRA do domínio (o corrigido manda) de
  -- forma independente. A régua mudou porque estava errada, não para o teste passar.
  SELECT sh.id::text AS sid, sh.shift_date AS d,
         coalesce((SELECT hv.entrada FROM ponto_horario_vigencia hv
                    WHERE hv.employee_id = sh.employee_id
                      AND hv.vigencia_inicio <= sh.shift_date
                      AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date)
                    ORDER BY hv.vigencia_inicio DESC LIMIT 1),
                  sh.planned_start_time) AS ini,
         coalesce((SELECT hv.saida FROM ponto_horario_vigencia hv
                    WHERE hv.employee_id = sh.employee_id
                      AND hv.vigencia_inicio <= sh.shift_date
                      AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date)
                    ORDER BY hv.vigencia_inicio DESC LIMIT 1),
                  sh.planned_end_time) AS fim,
         sh.actual_start_time AS ast,
         sh.post_id::text AS pid, sh.employee_id::text AS eid, e.nome
    FROM shifts sh JOIN employees e ON e.id = sh.employee_id JOIN posts p ON p.id = sh.post_id
   WHERE sh.shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
     AND {esperado} AND {coorte} {nao_ausente}),
t AS (
  SELECT *, (d + ini) AS dt_ini,
         CASE WHEN (d + fim) <= (d + ini) THEN (d + interval '1 day' + fim) ELSE (d + fim) END AS dt_fim
    FROM turnos),
w AS (
  SELECT *, dt_ini - interval '2 hours' AS j_ini,
         CASE WHEN ini >= time '15:00' THEN (d + interval '1 day' + time '07:00') ELSE dt_fim END AS j_fim
    FROM t),
prim AS (
  SELECT w.*, cp.punch_timestamp AS ts, cp.dentro_geofence, cp.posto_id, cp.latitude, cp.longitude,
         row_number() OVER (PARTITION BY w.sid ORDER BY cp.punch_timestamp) AS rn
    FROM w JOIN gp_clock_punches cp ON cp.employee_id::text = w.eid
         AND cp.punch_timestamp >= w.j_ini AND cp.punch_timestamp <= w.j_fim
         AND coalesce(cp.status, '') <> 'facial_reprovado'
         AND cp.employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao, false) = true)),
com_geo AS (
  SELECT b.*, CASE WHEN b.dentro_geofence IS TRUE AND b.posto_id IS NOT NULL THEN b.posto_id::text
    ELSE (SELECT geo.pid FROM postos_geo geo
           WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL AND {dist} <= geo.raio
           ORDER BY {dist} LIMIT 1) END AS posto_geofence
    FROM prim b WHERE b.rn = 1),
-- sem batida na janela, o check-in MANUAL (`shifts.actual_start_time`) vale como presença — é o
-- que `classificar` faz, e é o que o quadro ao vivo mostra. Sem isso o SQL some com o turno.
decisao AS (
  SELECT w.eid, w.nome, w.pid, w.dt_ini, w.dt_fim,
         coalesce(cg.ts, w.ast) AS ts,
         CASE WHEN cg.ts IS NOT NULL THEN cg.posto_geofence END AS posto_geofence
    FROM w LEFT JOIN com_geo cg ON cg.sid = w.sid
   WHERE coalesce(cg.ts, w.ast) IS NOT NULL),
atrasados AS (
  SELECT eid, nome,
         (EXTRACT(EPOCH FROM (ts - dt_ini))/60)::double precision AS minutos,
         (EXTRACT(EPOCH FROM (dt_fim - dt_ini))/60)::double precision AS jornada
    FROM decisao
   WHERE (posto_geofence IS NULL OR posto_geofence = pid)
     AND ts > dt_ini + (CAST(:tol AS int) * interval '1 minute'))
SELECT eid, nome,
       sum(minutos) FILTER (WHERE minutos < jornada * CAST(:frac AS double precision)) AS min_contados,
       sum(GREATEST(minutos - CAST(:tol AS double precision), 0))
         FILTER (WHERE minutos < jornada * CAST(:frac AS double precision)) AS min_alem,
       sum(minutos) FILTER (WHERE minutos >= jornada * CAST(:frac AS double precision)) AS min_descartados
  FROM atrasados GROUP BY 1, 2
"""

SQL_TOTAIS_FOLHA = """
SELECT count(*), coalesce(sum(total_earnings),0), coalesce(sum(total_deductions),0),
       coalesce(sum(net_salary),0),
       coalesce((SELECT count(*) FROM hr_payslips q, jsonb_array_elements(q.deductions) d
                  WHERE q.reference_year = :a AND q.reference_month = :m
                    AND d->>'codigo' IN ('1051','1053')), 0),
       coalesce((SELECT round(sum((d->>'valor')::numeric),2) FROM hr_payslips q,
                       jsonb_array_elements(q.deductions) d
                  WHERE q.reference_year = :a AND q.reference_month = :m
                    AND d->>'codigo' IN ('1051','1053')), 0)
  FROM hr_payslips WHERE reference_year = :a AND reference_month = :m
"""

SQL_VALOR_HORA = """
SELECT employee_id::text, round(base_salary / CASE WHEN coalesce(informative->>'escala','12x36') = '12x36'
       THEN 180 ELSE 220 END, 2) AS vh
  FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND reference_year = :a AND reference_month = :m
"""

SQL_COMPS = """
SELECT DISTINCT reference_year, reference_month FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus')
 ORDER BY 1 DESC, 2 DESC LIMIT 2
"""


async def _limpar_fixture(db) -> None:
    await db.execute(text("DELETE FROM gp_justifications WHERE reason LIKE :m"), {"m": f"%{MARCA}%"})
    await db.commit()


async def main() -> int:
    from modules.operacional.presence.controllers.presence_controller import _SHIFT_ESPERADO
    from modules.people_management.folha.services import atraso_falta_conferencia as afc
    from modules.people_management.ponto.mapa_de_ponto import COORTE, nao_ausente_em

    async with async_session_factory() as db:
        await afc._ensure(db)

        # A régua do SQL abaixo usa UMA tolerância (a da linha `empresa` da F7). Se alguém criar
        # linha por escopo ou tolerância de geofence, esta reconta deixa de ser fiel — e o oráculo
        # tem de gritar antes de mentir verde.
        escopadas = (
            await db.execute(text("SELECT count(*) FROM ponto_configuracoes WHERE escopo <> 'empresa' AND aplicado"))
        ).scalar()
        geo_tol = (
            await db.execute(
                text(
                    "SELECT count(*) FROM geofence_zones WHERE post_id IS NOT NULL "
                    "AND coalesce(is_active, true) AND entry_tolerance_minutes IS NOT NULL"
                )
            )
        ).scalar()
        tol_empresa = (
            await db.execute(
                text(
                    "SELECT tolerancia_entrada_min FROM ponto_configuracoes "
                    "WHERE escopo = 'empresa' AND aplicado ORDER BY id DESC LIMIT 1"
                )
            )
        ).scalar() or 15
        if escopadas or geo_tol:
            falhou(
                f"a tolerância ganhou escopo ({escopadas} linha(s) em ponto_configuracoes, {geo_tol} em "
                "geofence_zones) — o SQL deste oráculo reconta com UMA tolerância e precisa acompanhar a cascata"
            )

        comps = [(int(a), int(m)) for a, m in (await db.execute(text(SQL_COMPS))).all()]
        if not comps:
            falhou("nenhuma competência do motor próprio em hr_payslips")
            return 1

        sql_atraso = SQL_ATRASO.format(
            esperado=_SHIFT_ESPERADO, coorte=COORTE, nao_ausente=nao_ausente_em("sh.shift_date"), dist=_DIST
        )
        resumo_linhas: list[str] = []

        for ano, mes in comps:
            comp = f"{ano:04d}-{mes:02d}"
            de, ate = afc._limites(ano, mes)

            antes = (await db.execute(text(SQL_TOTAIS_FOLHA), {"a": ano, "m": mes})).first()
            r1 = await afc.apurar(db, comp)
            n1 = (
                await db.execute(
                    text("SELECT count(*) FROM ponto_folha_conferencia WHERE competencia = :c"), {"c": comp}
                )
            ).scalar()
            r2 = await afc.apurar(db, comp)  # (b) idempotência
            n2 = (
                await db.execute(
                    text("SELECT count(*) FROM ponto_folha_conferencia WHERE competencia = :c"), {"c": comp}
                )
            ).scalar()
            depois = (await db.execute(text(SQL_TOTAIS_FOLHA), {"a": ano, "m": mes})).first()

            # (a) paralelo cego
            deltas = [abs(_r(antes[i]) - _r(depois[i])) for i in (1, 2, 3, 5)]
            if sum(deltas) != 0 or antes[0] != depois[0] or antes[4] != depois[4]:
                falhou(f"{comp}: apurar MEXEU na folha — Σ|Δ| = R$ {sum(deltas)} (paralelo deixou de ser cego)")
            # (b)
            if n1 != n2 or r1["linhas"] != r2["linhas"]:
                falhou(
                    f"{comp}: apurar 2× duplicou/perdeu linha ({n1} → {n2}, serviço {r1['linhas']} → {r2['linhas']})"
                )

            # (c) minutos recontados por SQL próprio
            recont = {
                r[0]: (Decimal(str(r[2] or 0)), Decimal(str(r[3] or 0)), Decimal(str(r[4] or 0)))
                for r in (
                    await db.execute(
                        text(sql_atraso),
                        {"de": de, "ate": ate, "tol": int(tol_empresa), "frac": float(afc.FRACAO_ENTRADA_AUSENTE)},
                    )
                ).all()
            }
            gravado = {
                r[0]: (r[1], _r(r[2]), _r(r[3]), _r(r[4]), r[5], _r(r[6]))
                for r in (
                    await db.execute(
                        text(
                            "SELECT employee_id, employee_nome, ponto_qtd, ponto_qtd_util, ponto_qtd_descartada, "
                            "valor_hora, valor_estimado FROM ponto_folha_conferencia "
                            "WHERE competencia = :c AND tipo = 'atraso'"
                        ),
                        {"c": comp},
                    )
                ).all()
            }
            so_sql = set(recont) - set(gravado)
            so_serv = set(gravado) - set(recont)
            for eid in sorted(so_sql):
                falhou(f"{comp}: o SQL vê atraso de {eid} e a conferência não gravou linha")
            for eid in sorted(so_serv):
                falhou(f"{comp}: a conferência gravou atraso de {gravado[eid][0]} e o SQL não vê nenhum")
            for eid in sorted(set(recont) & set(gravado)):
                sq, gv = recont[eid], gravado[eid]
                for i, rot in ((0, "minutos"), (1, "minutos além da tolerância"), (2, "minutos descartados")):
                    if _r(sq[i]) != gv[i + 1]:
                        falhou(f"{comp}: {gv[0]} — {rot}: SQL {_r(sq[i])} × conferência {gv[i + 1]}")

            # (d) o R$ sai do holerite
            vh = {r[0]: _r(r[1]) for r in (await db.execute(text(SQL_VALOR_HORA), {"a": ano, "m": mes})).all()}
            for eid, gv in gravado.items():
                esperado_vh = vh.get(eid)
                if esperado_vh is None:
                    if gv[4] is not None:
                        falhou(f"{comp}: {gv[0]} não tem holerite próprio e mesmo assim ganhou valor-hora {gv[4]}")
                    if gv[5] != 0:
                        falhou(f"{comp}: {gv[0]} sem holerite e com R$ {gv[5]} estimado — chute")
                    continue
                if _r(gv[4]) != esperado_vh:
                    falhou(f"{comp}: {gv[0]} valor-hora {gv[4]} ≠ holerite {esperado_vh} (base ÷ divisor da escala)")
                esperado_rs = _r(gv[2] / Decimal(60) * esperado_vh)
                if gv[5] != esperado_rs:
                    falhou(f"{comp}: {gv[0]} R$ {gv[5]} ≠ {esperado_rs} (min além da tolerância × valor-hora)")

            resumo_linhas.append(
                f"{mes:02d}/{ano}: atraso {r1['atraso']['pessoas']} pessoa(s) · {r1['atraso']['minutos']} min "
                f"({r1['atraso']['minutos_alem']} além da tolerância, {r1['atraso']['minutos_descartados']} "
                f"descartados) ≈ R$ {r1['atraso']['valor']:.2f} · faltas descontadas R$ "
                f"{r1['folha_faltas']['valor']:.2f} · passivo (descontado COM abono) R$ {r1['passivo']['valor']:.2f} "
                f"em {r1['passivo']['pessoas']} pessoa(s) · abonado e não descontado: {r1['ok']['pessoas']} pessoa(s)"
            )

        # (e) fixture: falta descontada COM justificativa aprovada tem de virar divergência
        ano, mes = comps[0]
        comp = f"{ano:04d}-{mes:02d}"
        de, _ate = afc._limites(ano, mes)
        alvo = (
            await db.execute(
                text(
                    "SELECT p.employee_id::text FROM hr_payslips p, jsonb_array_elements(p.deductions) d "
                    "WHERE p.source_system = 'conecta' AND p.reference_year = :a AND p.reference_month = :m "
                    "AND d->>'codigo' = '1051' LIMIT 1"
                ),
                {"a": ano, "m": mes},
            )
        ).scalar()
        try:
            if alvo:
                await db.execute(
                    text(
                        "INSERT INTO gp_justifications (justification_id, employee_id, justification_type, reason, "
                        "category, status, reviewed_by, reviewed_at, created_at) VALUES "
                        "(:jid, :e, 'falta', :r, 'saude', 'aprovada', 'oraculo-x2', :dt, :dt)"
                    ),
                    {"jid": str(uuid.uuid4()), "e": alvo, "r": f"{MARCA} — falta abonada", "dt": de},
                )
                await db.commit()
                await afc.apurar(db, comp)
                linha = (
                    await db.execute(
                        text(
                            "SELECT divergente, sentido, valor_estimado FROM ponto_folha_conferencia "
                            "WHERE competencia = :c AND tipo = 'falta_justificada' AND employee_id = :e"
                        ),
                        {"c": comp, "e": alvo},
                    )
                ).first()
                if not linha:
                    falhou(f"fixture: {alvo} tem 1051 e justificativa APROVADA e não virou linha de conferência")
                elif not linha[0] or linha[1] != "passivo":
                    falhou(
                        f"fixture: falta descontada COM justificativa aprovada saiu divergente={linha[0]} "
                        f"sentido={linha[1]} — devia ser divergente/passivo"
                    )
                elif _r(linha[2]) <= 0:
                    falhou("fixture: divergência de passivo com R$ 0,00 estimado")
            else:
                falhou(f"{comp}: nenhuma falta 1051 no motor próprio — a fixture (e) não pôde ser montada")
        finally:
            await _limpar_fixture(db)
            await afc.apurar(db, comp)  # volta ao estado medido
            resto = (
                await db.execute(
                    text("SELECT count(*) FROM gp_justifications WHERE reason LIKE :m"), {"m": f"%{MARCA}%"}
                )
            ).scalar()
            if resto:
                falhou(f"fixture não foi apagada: {resto} linha(s) '{MARCA}' em gp_justifications")

        # (f) fiação
        raiz = Path(__file__).resolve().parents[1].parent / "modules/operacional/controllers/redesign_builders"
        dp = (raiz / "departamento_pessoal.py").read_text(encoding="utf-8")
        if "_dgx_x2_atraso_falta" not in dp:
            falhou("departamento_pessoal.py não chama a frente X2 — tela sem porta")
        grupos = (raiz / "_dp_grupos.py").read_text(encoding="utf-8")
        for tela in ("atraso-conferencia", "falta-justificada-conferencia", "ponto-folha-apurar"):
            if f'"{tela}"' not in grupos:
                falhou(f"a aba '{tela}' não está em _dp_grupos.py — tela sem porta")

        for ln in resumo_linhas:
            print(ln)
        print(f"TOTAL desvios: {len(DESVIOS)}")
        if not DESVIOS:
            print(
                "OK conferência atraso/falta: paralelo cego (Σ|Δ| = R$ 0,00 nos holerites), apurar 2× não duplica, "
                "minutos == régua da frente 04 recontada por SQL, R$ do valor-hora do holerite, falta descontada "
                "com abono vira divergência"
            )
        return 1 if DESVIOS else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
