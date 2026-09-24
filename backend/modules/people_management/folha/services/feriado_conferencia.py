"""Feriado trabalhado e HE 100% — a conferência que diz quanto a CCT manda pagar (DGX X3).

24/09/2026. A W5 (§7) mediu o buraco: o motor de folha produz 8 dos 15 eventos do ponto, e entre
os que faltam estão `feriado_trabalhado` e `he100`. A rubrica **`0011 Hora Extra 100%` existe em
`rubricas_folha` desde 03/2026 e nunca foi emitida** — em nenhuma competência, por ninguém. Os
feriados são dado com ESCOPO desde a F7 (`cct_feriados`: nacional | estadual | municipal |
cliente). Faltava o cruzamento: **quem trabalhou em feriado e o que recebeu por isso**.

Este serviço é esse cruzamento, numa tabela PRÓPRIA (`folha_feriado_conferencia`).
**Paralelo cego: nada aqui muda um centavo de holerite.** `calculo_service.py` não foi tocado —
só lido. Quem prova é `scripts/orq/test_oraculo_x3_feriado_he100.py` (Σ|Δ| nos holerites = R$ 0,00).

A regra que a conferência aplica — e de onde ela vem
────────────────────────────────────────────────────
· **Feriado trabalhado não compensado se paga em DOBRO** — art. 9º da Lei 605/49 e Súmula 146 do
  TST. Para o 12x36, que é a escala de 42 dos 63 ativos, a Súmula **444 do TST** é expressa:
  a jornada 12x36 é válida «assegurada a remuneração em dobro dos feriados trabalhados».
  O dia já está pago uma vez dentro do salário mensal (verba 0001); o que falta é a SEGUNDA vez.
  Por isso `pago_como = horas × valor_hora` e `deveria_ser = horas × valor_hora × 2`.
· **Hora extra em feriado/domingo/dia de descanso é 100%** — CCT SINDECOMPRESTS AM000613/2025,
  vigência 01/01/2026–31/12/2026 (`cct_convencoes`), que no sistema vive como
  `cct_cargos.horas_extras_noturnas_percentual = 100,00` (nas 51 funções da convenção) e como
  `modules/cct/models/schedule.ADICIONAIS.hora_extra_feriado_percentual = 100,0`. Quem classifica
  o dia é o espelho de ponto (`hr/services/espelho_service.py` L551-553: no 12x36, 100% só em
  feriado; no 44h, feriado, domingo ou dia sem jornada esperada).
  ⚠️ A CCT em si não está digitalizada neste repositório — o número da cláusula não existe em
  lugar nenhum do código. A `origem_regra` cita a CONVENÇÃO e o campo onde o percentual vive,
  que é o mais longe que dá para ir sem inventar. §7 do relatório.

Escopo do feriado: **importado da F7**, nunca recriado — `config_ponto.feriados_do_periodo`.
Feriado de CLIENTE vale só para o condomínio dele; estadual/municipal, só para o condomínio da
mesma UF/cidade. Pareamento das batidas: as PRIMITIVAS do `horas_service` (`dia_do_plantao`,
`janelas_de_turno`, `MAX_TURNO_H`, `SQL_BATIDAS`) — a régua do «um plantão é UM dia», importada.

Sem sobreposição: o dia de feriado sai como `feriado_trabalhado` (dobra sobre o plantão INTEIRO)
e nunca também como `he100` — pagar as duas seria contar a mesma hora duas vezes.

DDL idempotente em `_ensure(db)` (padrão da casa; `alembic/versions/` é zona proibida).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text

from modules.operacional.services import vinculo_cliente  # dgx y4 — o resolvedor único do vínculo
from modules.people_management.ponto.config_ponto import feriados_do_periodo
from modules.people_management.ponto.he_classificacao import competencia_valida

#: Divisor mensal por escala — cópia FIEL de `calculo_service.DIVISOR_ESCALA` (o oráculo reconta
#: o valor-hora por SQL próprio; se o motor mudar o divisor, a diferença aparece lá).
DIVISOR_ESCALA = {"12x36": 180, "44h": 220}

#: A verba que PAGARIA feriado trabalhado / HE 100%. Existe em `rubricas_folha` e nunca foi
#: emitida (medido em 24/09/2026: zero ocorrências em todos os holerites de 2026).
RUBRICA_100 = "0011"
#: O que o motor emite como HE 50% — 0040 no motor próprio, 0070 no backfill do espelho da Portte,
#: 0010 no cadastro de rubricas. É o que, no máximo, chegou à pessoa pelas horas de HE do mês.
CODIGOS_HE50 = ("0010", "0040", "0070")
#: Todos os códigos que a conferência LÊ do holerite (o oráculo confere linha a linha contra eles).
CODIGOS_PAGAM_FERIADO = (RUBRICA_100, *CODIGOS_HE50)

TIPOS = {
    "feriado_trabalhado": "Feriado trabalhado",
    "he100": "Hora extra que deveria ser 100%",
}

REGRA_FERIADO = (
    "Feriado trabalhado não compensado = pagamento em DOBRO (art. 9º da Lei 605/49; Súmula 146 do "
    "TST; para o 12x36, Súmula 444 do TST, que assegura a remuneração em dobro dos feriados "
    "trabalhados). O dia já está pago uma vez no salário mensal (0001) — falta a segunda."
)
REGRA_HE100 = (
    "Hora extra em feriado/domingo/dia de descanso = 100% — CCT SINDECOMPRESTS AM000613/2025 "
    "(cct_cargos.horas_extras_noturnas_percentual = 100,00; modules/cct/models/schedule."
    "ADICIONAIS.hora_extra_feriado_percentual = 100,0). O dia é classificado pelo espelho "
    "(espelho_service.py L551-553). A folha emitiu, no máximo, HE 50% (verba 0040/0070)."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS folha_feriado_conferencia (
  id serial PRIMARY KEY,
  competencia varchar(7) NOT NULL,
  tipo varchar(24) NOT NULL CHECK (tipo IN ('feriado_trabalhado','he100')),
  employee_id varchar(50) NOT NULL,
  nome varchar(180) NOT NULL DEFAULT '',
  cargo varchar(120), escala varchar(20), condominio varchar(180),
  data date NOT NULL,
  feriado varchar(160), escopo varchar(20),
  teve_turno boolean NOT NULL DEFAULT false,
  horas numeric(6,2) NOT NULL DEFAULT 0,
  valor_hora numeric(12,2) NOT NULL DEFAULT 0,
  pago_como numeric(12,2) NOT NULL DEFAULT 0,
  pago_detalhe text,
  verbas jsonb NOT NULL DEFAULT '{}'::jsonb,
  deveria_ser numeric(12,2) NOT NULL DEFAULT 0,
  diferenca numeric(12,2) NOT NULL DEFAULT 0,
  regra text NOT NULL DEFAULT '',
  apurado_em timestamptz NOT NULL DEFAULT now())""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_folha_feriado_conf "
    "ON folha_feriado_conferencia (competencia, tipo, employee_id, data)",
    "CREATE INDEX IF NOT EXISTS ix_folha_feriado_conf_comp ON folha_feriado_conferencia (competencia)",
]

#: As duas linhas que faltavam no mapa evento→rubrica da W5 — a DECLARAÇÃO do que a CCT manda,
#: não do que o motor faz. Nascem com «o motor usa? NÃO» (a W5 já marca `produzido=False` nos dois)
#: e a tela diz isso em voz alta. `WHERE NOT EXISTS` no escopo empresa: o que o dono editar depois
#: nunca é sobrescrito. (evento, rubrica, fórmula, base, percentual, origem_regra)
SEMENTE_MAPA: list[tuple[str, str, str, str, str, str]] = [
    (
        "feriado_trabalhado",
        "0011",
        "horas × valor_hora × 2",
        "valor_hora",
        "2.0000",
        "DGX X3 24/09/2026 — DECLARAÇÃO (o motor NÃO emite): feriado trabalhado não compensado se "
        "paga em dobro — art. 9º da Lei 605/49, Súmula 146 do TST e, para o 12x36, Súmula 444 do "
        "TST («assegurada a remuneração em dobro dos feriados trabalhados»). O dia já está pago "
        "uma vez no salário mensal (0001): a verba devida é a SEGUNDA vez. Feriado e escopo em "
        "cct_feriados (DGX F7); conferência em folha_feriado_conferencia.",
    ),
    (
        "he100",
        "0011",
        "horas × valor_hora × 2",
        "valor_hora",
        "2.0000",
        "DGX X3 24/09/2026 — DECLARAÇÃO (o motor NÃO emite; hoje sai 0040 a 1,5 ou não sai): hora "
        "extra em feriado/domingo/dia de descanso a 100% — CCT SINDECOMPRESTS AM000613/2025 "
        "(cct_convencoes.registro_mte), percentual em cct_cargos.horas_extras_noturnas_percentual "
        "= 100,00 nas 51 funções e em modules/cct/models/schedule.ADICIONAIS."
        "hora_extra_feriado_percentual = 100,0. Classificação do dia: espelho_service.py L551-553.",
    ),
]

_SQL_SEMENTE_MAPA = """
INSERT INTO ponto_evento_rubrica
  (evento, rubrica_codigo, escopo, escopo_id, formula, base, percentual, origem_regra, criado_por)
