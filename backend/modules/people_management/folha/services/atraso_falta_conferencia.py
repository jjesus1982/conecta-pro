"""Conferência ponto × folha: atraso e falta justificada — PARALELO CEGO (DGX X2, 24/09/2026).

## Por que existe

O motor de folha (`calculo_service.py`) não produz os eventos `atraso` nem `falta_justificada`
(medido e registrado em `DGX_W5_mapa_evento_rubrica.md` §7). Mas o ponto MEDE atraso — a frente 04
(`ponto.mapa_de_ponto`) classifica cada turno esperado em cinco estados, e um deles é
`atendido_com_atraso`, com o horário exato da batida e a tolerância da cascata da F7 — e existe
fluxo de justificativa (`gp_justifications`, telas «Justificar falta/atraso» e «Revisar
justificativas»).

São duas perguntas de dinheiro, nos dois sentidos:

  · **atraso não descontado** — a empresa paga hora que não recebeu (`sentido='empresa_paga'`);
  · **falta justificada e ainda assim descontada** — dinheiro tirado do colaborador que não devia,
    passivo trabalhista (`sentido='passivo'`);
  · **falta justificada não descontada** — o caminho certo (`sentido='ok'`), medido para provar
    que o certo acontece, e não só para contar o errado.

## O que este módulo NÃO faz

**Não muda um centavo.** Nada aqui escreve em `hr_payslips`, em `time_sheets` ou em rubrica
nenhuma. Escreve numa tabela PRÓPRIA (`ponto_folha_conferencia`), que existe para ser lida por
gente. O oráculo `test_oraculo_x2_atraso_falta.py` prova Σ|Δ| = R$ 0,00 contra os holerites.

## A régua do atraso é IMPORTADA, não recriada

`mapa_de_ponto._carregar` / `._tolerancia` / `.classificar` — as mesmas funções que pintam o mapa
de ponto e a grade do mês. Se a régua mudar lá, muda aqui. O que este módulo acrescenta é só a
aritmética que o mapa não precisava: **quantos minutos** o `atendido_com_atraso` custou.

## Dois números de minuto, porque são duas perguntas diferentes

`minutos` = batida − início planejado (o atraso inteiro, o que o relógio viu).
`minutos_alem_tolerancia` = o que sobra depois da tolerância do turno (15 min na semente da F7).
A estimativa em R$ usa o **segundo**, o mais conservador — e a tela diz isso.

## A armadilha medida em 24/09: quem só bate na SAÍDA parece 8 h atrasado

`_janela_presenca` aceita como presença qualquer batida entre 2 h antes do início e o fim do
turno; `_primeira_batida_na_janela` pega a PRIMEIRA. Quem esqueceu a batida de entrada e só bateu
na saída entra como `atendido_com_atraso` com o turno inteiro de "atraso" — 4.563 min em 9 turnos
num caso real de 08/2026. Isso não é atraso, é batida faltando. Por isso todo turno cujo atraso
alcança `FRACAO_ENTRADA_AUSENTE` da jornada planejada é marcado `entrada_ausente`, sai da conta
de dinheiro e vai para uma coluna própria na tela. A fração é um **botão de calibragem**, não uma
verdade: o dono pode apertá-la.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text

#: Turno cujo "atraso" alcança esta fração da jornada planejada é batida de ENTRADA faltando, não
#: atraso. Calibragem, não lei — ver docstring.
FRACAO_ENTRADA_AUSENTE = Decimal("0.5")

#: Divisor mensal por escala (o mesmo de `calculo_service.DIVISOR_ESCALA`; recontado aqui de
#: propósito — importar o motor de folha para uma conferência do motor de folha é medir com a
#: própria régua que se quer conferir).
DIVISOR_ESCALA = {"12x36": 180, "44h": 220}

TIPOS = ("atraso", "falta_justificada")
SENTIDOS = ("empresa_paga", "passivo", "ok")

DDL = """
CREATE TABLE IF NOT EXISTS ponto_folha_conferencia (
  id serial PRIMARY KEY,
  competencia varchar(7) NOT NULL,
  tipo varchar(24) NOT NULL CHECK (tipo IN ('atraso','falta_justificada')),
  employee_id varchar(50) NOT NULL,
  employee_nome varchar(200) NOT NULL,
  ponto_qtd numeric(12,2) NOT NULL DEFAULT 0,
  ponto_qtd_util numeric(12,2) NOT NULL DEFAULT 0,
  ponto_qtd_descartada numeric(12,2) NOT NULL DEFAULT 0,
  unidade varchar(10) NOT NULL DEFAULT 'min',
  valor_hora numeric(12,4),
  valor_estimado numeric(12,2) NOT NULL DEFAULT 0,
  folha_qtd numeric(12,2) NOT NULL DEFAULT 0,
  folha_valor numeric(12,2) NOT NULL DEFAULT 0,
  divergente boolean NOT NULL DEFAULT false,
  sentido varchar(16) NOT NULL DEFAULT 'ok',
  observacao text,
  detalhe jsonb NOT NULL DEFAULT '[]'::jsonb,
  apurado_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_folha_conferencia
  ON ponto_folha_conferencia (competencia, tipo, employee_id);
CREATE INDEX IF NOT EXISTS ix_ponto_folha_conferencia_div
  ON ponto_folha_conferencia (competencia, tipo) WHERE divergente;
"""


async def _ensure(db) -> None:
    for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
        await db.execute(text(stmt))
    await db.commit()


def _d(v) -> Decimal:
    """O arredondamento do motor de folha (`calculo_service._d`): 2 casas, meio para cima."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def competencia_tupla(comp: str | tuple[int, int]) -> tuple[int, int]:
    """Aceita (ano, mes), 'AAAA-MM' e o formato brasileiro 'MM/AAAA'."""
    if isinstance(comp, tuple):
        return int(comp[0]), int(comp[1])
    s = str(comp).strip()
    if "/" in s:
        m, a = s.split("/", 1)
        return int(a), int(m)
    a, m = s.split("-", 1)
    return int(a), int(m)


def competencia_iso(comp) -> str:
    a, m = competencia_tupla(comp)
    if not (1 <= m <= 12) or not (2000 <= a <= 2100):
        raise ValueError(f"Competência inválida: {comp!r} — use MM/AAAA.")
    return f"{a:04d}-{m:02d}"


def _limites(ano: int, mes: int) -> tuple[date, date]:
    de = date(ano, mes, 1)
    return de, date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)