SELECT :evento, :rubrica, 'empresa', '', :formula, :base, CAST(:percentual AS numeric), :origem, 'dgx-x3'
 WHERE NOT EXISTS (SELECT 1 FROM ponto_evento_rubrica WHERE evento = CAST(:evento AS varchar) AND escopo = 'empresa')
"""

_ENSURED = False


async def _ensure(db) -> None:
    global _ENSURED  # noqa: PLW0603 — uma vez por processo, como `config_ponto._ensure`
    if _ENSURED:
        return
    for stmt in DDL:
        await db.execute(text(stmt))
    # o cadastro da W5 precisa existir antes de ganhar as duas linhas novas
    from modules.people_management.folha.services.mapa_evento_rubrica import _ensure as _ensure_mapa

    await _ensure_mapa(db)
    for evento, rubrica, formula, base, pct, origem in SEMENTE_MAPA:
        await db.execute(
            text(_SQL_SEMENTE_MAPA),
            {
                "evento": evento,
                "rubrica": rubrica,
                "formula": formula,
                "base": base,
                "percentual": pct,
                "origem": origem,
            },
        )
    await db.commit()
    _ENSURED = True


def _d(v) -> Decimal:
    """O arredondamento do motor (`calculo_service._d`): 2 casas, meio para cima."""
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ───────────────────────────────── leituras ─────────────────────────────────
#: Quem pode entrar na conferência: todo empregado com batida na competência. O condomínio sai
#: DGX Y4 (24/09/2026): o condomínio saía daqui por `condominios.client_id = e.cliente_id` e
#: resolvia **0 das 61 pessoas** com batida em 09/2026 — `employees.cliente_id` é campo morto
#: (órfão em 37 dos 63 ativos, nulo em 14). Enquanto foi assim, **feriado de CLIENTE não alcançava
#: ninguém**: `config_ponto.SQL_FERIADOS` exige `f.condominio_id = :cond` para o escopo `cliente`.
#: O condomínio agora vem do resolvedor único (`operacional/services/vinculo_cliente.py`), pela
#: alocação vigente na competência — 0 → 46 pessoas. Só ACRESCENTA: ninguém tinha condomínio antes,
#: e nenhum dos condomínios resolvidos tem UF/cidade que exclua um feriado que hoje se aplica
#: (o oráculo `y4_vinculo_cliente` afirma isso, item (f) — feriado é dinheiro).
_SQL_PESSOAS = """
SELECT e.id::text AS employee_id, coalesce(e.nome,'?') AS nome, e.cargo,
       coalesce(e.escala_padrao,'44h') AS escala,
       coalesce(e.salario_base, 0) AS salario_cadastro
  FROM employees e
 WHERE EXISTS (SELECT 1 FROM gp_clock_punches p
                WHERE p.employee_id = e.id
                  AND p.punch_timestamp >= CAST(:de AS date) - 1
                  AND p.punch_timestamp < CAST(:ate AS date) + 2)
 ORDER BY nome