# ── valor-hora: sai do HOLERITE da pessoa, não de um chute ────────────────────────────────────

_SQL_VALOR_HORA = """
SELECT employee_id::text, base_salary, coalesce(informative->>'escala', '12x36') AS escala
  FROM hr_payslips
 WHERE source_system = 'conecta' AND payslip_code NOT LIKE '13O-%'
   AND reference_year = :a AND reference_month = :m
"""


async def valor_hora_do_holerite(db, ano: int, mes: int) -> dict[str, Decimal]:
    """{employee_id: valor-hora} = base do holerite ÷ divisor da escala do holerite.

    Sem holerite na competência não há valor-hora — e a linha fica com `valor_estimado = 0` e o
    motivo na observação. Zero por falta de dado ≠ zero por ausência de atraso.
    """
    out: dict[str, Decimal] = {}
    for eid, base, escala in (await db.execute(text(_SQL_VALOR_HORA), {"a": ano, "m": mes})).all():
        out[eid] = _d(Decimal(str(base or 0)) / Decimal(DIVISOR_ESCALA.get(escala, 220)))
    return out


# ── (a) atraso, pela régua da frente 04 ───────────────────────────────────────────────────────


async def atraso_por_pessoa(db, ano: int, mes: int) -> dict[str, dict]:
    """Minutos de atraso por pessoa no mês, pela régua do mapa de ponto (frente 04).

    Importa `_carregar`/`_tolerancia`/`classificar` — a MESMA régua da grade e do quadro ao vivo.
    """
    from modules.operacional.presence.controllers.presence_controller import _janela_turno
    from modules.people_management.ponto import mapa_de_ponto as mp

    de, ate = _limites(ano, mes)
    turnos, batidas, _geo, tol, regras = await mp._carregar(db, de, ate)
    agora = mp.agora_manaus()
    por: dict[str, dict] = {}
    for t in turnos:
        tol_min = mp._tolerancia(tol, t, regras)
        estado, bat = mp.classificar(t, batidas.get(t["employee_id"], []), tol_min, agora)
        if estado != "atendido_com_atraso" or not bat:
            continue
        dt_ini, dt_fim = _janela_turno(t["shift_date"], t["planned_start_time"], t["planned_end_time"])
        minutos = Decimal((bat["punch_timestamp"] - dt_ini).total_seconds()) / Decimal(60)
        jornada = Decimal((dt_fim - dt_ini).total_seconds()) / Decimal(60)
        entrada_ausente = jornada > 0 and minutos >= jornada * FRACAO_ENTRADA_AUSENTE
        alem = max(minutos - Decimal(tol_min), Decimal(0))
        r = por.setdefault(
            t["employee_id"],
            {
                "nome": t["nome"],
                "turnos": 0,
                "minutos": Decimal(0),
                "minutos_alem": Decimal(0),
                "minutos_descartados": Decimal(0),
                "turnos_descartados": 0,
                "tolerancia_min": tol_min,
                "detalhe": [],
            },
        )
        r["turnos"] += 1
        if entrada_ausente:
            r["turnos_descartados"] += 1
            r["minutos_descartados"] += minutos
        else:
            r["minutos"] += minutos
            r["minutos_alem"] += alem
        r["detalhe"].append(
            {
                "dia": t["shift_date"].isoformat(),
                "posto": t["posto"],
                "turno": f"{t['planned_start_time']:%H:%M}–{t['planned_end_time']:%H:%M}",
                "batida": bat["punch_timestamp"].isoformat(timespec="minutes"),
                "fonte": bat.get("fonte") or bat.get("device_type") or "app",
                "minutos": int(minutos),
                "alem_tolerancia": int(alem),
                "tolerancia_min": tol_min,
                "entrada_ausente": entrada_ausente,
            }
        )
    return por


# ── (b)/(c) falta justificada × falta descontada ──────────────────────────────────────────────

#: O que a FOLHA fez: 1051 (Faltas) e 1053 (DSR sobre Faltas) do holerite próprio da competência.
#: Os dias vêm de `time_sheets`, que é a fonte que o motor leu (`calculo_service.py` L563-607).
_SQL_FOLHA_FALTAS = """
SELECT p.employee_id::text AS employee_id, coalesce(e.nome, '?') AS nome,
       round(sum((d->>'valor')::numeric), 2) AS valor,
       coalesce(max(ts.unjustified_absent_days), 0) AS dias,
       coalesce(max(ts.dsr_lost_days), 0) AS dias_dsr
  FROM hr_payslips p
  JOIN employees e ON e.id = p.employee_id
  CROSS JOIN LATERAL jsonb_array_elements(p.deductions) d
  LEFT JOIN LATERAL (
      SELECT unjustified_absent_days, dsr_lost_days FROM time_sheets ts
       WHERE CAST(ts.employee_id AS TEXT) = p.employee_id::text
         AND ts.reference_month = :m AND ts.reference_year = :a
         AND coalesce(ts.is_deleted, false) = false
       ORDER BY ts.updated_at DESC NULLS LAST LIMIT 1) ts ON true
 WHERE p.source_system = 'conecta' AND p.payslip_code NOT LIKE '13O-%'
   AND p.reference_year = :a AND p.reference_month = :m
   AND d->>'codigo' IN ('1051', '1053')
 GROUP BY 1, 2
"""

#: O que o PONTO abonou: justificativa APROVADA. O dia justificado não tem campo próprio na
#: `gp_justifications` (medido em 24/09: a tabela guarda `punch_id` e `created_at`, nunca a data
#: do dia) — então o dia é o da batida ligada e, sem ela, o da criação. Está na observação.
_SQL_JUSTIFICATIVAS = """
SELECT j.employee_id, coalesce(e.nome, '?') AS nome, j.justification_type, j.category,
       j.reason, j.reviewed_by, j.reviewed_at, j.status,
       coalesce(cp.punch_timestamp::date, j.created_at::date) AS dia,
       (cp.punch_timestamp IS NULL) AS dia_por_criacao
  FROM gp_justifications j
  LEFT JOIN gp_clock_punches cp ON cp.punch_id = j.punch_id
  LEFT JOIN employees e ON e.id::text = j.employee_id
 WHERE lower(j.status) = 'aprovada'
   AND coalesce(cp.punch_timestamp::date, j.created_at::date) BETWEEN :de AND :ate
"""