"""

#: A base salarial que o motor usou na competência (pós-piso da CCT) e as verbas que pagariam
#: feriado/HE. Uma linha por pessoa; as verbas vêm agregadas por código.
_SQL_HOLERITE = """
SELECT p.employee_id::text, coalesce(p.base_salary, 0) AS base,
       coalesce(jsonb_object_agg(v.cod, v.val) FILTER (WHERE v.cod IS NOT NULL), '{}'::jsonb) AS verbas
  FROM hr_payslips p
  LEFT JOIN LATERAL (
      SELECT x->>'codigo' AS cod, round(sum((x->>'valor')::numeric), 2) AS val
        FROM jsonb_array_elements(coalesce(p.earnings,'[]'::jsonb)) x
       WHERE x->>'codigo' = ANY(CAST(:cods AS text[]))
       GROUP BY 1) v ON true
 WHERE p.reference_year = :a AND p.reference_month = :m AND coalesce(p.status,'') <> 'cancelled'
 GROUP BY 1, 2
"""

#: Os dias que o espelho classificou como HE 100% (a régua do `espelho_service`), e o total de
#: HE do mês da pessoa — que é o rateio honesto do que a folha pagou por hora de HE.
_SQL_ESPELHO_HE = """
SELECT ts.employee_id::text,
       (x->>'date')::date AS dia,
       round(coalesce((x->>'overtime')::numeric,0) / 60.0, 2) AS horas,
       CASE WHEN (x->>'overtime_type') = '100' THEN '100' ELSE '50' END AS tp
  FROM time_sheets ts, jsonb_array_elements(coalesce(ts.daily_summary,'[]'::jsonb)) x
 WHERE coalesce(ts.is_deleted,false) = false
   AND ts.reference_year = :a AND ts.reference_month = :m
   AND coalesce((x->>'overtime')::numeric,0) > 0
"""

#: Quem tinha turno lançado no dia (a coluna «tinha escala?» da tela).
_SQL_TURNOS = """
SELECT employee_id::text, shift_date FROM shifts
 WHERE shift_date BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
   AND lower(coalesce(status,'')) <> 'cancelled' AND NOT coalesce(is_off_day, false)
"""

_SQL_UPSERT = """
INSERT INTO folha_feriado_conferencia
  (competencia, tipo, employee_id, nome, cargo, escala, condominio, data, feriado, escopo, teve_turno,
   horas, valor_hora, pago_como, pago_detalhe, verbas, deveria_ser, diferenca, regra, apurado_em)
VALUES
  (:competencia, :tipo, :employee_id, :nome, :cargo, :escala, :condominio, :data, :feriado, :escopo,
   :teve_turno, :horas, :valor_hora, :pago_como, :pago_detalhe, CAST(:verbas AS jsonb), :deveria_ser,
   :diferenca, :regra, now())
ON CONFLICT (competencia, tipo, employee_id, data) DO UPDATE SET
  nome = EXCLUDED.nome, cargo = EXCLUDED.cargo, escala = EXCLUDED.escala, condominio = EXCLUDED.condominio,
  feriado = EXCLUDED.feriado, escopo = EXCLUDED.escopo, teve_turno = EXCLUDED.teve_turno,
  horas = EXCLUDED.horas, valor_hora = EXCLUDED.valor_hora, pago_como = EXCLUDED.pago_como,
  pago_detalhe = EXCLUDED.pago_detalhe, verbas = EXCLUDED.verbas, deveria_ser = EXCLUDED.deveria_ser,
  diferenca = EXCLUDED.diferenca, regra = EXCLUDED.regra, apurado_em = now()