#: Atestado/afastamento que cobre dias da competência (`sst_afastamentos`). Afastamento sem fim
#: previsto nem retorno é contado até o fim do mês — é o que ele significa hoje.
_SQL_AFASTAMENTOS = """
SELECT a.employee_id::text AS employee_id, a.employee_nome AS nome, a.tipo, a.motivo, a.cid,
       a.atestado, a.status, a.data_inicio,
       coalesce(a.data_retorno, a.data_fim_prevista, CAST(:ate AS date)) AS data_fim,
       (LEAST(coalesce(a.data_retorno, a.data_fim_prevista, CAST(:ate AS date)), CAST(:ate AS date))
        - GREATEST(a.data_inicio, CAST(:de AS date)) + 1) AS dias
  FROM sst_afastamentos a
 WHERE a.data_inicio <= CAST(:ate AS date)
   AND coalesce(a.data_retorno, a.data_fim_prevista, CAST(:ate AS date)) >= CAST(:de AS date)
"""


async def falta_justificada_por_pessoa(db, ano: int, mes: int) -> dict[str, dict]:
    """Por pessoa: o que a folha descontou de falta × o que estava abonado no ponto."""
    de, ate = _limites(ano, mes)
    por: dict[str, dict] = {}

    def _slot(eid: str, nome: str) -> dict:
        return por.setdefault(
            eid,
            {
                "nome": nome,
                "folha_dias": Decimal(0),
                "folha_valor": Decimal(0),
                "abonos": [],
            },
        )

    for r in (await db.execute(text(_SQL_FOLHA_FALTAS), {"a": ano, "m": mes})).mappings().all():
        s = _slot(r["employee_id"], r["nome"])
        s["folha_dias"] = Decimal(str(r["dias"] or 0))
        s["folha_valor"] = Decimal(str(r["valor"] or 0))
        s["folha_dias_dsr"] = Decimal(str(r["dias_dsr"] or 0))

    for r in (await db.execute(text(_SQL_JUSTIFICATIVAS), {"de": de, "ate": ate})).mappings().all():
        s = _slot(str(r["employee_id"]), r["nome"])
        s["abonos"].append(
            {
                "origem": "justificativa",
                "dia": r["dia"].isoformat(),
                "dias": 1,
                "motivo": (r["reason"] or "")[:200],
                "categoria": r["category"],
                "tipo": r["justification_type"],
                "aprovada_por": r["reviewed_by"] or "—",
                "aprovada_em": r["reviewed_at"].isoformat(timespec="minutes") if r["reviewed_at"] else None,
                "dia_por_criacao": bool(r["dia_por_criacao"]),
            }
        )

    for r in (await db.execute(text(_SQL_AFASTAMENTOS), {"de": de, "ate": ate})).mappings().all():
        if not r["atestado"]:
            continue
        s = _slot(r["employee_id"], r["nome"])
        s["abonos"].append(
            {
                "origem": "atestado",
                "dia": max(r["data_inicio"], de).isoformat(),
                "dias": int(r["dias"] or 0),
                "motivo": (r["motivo"] or r["tipo"] or "")[:200],
                "categoria": r["tipo"],
                "tipo": "afastamento",
                "aprovada_por": f"SST · CID {r['cid']}" if r["cid"] else "SST",
                "aprovada_em": None,
                "dia_por_criacao": False,
            }
        )
    return por


# ── apuração ──────────────────────────────────────────────────────────────────────────────────