"""


def _brl(v) -> str:
    return f"R$ {Decimal(str(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _horas_por_dia(db, employee_id: str, ano: int, mes: int) -> dict[date, float]:
    """{dia do plantão: horas} — pareia as batidas do mês com as primitivas do `horas_service`.

    Importa a RÉGUA (`dia_do_plantao`, `janelas_de_turno`, `MAX_TURNO_H`, `SQL_BATIDAS`), não a
    copia: o dia de um par é o do TURNO, não o da entrada, e o segmento pós-intervalo do 12x36
    noturno (19:00 → 02:00 · 03:00 → 07:00) é do plantão da véspera.

    Diferença deliberada para `beneficio_ponto._horas_por_dia`: a batida SEM PAR também entra na
    corrente de continuidade (`ultimo`). Lá isso não importa — o VT/VR conta dia com horas. Aqui
    importa: a batida solitária vira uma linha de «trabalhou no feriado», e sem a continuidade a
    saída das 07:10 do plantão que entrou 18:45 da véspera inventaria um feriado trabalhado.
    Dia com batida e sem par nasce com **0h** e a tela diz «sem par de batidas» — presença
    registrada com hora desconhecida não é ausência.
    """
    from modules.people_management.ponto.services.horas_service import (
        MAX_TURNO_H,
        SQL_BATIDAS,
        SQL_TURNOS_JANELA,
        dia_do_plantao,
        janelas_de_turno,
        params_batidas,
        params_turnos,
    )

    p = params_batidas(str(employee_id), mes, ano)
    rows = (await db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})).fetchall()
    janelas = janelas_de_turno((await db.execute(SQL_TURNOS_JANELA, params_turnos(p))).fetchall())
    ini, fim = p["_ini_mes"].date(), p["_fim_mes"].date()
    horas: dict[date, float] = {}
    ultimo: tuple | None = None
    i = 0
    while i < len(rows):
        if i + 1 < len(rows):
            entrada, saida = rows[i][1], rows[i + 1][1]
            dur = (saida - entrada).total_seconds() / 3600.0
            if 0 < dur <= MAX_TURNO_H:
                dia = dia_do_plantao(entrada, janelas, ultimo)
                ultimo = (saida, dia)
                if ini <= dia < fim:
                    horas[dia] = horas.get(dia, 0.0) + dur
                i += 2
                continue
        ts = rows[i][1]
        dia = dia_do_plantao(ts, janelas, ultimo)
        ultimo = (ts, dia)
        if ini <= dia < fim:
            horas.setdefault(dia, 0.0)
        i += 1
    return horas


def _mes_bounds(ano: int, mes: int) -> tuple[date, date]:
    de = date(ano, mes, 1)
    ate = date(ano + (mes == 12), (mes % 12) + 1, 1)
    return de, date.fromordinal(ate.toordinal() - 1)


async def apurar(db, competencia: str) -> dict[str, Any]:
    """Cruza feriados (escopo da F7) × turnos × batidas × holerite da competência.

    Idempotente por (competência, tipo, pessoa, dia): rodar de novo atualiza a linha, nunca
    duplica. **Não escreve em `hr_payslips` nem em nada da folha** — só na tabela desta frente.
    """
    ano, mes = competencia_valida(competencia)
    await _ensure(db)
    comp = f"{ano:04d}-{mes:02d}"
    de, ate = _mes_bounds(ano, mes)

    pessoas = [dict(r) for r in (await db.execute(text(_SQL_PESSOAS), {"de": de, "ate": ate})).mappings().all()]
    # dgx y4 — o condomínio de cada um pela alocação vigente NO FIM DA COMPETÊNCIA (não hoje):
    # quem mudou de posto em outubro não reescreve o feriado de setembro.
    vinc = await vinculo_cliente.mapa_cliente(db, [p["employee_id"] for p in pessoas], ref=ate)
    for p in pessoas:
        v = vinc.get(p["employee_id"]) or {}
        p["condominio_id"] = v.get("condominio_id")
        p["condominio"] = v.get("condominio_nome") or "—"

    hol: dict[str, dict[str, Any]] = {
        str(r[0]): {"base": Decimal(str(r[1] or 0)), "verbas": dict(r[2] or {})}
        for r in (
            await db.execute(text(_SQL_HOLERITE), {"a": ano, "m": mes, "cods": list(CODIGOS_PAGAM_FERIADO)})
        ).all()
    }

    he_dias: dict[str, list[tuple[date, Decimal, str]]] = {}
    for emp, dia, horas, tp in (await db.execute(text(_SQL_ESPELHO_HE), {"a": ano, "m": mes})).all():
        he_dias.setdefault(str(emp), []).append((dia, Decimal(str(horas or 0)), tp))

    turnos: set[tuple[str, date]] = {
        (str(e), d) for e, d in (await db.execute(text(_SQL_TURNOS), {"de": de, "ate": ate})).all()
    }

    # feriados: uma leitura por condomínio distinto (≤ nº de clientes), com a régua de escopo da F7
    cache_fer: dict[str | None, dict[date, list[dict]]] = {}

    params: list[dict[str, Any]] = []
    for p in pessoas:
        eid = p["employee_id"]
        cond = p["condominio_id"]
        if cond not in cache_fer:
            cache_fer[cond] = await feriados_do_periodo(db, de, ate, cond)
        feriados = cache_fer[cond]
        if not feriados and eid not in he_dias:
            continue

        h = hol.get(eid, {})
        base = h.get("base") or Decimal(str(p["salario_cadastro"] or 0))
        divisor = DIVISOR_ESCALA.get(p["escala"], 220)
        valor_hora = _d(base / Decimal(divisor)) if base else Decimal("0")
        verbas: dict[str, Decimal] = {k: Decimal(str(v)) for k, v in (h.get("verbas") or {}).items()}
        pago_100 = verbas.get(RUBRICA_100, Decimal("0"))
        pago_he50 = sum((verbas.get(c, Decimal("0")) for c in CODIGOS_HE50), Decimal("0"))
        verbas_txt = (
            " · ".join(f"{c} {_brl(v)}" for c, v in sorted(verbas.items())) if verbas else "nenhuma verba de HE/100%"
        )
        horas_por_dia = await _horas_por_dia(db, eid, ano, mes)
        base_comum = {
            "competencia": comp,
            "employee_id": eid,
            "nome": p["nome"],
            "cargo": p["cargo"],
            "escala": p["escala"],
            "condominio": p["condominio"],
            "valor_hora": valor_hora,
            "verbas": _json(verbas),
        }

        dias_feriado: set[date] = set()
        for dia, fers in sorted(feriados.items()):
            if dia not in horas_por_dia:
                continue  # tinha turno mas não bateu, ou nem turno tinha: não trabalhou
            dias_feriado.add(dia)
            horas = _d(horas_por_dia[dia])
            ja_pago = _d(horas * valor_hora)  # o plantão já está dentro do salário mensal (0001)
            devido = _d(horas * valor_hora * Decimal("2"))
            f0 = fers[0]
            params.append(
                {
                    **base_comum,
                    "tipo": "feriado_trabalhado",
                    "data": dia,
                    "feriado": f0.get("nome"),
                    "escopo": f0.get("escopo"),
                    "teve_turno": (eid, dia) in turnos,
                    "horas": horas,
                    "pago_como": _d(ja_pago + pago_100),
                    "pago_detalhe": (
                        f"{_brl(ja_pago)} já dentro do salário mensal (0001) · "
                        f"{RUBRICA_100} Hora Extra 100%: {_brl(pago_100)} · holerite {mes:02d}/{ano}: {verbas_txt}"
                    ),
                    "deveria_ser": devido,
                    "diferenca": _d(devido - ja_pago - pago_100),
                    "regra": REGRA_FERIADO,
                }
            )

        # HE que o espelho classificou como 100% FORA de feriado (domingo / dia de descanso no
        # 44h). Em feriado a dobra acima já cobre o plantão inteiro — contar aqui seria 2×.
        linhas_he = he_dias.get(eid, [])
        horas_he_mes = sum((hh for _d0, hh, _t in linhas_he), Decimal("0"))
        for dia, horas, tp in sorted(linhas_he):
            if tp != "100" or dia in dias_feriado or horas <= 0:
                continue
            rateio = _d(pago_he50 * horas / horas_he_mes) if horas_he_mes else Decimal("0")
            devido = _d(horas * valor_hora * Decimal("2"))
            params.append(
                {
                    **base_comum,
                    "tipo": "he100",
                    "data": dia,
                    "feriado": "domingo / dia de descanso (classificação do espelho)",
                    "escopo": "espelho",
                    "teve_turno": (eid, dia) in turnos,
                    "horas": horas,
                    "pago_como": _d(rateio + pago_100),
                    "pago_detalhe": (
                        f"HE 50% do holerite rateada por hora: {_brl(pago_he50)} × {horas}h ÷ {horas_he_mes}h "
                        f"= {_brl(rateio)} · {RUBRICA_100}: {_brl(pago_100)} · holerite {mes:02d}/{ano}: {verbas_txt}"
                    ),
                    "deveria_ser": devido,
                    "diferenca": _d(devido - rateio - pago_100),
                    "regra": REGRA_HE100,
                }
            )

    if params:
        await db.execute(text(_SQL_UPSERT), params)
    # linhas que deixaram de valer (feriado removido, batida corrigida) não podem ficar de pé
    chaves = [f"{x['tipo']}|{x['employee_id']}|{x['data'].isoformat()}" for x in params]
    await db.execute(
        text(
            "DELETE FROM folha_feriado_conferencia WHERE competencia = :c "
            " AND tipo || '|' || employee_id || '|' || data::text <> ALL(CAST(:k AS text[]))"
        ),
        {"c": comp, "k": chaves or [""]},
    )
    await db.commit()

    n = (
        await db.execute(text("SELECT count(*) FROM folha_feriado_conferencia WHERE competencia = :c"), {"c": comp})
    ).scalar()
    return {"competencia": comp, "linhas": int(n or 0), "pessoas_avaliadas": len(pessoas)}


def _json(verbas: dict[str, Decimal]) -> str:
    import json

    return json.dumps({k: float(v) for k, v in verbas.items()})


_SQL_LINHAS = """
SELECT id, tipo, employee_id, nome, cargo, escala, condominio, data, feriado, escopo, teve_turno,
       horas, valor_hora, pago_como, pago_detalhe, verbas, deveria_ser, diferenca, regra
  FROM folha_feriado_conferencia
 WHERE competencia = :c
 ORDER BY diferenca DESC, data, nome