_SQL_UPSERT = """
INSERT INTO ponto_folha_conferencia
  (competencia, tipo, employee_id, employee_nome, ponto_qtd, ponto_qtd_util, ponto_qtd_descartada,
   unidade, valor_hora, valor_estimado, folha_qtd, folha_valor, divergente, sentido, observacao,
   detalhe, apurado_em)
VALUES
  (:competencia, :tipo, :employee_id, :employee_nome, :ponto_qtd, :ponto_qtd_util, :ponto_qtd_descartada,
   :unidade, :valor_hora, :valor_estimado, :folha_qtd, :folha_valor, :divergente, :sentido, :observacao,
   CAST(:detalhe AS jsonb), now())
ON CONFLICT (competencia, tipo, employee_id) DO UPDATE SET
  employee_nome = EXCLUDED.employee_nome, ponto_qtd = EXCLUDED.ponto_qtd,
  ponto_qtd_util = EXCLUDED.ponto_qtd_util, ponto_qtd_descartada = EXCLUDED.ponto_qtd_descartada,
  unidade = EXCLUDED.unidade, valor_hora = EXCLUDED.valor_hora,
  valor_estimado = EXCLUDED.valor_estimado, folha_qtd = EXCLUDED.folha_qtd,
  folha_valor = EXCLUDED.folha_valor, divergente = EXCLUDED.divergente, sentido = EXCLUDED.sentido,
  observacao = EXCLUDED.observacao, detalhe = EXCLUDED.detalhe, apurado_em = now()
"""