"""


async def linhas(db, competencia: str) -> list[dict[str, Any]]:
    """As linhas da competência, prontas para a tela e para o oráculo."""
    ano, mes = competencia_valida(competencia)
    await _ensure(db)
    rows = (await db.execute(text(_SQL_LINHAS), {"c": f"{ano:04d}-{mes:02d}"})).mappings().all()
    return [
        {
            **dict(r),
            "horas": float(r["horas"] or 0),
            "valor_hora": float(r["valor_hora"] or 0),
            "pago_como": float(r["pago_como"] or 0),
            "deveria_ser": float(r["deveria_ser"] or 0),
            "diferenca": float(r["diferenca"] or 0),
            "verbas": dict(r["verbas"] or {}),
        }
        for r in rows
    ]


async def resumo(db, competencia: str) -> dict[str, Any]:
    """Totais da competência — o número que vai no topo da tela."""
    ls = await linhas(db, competencia)
    return {
        "competencia": competencia,
        "linhas": len(ls),
        "pessoas": len({x["employee_id"] for x in ls}),
        "feriados": len({x["data"] for x in ls if x["tipo"] == "feriado_trabalhado"}),
        "horas": round(sum(x["horas"] for x in ls), 2),
        "pago": round(sum(x["pago_como"] for x in ls), 2),
        "devido": round(sum(x["deveria_ser"] for x in ls), 2),
        "diferenca": round(sum(x["diferenca"] for x in ls), 2),
    }


async def trabalhado_por_feriado(db, de: date, ate: date) -> dict[date, int]:
    """{data do feriado: nº de pessoas que trabalharam} — a coluna nova da tela de feriados (F7)."""
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT data, count(DISTINCT employee_id) FROM folha_feriado_conferencia "
                " WHERE tipo = 'feriado_trabalhado' AND data BETWEEN :de AND :ate GROUP BY 1"
            ),
            {"de": de, "ate": ate},
        )
    ).all()
    return {d: int(n) for d, n in rows}


async def competencias(db, limite: int = 12) -> list[str]:
    """Competências com holerite (mais recentes primeiro) — alimenta o select da tela."""
    rows = (
        await db.execute(
            text("SELECT DISTINCT reference_year, reference_month FROM hr_payslips  ORDER BY 1 DESC, 2 DESC LIMIT :n"),
            {"n": limite},
        )
    ).all()
    return [f"{a:04d}-{m:02d}" for a, m in rows]


def demo() -> None:
    """Checagem local das partes puras (não toca no banco)."""
    assert _mes_bounds(2026, 9) == (date(2026, 9, 1), date(2026, 9, 30))
    assert _mes_bounds(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))
    assert _mes_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert _d("1670") / 1 == Decimal("1670.00")
    assert _d(Decimal("1670") / 180) == Decimal("9.28")  # valor-hora do piso no 12x36
    # a dobra: 11h a R$ 9,28 → pago 102,08, devido 204,16, diferença 102,08
    vh, horas = Decimal("9.28"), Decimal("11")
    assert _d(horas * vh) == Decimal("102.08")
    assert _d(horas * vh * 2) - _d(horas * vh) == Decimal("102.08")
    assert RUBRICA_100 in CODIGOS_PAGAM_FERIADO and "0040" in CODIGOS_PAGAM_FERIADO
    assert set(TIPOS) == {"feriado_trabalhado", "he100"}
    print("feriado_conferencia.demo: ok")


if __name__ == "__main__":  # pragma: no cover
    demo()