async def apurar(db, competencia) -> dict:
    """Apura a competência e grava a tabela de conferência. **Não muda um centavo da folha.**

    Idempotente: a chave é (competência, tipo, employee_id) — apurar duas vezes reescreve as
    mesmas linhas, e quem saiu da apuração é removido (só linhas desta tabela, criada aqui).
    """
    import json

    await _ensure(db)
    comp = competencia_iso(competencia)
    ano, mes = competencia_tupla(comp)
    vh = await valor_hora_do_holerite(db, ano, mes)
    atrasos = await atraso_por_pessoa(db, ano, mes)
    faltas = await falta_justificada_por_pessoa(db, ano, mes)

    linhas: list[dict] = []
    res = {
        "competencia": comp,
        "atraso": {"pessoas": 0, "minutos": 0, "minutos_alem": 0, "minutos_descartados": 0, "valor": Decimal(0)},
        "passivo": {"pessoas": 0, "dias": 0, "valor": Decimal(0)},
        "ok": {"pessoas": 0, "dias": 0},
        "folha_faltas": {"pessoas": len(faltas), "valor": Decimal(0)},
    }

    for eid, a in atrasos.items():
        h = vh.get(eid)
        # arredonda ANTES de virar dinheiro: é `ponto_qtd_util` (numeric(12,2)) que a tela mostra
        # e o oráculo reconta. Multiplicar o número cheio e gravar o arredondado dá R$ 0,01 de
        # diferença entre o que está escrito e o que foi cobrado — medido em 24/09.
        alem = _d(a["minutos_alem"])
        valor = _d(alem / Decimal(60) * h) if h else Decimal(0)
        obs = (
            f"O motor de folha não produz o evento 'atraso' — não há rubrica de atraso em "
            f"rubricas_folha (medido em 24/09/2026). Estimativa = minutos além da tolerância de "
            f"{a['tolerancia_min']} min × valor-hora do holerite."
        )
        if h is None:
            obs += " SEM holerite próprio nesta competência: valor-hora desconhecido, R$ 0,00 por falta de dado."
        if a["turnos_descartados"]:
            obs += (
                f" {a['turnos_descartados']} turno(s) ({int(a['minutos_descartados'])} min) fora da conta: "
                f"o 'atraso' alcança {FRACAO_ENTRADA_AUSENTE:.0%} da jornada — é batida de ENTRADA faltando."
            )
        linhas.append(
            {
                "competencia": comp,
                "tipo": "atraso",
                "employee_id": eid,
                "employee_nome": a["nome"],
                "ponto_qtd": _d(a["minutos"]),
                "ponto_qtd_util": alem,
                "ponto_qtd_descartada": _d(a["minutos_descartados"]),
                "unidade": "min",
                "valor_hora": h,
                "valor_estimado": valor,
                "folha_qtd": Decimal(0),
                "folha_valor": Decimal(0),
                "divergente": alem > 0,
                "sentido": "empresa_paga" if alem > 0 else "ok",
                "observacao": obs,
                "detalhe": json.dumps(a["detalhe"], ensure_ascii=False),
            }
        )
        res["atraso"]["pessoas"] += 1
        res["atraso"]["minutos"] += int(a["minutos"])
        res["atraso"]["minutos_alem"] += int(alem)
        res["atraso"]["minutos_descartados"] += int(a["minutos_descartados"])
        res["atraso"]["valor"] += valor

    for eid, f in faltas.items():
        dias_abono = sum(int(x["dias"]) for x in f["abonos"])
        folha_dias = f["folha_dias"]
        folha_valor = f["folha_valor"]
        res["folha_faltas"]["valor"] += folha_valor
        divergente = folha_dias > 0 and dias_abono > 0
        if divergente:
            # proporcional: só os dias descontados que TÊM abono viram passivo
            cobertos = min(Decimal(dias_abono), folha_dias)
            valor = _d(folha_valor * cobertos / folha_dias) if folha_dias else Decimal(0)
            sentido = "passivo"
            obs = (
                f"{int(cobertos)} de {int(folha_dias)} dia(s) descontado(s) têm justificativa aprovada ou "
                f"atestado nesta competência. O motor desconta 1051/1053 por `time_sheets."
                f"unjustified_absent_days` e NUNCA consulta gp_justifications nem sst_afastamentos."
            )
        elif dias_abono > 0:
            valor = Decimal(0)
            sentido = "ok"
            obs = f"{dias_abono} dia(s) abonado(s) e nada descontado na folha — o caminho certo."
            res["ok"]["pessoas"] += 1
            res["ok"]["dias"] += dias_abono
        else:
            valor = Decimal(0)
            sentido = "ok"
            obs = (
                f"{int(folha_dias)} dia(s) descontado(s) sem justificativa aprovada nem atestado — "
                "desconto sem contestação conhecida."
            )
        if divergente:
            res["passivo"]["pessoas"] += 1
            res["passivo"]["dias"] += int(min(Decimal(dias_abono), folha_dias))
            res["passivo"]["valor"] += valor
        if folha_dias == 0 and dias_abono == 0:
            continue
        linhas.append(
            {
                "competencia": comp,
                "tipo": "falta_justificada",
                "employee_id": eid,
                "employee_nome": f["nome"],
                "ponto_qtd": Decimal(dias_abono),
                "ponto_qtd_util": Decimal(dias_abono),
                "ponto_qtd_descartada": Decimal(0),
                "unidade": "dia",
                "valor_hora": vh.get(eid),
                "valor_estimado": valor,
                "folha_qtd": folha_dias,
                "folha_valor": folha_valor,
                "divergente": divergente,
                "sentido": sentido,
                "observacao": obs,
                "detalhe": json.dumps(f["abonos"], ensure_ascii=False),
            }
        )

    for ln in linhas:
        await db.execute(text(_SQL_UPSERT), ln)
    vivos = [(ln["tipo"], ln["employee_id"]) for ln in linhas]
    await db.execute(
        text(
            "DELETE FROM ponto_folha_conferencia WHERE competencia = :c "
            "AND (tipo || '|' || employee_id) <> ALL(CAST(:v AS text[]))"
        ),
        {"c": comp, "v": [f"{tp}|{eid}" for tp, eid in vivos] or ["-"]},
    )
    await db.commit()
    res["linhas"] = len(linhas)
    for k in ("atraso", "passivo", "folha_faltas"):
        res[k]["valor"] = float(res[k].get("valor", 0))
    return res


async def resumo(db, competencia) -> dict:
    """Lê a última apuração da competência (sem reapurar)."""
    await _ensure(db)
    comp = competencia_iso(competencia)
    r = (
        (
            await db.execute(
                text(
                    "SELECT tipo, count(*) n, count(*) FILTER (WHERE divergente) div, "
                    "  coalesce(sum(valor_estimado),0) v, coalesce(sum(folha_valor),0) fv, "
                    "  max(apurado_em) em FROM ponto_folha_conferencia WHERE competencia = :c GROUP BY 1"
                ),
                {"c": comp},
            )
        )
        .mappings()
        .all()
    )
    return {"competencia": comp, "por_tipo": {x["tipo"]: dict(x) for x in r}}
