"""A direção da batida: as duas réguas medidas lado a lado — PARALELO CEGO (DGX Y2, 24/09/2026).

## Por que existe

`DGX_X4_pareador_unico.md` §7.1 fechou a frente do DIA e deixou aberta a do PAR. A casa tem duas
réguas de pareamento que discordam sobre **se o tipo da batida manda**:

  · **Régua A — cronológica** (`horas_service.parear_batidas`, a da FOLHA e do FECHAMENTO):
    ignora `punch_type` de propósito. As batidas do noturno vêm tipadas erradas com frequência
    (entra 21:01 e sai 09:01 gravando as duas como `entrada`) e confiar no tipo fazia o turno
    inteiro sumir, levando junto o adicional noturno.
  · **Régua B — com direção** (`time_record_service._pair_punches`, a da TELA DE PONTO do DP):
    *batida tipada `saida` não ABRE turno*. Nasceu do defeito real do commit 5e0bbc1f: sem ela,
    `[saída de ontem 07:00, entrada de hoje 19:00]` viravam 12h de trabalho **sobre o descanso**.

As duas nasceram de defeito real e **cada uma acerta em dias diferentes**. Σ|Δ| medido pela X4:
**192 horas** em 07+08+09/2026. Escolher uma muda `horas_trabalhadas`/`horas_noturnas` — e daí
saem hora extra 50% e adicional noturno. Ou seja: dinheiro.

## O que este módulo faz — e o que NÃO faz

**Mede, explica e classifica.** Grava numa tabela PRÓPRIA (`ponto_divergencia_regua`), que existe
para ser lida por gente. **Não escolhe régua nenhuma**, não muda folha, espelho, `time_sheets`
nem a tela de ponto. O oráculo `test_oraculo_y2_direcao_batida.py` prova Σ|Δ| = R$ 0,00 contra os
holerites gravados.

## As duas réguas são IMPORTADAS, não recriadas

Um nono pareador de batida seria exatamente o defeito que a X4 §7.2 catalogou (são OITO). Aqui:

  · Régua B roda como o DP a roda: `TimeRecordService._pair_punches(..., manter_origem=True)`,
    com as MESMAS janelas de turno. `_punch_ids` diz quais batidas cada registro consumiu.
  · Régua A roda por **sondagem de prefixo** sobre a própria `parear_batidas`: a função é uma
    varredura da esquerda para a direita, então acrescentar uma batida ao fim nunca muda decisão
    anterior. Chamando-a sobre `rows[:k]` para k = 2..n e olhando onde `dias_com_par` sobe,
    recupera-se CADA par que ela formou — e um par dela é sempre de linhas ADJACENTES
    (`entrada, saida = rows[i], rows[i+1]`), então o par que fecha no prefixo k é (k−2, k−1).
    Nenhuma linha da régua foi copiada: se a Y1 mexer em `horas_service`, esta medição segue.

## O dia é o do PLANTÃO nos dois lados

`dia_do_plantao` (DGX V1/W1) já é a régua das duas — foi o que a X4 unificou (Σ|Δ| de dias caiu
de 162 para 2). Por isso a comparação aqui é por **hora**, não por dia: agrupa-se pelo dia do
plantão e compara-se `horas_trabalhadas`. Diferença de número de PARES sem diferença de hora é a
fusão de intervalo da régua B (o 12x36 com 1h de almoço vira 1 registro de 11h onde a régua A vê
2 pares de 7h + 4h) — mesma hora, mesmo dia, nada a decidir: fica registrada na coluna, não vira
divergência.

## As causas

Cada divergência recebe UMA causa, na ordem em que são testadas (a primeira que explica vence):

  `batida_duplicada`      duas batidas a menos de DUPLICADA_MIN uma da outra
  `tipo_errado_no_aparelho`  a régua A abriu turno com uma batida tipada `saida` — que é
                          exatamente o que a régua B recusa. É a §7.1 em estado puro:
                          bateu «saída» ao chegar.
  `batida_faltando`       número ÍMPAR de batidas no dia, ou ponta que nenhuma régua fechou
  `virada_de_meia_noite`  as batidas do dia caem em duas datas civis e nada acima explica
  `indeterminado`         nenhuma das anteriores

`indeterminado` é confissão de ignorância, não lixo: o oráculo exige que as duas réguas tenham
de fato rodado antes de aceitar uma linha assim.

## Quem acerta

Quando há turno lançado em `shifts` cobrindo o dia, a jornada planejada é o árbitro: ganha a
régua cuja hora chega mais perto dela. Sem turno lançado, `sem_turno` — e a linha fica na tela
dizendo que não dá para saber. Geofence e cobertura NÃO entram (ver §5 do relatório): o turno
planejado é o único sinal que existe para todos os dias medidos.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import text

from modules.people_management.folha.services.atraso_falta_conferencia import (
    competencia_iso,
    competencia_tupla,
)

#: Duas batidas a menos disto uma da outra são a mesma intenção registrada duas vezes (toque
#: duplo no aparelho). Calibragem, não lei — o dono pode apertar.
DUPLICADA_MIN = 3

#: Tolerância para considerar duas horas IGUAIS (em horas). 0,02 h = 1,2 min — é o arredondamento
#: de `parear_batidas` (2 casas) contra o `HH:MM` da régua B, que perde os segundos.
TOL_H = 0.02

#: Quanto uma régua pode se afastar da jornada PLANEJADA e ainda ser considerada "bate com a
#: realidade". Acima disto ela não está medindo o turno — está medindo um buraco de ponto.
#: 2 h cobre folga legítima de entrada/saída e hora extra curta sem absorver meio plantão.
#: Calibragem, não lei: apertar para 1 h aumenta `ambas_erram`, afrouxar para 3 h diminui.
TOL_REALIDADE_H = 2.0

CAUSAS = (
    "tipo_errado_no_aparelho",
    "batida_faltando",
    "batida_duplicada",
    "virada_de_meia_noite",
    "indeterminado",
)

#: As batidas cruas do mês ± 1 dia, na MESMA ordem de `horas_service.SQL_BATIDAS` (o desempate
#: por tipo e punch_id existe para o total não oscilar entre execuções). As duas réguas recebem
#: esta mesma lista, na mesma ordem — senão a comparação mediria a ordenação, não a régua.
SQL_BATIDAS_RICAS = text(
    "SELECT punch_id, employee_id, punch_type, punch_timestamp, device_type, created_at, "
    "       updated_at, latitude, longitude "
    "  FROM gp_clock_punches "
    " WHERE CAST(employee_id AS TEXT) = :e AND punch_timestamp >= :ini AND punch_timestamp < :fim "
    " ORDER BY punch_timestamp, "
    "          CASE WHEN lower(coalesce(punch_type,'')) LIKE 'sa%' THEN 0 ELSE 1 END, punch_id"
)

SQL_PESSOAS = text(
    "SELECT CAST(id AS TEXT), nome FROM employees  WHERE coalesce(is_homologacao,false) = false ORDER BY nome"
)

#: Jornada planejada do dia, para saber qual régua chega mais perto da realidade.
SQL_TURNO_DIA = text(
    "SELECT shift_date, planned_start_time, planned_end_time FROM shifts "
    " WHERE CAST(employee_id AS TEXT) = :e AND shift_date BETWEEN :ini AND :fim "
    "   AND lower(coalesce(status,'')) <> 'cancelled' AND NOT coalesce(is_off_day,false)"
)

DDL = """
CREATE TABLE IF NOT EXISTS ponto_divergencia_regua (
  id serial PRIMARY KEY,
  competencia varchar(7) NOT NULL,
  employee_id varchar(50) NOT NULL,
  employee_nome varchar(200) NOT NULL,
  dia date NOT NULL,
  batidas jsonb NOT NULL DEFAULT '[]'::jsonb,
  pares_a integer NOT NULL DEFAULT 0,
  horas_a numeric(8,2) NOT NULL DEFAULT 0,
  detalhe_a jsonb NOT NULL DEFAULT '[]'::jsonb,
  pares_b integer NOT NULL DEFAULT 0,
  horas_b numeric(8,2) NOT NULL DEFAULT 0,
  detalhe_b jsonb NOT NULL DEFAULT '[]'::jsonb,
  delta_h numeric(8,2) NOT NULL DEFAULT 0,
  causa varchar(32) NOT NULL DEFAULT 'indeterminado',
  quem_acerta varchar(16) NOT NULL DEFAULT 'sem_turno',
  mais_perto varchar(1) NOT NULL DEFAULT '',
  horas_planejadas numeric(8,2),
  observacao text,
  apurado_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_divergencia_regua
  ON ponto_divergencia_regua (competencia, employee_id, dia);
CREATE INDEX IF NOT EXISTS ix_ponto_divergencia_regua_causa
  ON ponto_divergencia_regua (competencia, causa);
"""


async def _ensure(db) -> None:
    for stmt in filter(None, (s.strip() for s in DDL.split(";"))):
        await db.execute(text(stmt))
    await db.commit()


def _br(comp: str) -> str:
    a, m = comp.split("-")
    return f"{m}/{a}"


# ───────────────────────── régua A: os pares que `parear_batidas` formou ─────────────────────────


def pares_regua_a(rows: list, ini: datetime, fim: datetime, janelas: list) -> list[tuple[int, int]]:
    """Os pares (índice da entrada, índice da saída) que `parear_batidas` formou sobre `rows`.

    Sondagem de prefixo sobre a FUNÇÃO DE PRODUÇÃO — nenhuma linha da régua é copiada aqui.
    Vale porque `parear_batidas` é uma varredura da esquerda para a direita: o que ela decide
    em `rows[:k]` não muda quando chega `rows[k]`. E porque um par dela é sempre de linhas
    ADJACENTES (`entrada, saida = rows[i], rows[i + 1]`) — então o par que fecha no prefixo k
    é exatamente (k−2, k−1).

    `ini`/`fim` têm de ser LARGOS (o mês ± 1 dia): `dias_com_par` só conta o par cuja entrada
    cai na janela, e aqui queremos todos.
    """
    from modules.people_management.ponto.services.horas_service import parear_batidas

    pares: list[tuple[int, int]] = []
    anterior = 0
    for k in range(2, len(rows) + 1):
        n = parear_batidas(rows[:k], ini, fim, janelas)["dias_com_par"]
        if n > anterior:
            pares.append((k - 2, k - 1))
            anterior = n
    return pares


def _dias_regua_a(rows: list, pares: list[tuple[int, int]], janelas: list) -> dict:
    """{dia do plantão: {pares, horas, detalhe, indices}} da régua A.

    O dia sai de `dia_do_plantao` (a régua única da V1/W1), com a MESMA cadeia de continuidade
    que `parear_batidas` mantém: `ultimo = (saída do par anterior, dia atribuído a ele)`.
    """
    from modules.people_management.ponto.services.horas_service import dia_do_plantao

    out: dict[date, dict] = {}
    ultimo: tuple | None = None
    for i, j in pares:
        entrada, saida = rows[i][1], rows[j][1]
        dia = dia_do_plantao(entrada, janelas, ultimo)
        ultimo = (saida, dia)
        d = out.setdefault(dia, {"pares": 0, "horas": 0.0, "detalhe": [], "indices": set()})
        d["pares"] += 1
        d["horas"] += (saida - entrada).total_seconds() / 3600.0
        d["detalhe"].append(
            {
                "entrada": f"{entrada:%d/%m %H:%M}",
                "saida": f"{saida:%d/%m %H:%M}",
                "horas": round((saida - entrada).total_seconds() / 3600.0, 2),
            }
        )
        d["indices"].update((i, j))
    # órfãs da régua A: tudo que nenhum par consumiu. Entram no conjunto de batidas do dia pelo
    # dia do plantão da própria batida, para a causa poder vê-las.
    usados = {i for par in pares for i in par}
    ultimo = None
    for i, r in enumerate(rows):
        if i in usados:
            continue
        dia = dia_do_plantao(r[1], janelas, ultimo)
        d = out.setdefault(dia, {"pares": 0, "horas": 0.0, "detalhe": [], "indices": set()})
        d["indices"].add(i)
        d.setdefault("orfas", 0)
        d["orfas"] += 1
    for d in out.values():
        d["horas"] = round(d["horas"], 2)
        d.setdefault("orfas", 0)
    return out


# ───────────────────────── régua B: o que `_pair_punches` concluiu ─────────────────────────


def _dias_regua_b(recs: list[dict], por_id: dict[str, int], rows: list) -> dict:
    """{dia do plantão: {pares, horas, detalhe, indices, orfas}} da régua B.

    `recs` vem de `TimeRecordService._pair_punches(..., manter_origem=True)` — `_punch_ids` diz
    quais batidas cada registro consumiu, e `record_date` já é o dia do plantão (DGX X4).
    Registro sem `total_hours` é ponta solta (`inconsistencia`): conta como órfã, nunca hora.
    """
    out: dict[date, dict] = {}
    for r in recs:
        dia = date.fromisoformat(r["record_date"])
        d = out.setdefault(dia, {"pares": 0, "horas": 0.0, "detalhe": [], "indices": set(), "orfas": 0})
        for pid in r.get("_punch_ids") or ():
            if pid in por_id:
                d["indices"].add(por_id[pid])
        if not r.get("total_hours"):
            d["orfas"] += 1
            continue
        hh, mm = r["total_hours"].split(":")
        horas = int(hh) + int(mm) / 60.0
        idx = sorted(por_id[p] for p in (r.get("_punch_ids") or ()) if p in por_id)
        d["pares"] += 1
        d["horas"] += horas
        d["detalhe"].append(
            {
                "entrada": f"{rows[idx[0]][1]:%d/%m %H:%M}" if idx else "?",
                "saida": f"{rows[idx[-1]][1]:%d/%m %H:%M}" if idx else "?",
                "horas": round(horas, 2),
                "intervalo": bool(r.get("clock_in_lunch")),
            }
        )
    for d in out.values():
        d["horas"] = round(d["horas"], 2)
    return out


# ───────────────────────────────────── a causa ─────────────────────────────────────


def classificar(batidas: list[dict], a: dict, b: dict) -> tuple[str, str]:
    """(causa, observação) de UMA divergência. Primeira regra que explica vence.

    `batidas` = as batidas cruas do dia, `[{hora, tipo, ts, abre_a, par_b}]` em ordem;
    `a`/`b` = o que cada régua concluiu no dia.

    A causa é lida do MECANISMO, não de palpite: `abre_a and not par_b` com tipo exatamente
    `saida` é a regra dura da régua B disparando («saída não abre turno») sobre uma batida que
    a régua A usou como entrada. `saida` tem de ser o tipo EXATO — `saida_almoco` não dispara a
    regra, e tratá-lo como se disparasse rotulava errado 12 dias de jornada partida (medido).
    """
    tss = [x["ts"] for x in batidas]
    for i in range(1, len(tss)):
        if (tss[i] - tss[i - 1]).total_seconds() <= DUPLICADA_MIN * 60:
            return (
                "batida_duplicada",
                f"{batidas[i - 1]['hora']} e {batidas[i]['hora']} a menos de {DUPLICADA_MIN} min "
                "uma da outra: é a mesma intenção registrada duas vezes no aparelho.",
            )
    recusadas = [x for x in batidas if x.get("abre_a") and not x.get("par_b") and x["tipo"] == "saida"]
    if recusadas:
        q = ", ".join(x["hora"] for x in recusadas[:3])
        return (
            "tipo_errado_no_aparelho",
            f"A régua A abriu turno com batida tipada «saída» ({q}); a régua B recusou pela regra "
            "dura «saída não abre turno». Se a pessoa bateu «saída» ao CHEGAR (ou ao voltar do "
            "intervalo), quem acerta é a régua A; se é mesmo a saída de um turno anterior, é a B.",
        )
    if len(batidas) % 2 == 1:
        return (
            "batida_faltando",
            f"{len(batidas)} batida(s) no plantão — número ÍMPAR: uma ponta não foi registrada. "
            "As duas réguas fecham o buraco de jeitos diferentes.",
        )
    if a.get("orfas") or b.get("orfas"):
        return (
            "batida_faltando",
            f"Ponta que nenhuma régua conseguiu fechar (régua A: {a.get('orfas', 0)} órfã(s); "
            f"régua B: {b.get('orfas', 0)}). Buraco de ponto, não de cálculo.",
        )
    if len({x["ts"].date() for x in batidas}) > 1:
        return (
            "virada_de_meia_noite",
            "As batidas do plantão caem em duas datas civis e as réguas as agrupam diferente.",
        )
    return (
        "indeterminado",
        "Nenhuma causa conhecida explica: as batidas são pares, do mesmo dia civil, sem duplicata "
        "e sem «saída» abrindo turno — e ainda assim as réguas somam horas diferentes.",
    )


def arbitrar(horas_a: float, horas_b: float, planejado: float | None) -> tuple[str, str]:
    """(quem_acerta, mais_perto) — a jornada planejada de `shifts` é o único árbitro que existe.

    `quem_acerta`: `A`/`B` quando só uma das duas cai dentro de TOL_REALIDADE_H do planejado;
    `empate` quando as duas caem; `ambas_erram` quando nenhuma cai — e esse é o caso que importa
    ler, porque ali o defeito está no DADO, não na escolha da régua; `sem_turno` quando não há
    turno lançado no dia e não dá para saber.

    `mais_perto` é o desempate FRACO (só quem chegou mais perto), registrado à parte de propósito:
    ganhar por 3,9 h contra 6,9 h numa jornada de 12 h não é acertar.
    """
    if planejado is None:
        return "sem_turno", ""
    da, dbb = abs(horas_a - planejado), abs(horas_b - planejado)
    perto = "" if abs(da - dbb) <= TOL_H else ("A" if da < dbb else "B")
    dentro_a, dentro_b = da <= TOL_REALIDADE_H, dbb <= TOL_REALIDADE_H
    if dentro_a and dentro_b:
        return "empate", perto
    if dentro_a:
        return "A", perto
    if dentro_b:
        return "B", perto
    return "ambas_erram", perto


# ───────────────────────────────────── apuração ─────────────────────────────────────

_SQL_UPSERT = text(
    """
INSERT INTO ponto_divergencia_regua
  (competencia, employee_id, employee_nome, dia, batidas, pares_a, horas_a, detalhe_a,
   pares_b, horas_b, detalhe_b, delta_h, causa, quem_acerta, mais_perto, horas_planejadas,
   observacao, apurado_em)
VALUES
  (:competencia, :employee_id, :employee_nome, :dia, CAST(:batidas AS jsonb), :pares_a, :horas_a,
   CAST(:detalhe_a AS jsonb), :pares_b, :horas_b, CAST(:detalhe_b AS jsonb), :delta_h, :causa,
   :quem_acerta, :mais_perto, :horas_planejadas, :observacao, now())
ON CONFLICT (competencia, employee_id, dia) DO UPDATE SET
  employee_nome = EXCLUDED.employee_nome, batidas = EXCLUDED.batidas,
  pares_a = EXCLUDED.pares_a, horas_a = EXCLUDED.horas_a, detalhe_a = EXCLUDED.detalhe_a,
  pares_b = EXCLUDED.pares_b, horas_b = EXCLUDED.horas_b, detalhe_b = EXCLUDED.detalhe_b,
  delta_h = EXCLUDED.delta_h, causa = EXCLUDED.causa, quem_acerta = EXCLUDED.quem_acerta,
  mais_perto = EXCLUDED.mais_perto, horas_planejadas = EXCLUDED.horas_planejadas,
  observacao = EXCLUDED.observacao, apurado_em = now()
"""
)


def _horas_planejadas(turnos: dict, dia: date) -> float | None:
    """Horas da jornada planejada do dia (soma dos turnos lançados), ou None se não houver."""
    t = turnos.get(dia)
    return round(t, 2) if t else None


async def apurar(db, competencia) -> dict:  # noqa: C901, PLR0912, PLR0915
    """Mede as duas réguas em toda a competência e grava a conferência. **Não muda um centavo.**

    Idempotente: a chave é (competência, employee_id, dia) — apurar duas vezes reescreve as
    MESMAS linhas, e o que saiu da apuração é removido (só linhas desta tabela, criada aqui).
    """
    from modules.people_management.hr.services.time_record_service import TimeRecordService
    from modules.people_management.ponto.services import horas_service as hs

    await _ensure(db)
    comp = competencia_iso(competencia)
    ano, mes = competencia_tupla(comp)
    p0 = hs.params_batidas("-", mes, ano)
    ini_mes, fim_mes = p0["_ini_mes"].date(), p0["_fim_mes"].date()

    svc = TimeRecordService(db)
    pessoas = (await db.execute(SQL_PESSOAS)).fetchall()

    linhas: list[dict] = []
    res = {
        "competencia": comp,
        "pessoas_com_batida": 0,
        "pessoas_divergentes": 0,
        "dias_divergentes": 0,
        "soma_abs_horas": 0.0,
        "por_causa": {c: {"dias": 0, "horas": 0.0} for c in CAUSAS},
        "quem_acerta": {"A": 0, "B": 0, "empate": 0, "ambas_erram": 0, "sem_turno": 0},
        "mais_perto": {"A": 0, "B": 0},
        "reguas_rodadas": 0,
    }

    for eid, nome in pessoas:
        p = hs.params_batidas(eid, mes, ano)
        pr = [
            dict(m)
            for m in (await db.execute(SQL_BATIDAS_RICAS, {"e": eid, "ini": p["ini"], "fim": p["fim"]}))
            .mappings()
            .all()
        ]
        if not pr:
            continue
        res["pessoas_com_batida"] += 1
        turnos_rows = (await db.execute(hs.SQL_TURNOS_JANELA, hs.params_turnos(p))).fetchall()
        janelas = hs.janelas_de_turno(turnos_rows)

        # a mesma lista, na mesma ordem, para as duas réguas
        rows = [(x["punch_type"], x["punch_timestamp"]) for x in pr]
        por_id = {str(x["punch_id"]): i for i, x in enumerate(pr)}

        pares_a = pares_regua_a(rows, p["ini"], p["fim"], janelas)
        dias_a = _dias_regua_a(rows, pares_a, janelas)
        recs_b = svc._pair_punches(pr, manter_origem=True, janelas={str(eid): janelas})
        dias_b = _dias_regua_b(recs_b, por_id, rows)
        res["reguas_rodadas"] += 1

        # jornada planejada por dia (soma dos turnos lançados naquele shift_date)
        planejado: dict[date, float] = {}
        for d, t0, t1 in (await db.execute(SQL_TURNO_DIA, hs.params_turnos(p))).fetchall():
            h0 = datetime.combine(d, t0)
            h1 = datetime.combine(d + timedelta(days=1) if t1 < t0 else d, t1)
            planejado[d] = planejado.get(d, 0.0) + (h1 - h0).total_seconds() / 3600.0

        abre_a = {i for i, _ in pares_a}
        #: índices que a régua B consumiu num par FECHADO (registro com horas). Quem abre par na
        #: régua A e não está aqui foi RECUSADO pela régua B — é o mecanismo da §7.1.
        par_b = {por_id[p] for r in recs_b if r.get("total_hours") for p in (r.get("_punch_ids") or ()) if p in por_id}
        divergiu = False
        for dia in sorted(set(dias_a) | set(dias_b)):
            if not (ini_mes <= dia < fim_mes):
                continue
            a = dias_a.get(dia, {"pares": 0, "horas": 0.0, "detalhe": [], "indices": set(), "orfas": 0})
            b = dias_b.get(dia, {"pares": 0, "horas": 0.0, "detalhe": [], "indices": set(), "orfas": 0})
            delta = round(a["horas"] - b["horas"], 2)
            if abs(delta) <= TOL_H:
                continue
            divergiu = True
            idx = sorted(a["indices"] | b["indices"])
            batidas = [
                {
                    "hora": f"{rows[i][1]:%d/%m %H:%M}",
                    "tipo": str(rows[i][0] or "").lower(),
                    "ts": rows[i][1],
                    "abre_a": i in abre_a,
                    "par_b": i in par_b,
                }
                for i in idx
            ]
            causa, obs = classificar(batidas, a, b)
            hplan = _horas_planejadas(planejado, dia)
            quem, perto = arbitrar(a["horas"], b["horas"], hplan)
            linhas.append(
                {
                    "competencia": comp,
                    "employee_id": str(eid),
                    "employee_nome": nome or str(eid),
                    "dia": dia,
                    "batidas": json.dumps(
                        [{k: v for k, v in x.items() if k != "ts"} for x in batidas], ensure_ascii=False
                    ),
                    "pares_a": a["pares"],
                    "horas_a": a["horas"],
                    "detalhe_a": json.dumps(a["detalhe"], ensure_ascii=False),
                    "pares_b": b["pares"],
                    "horas_b": b["horas"],
                    "detalhe_b": json.dumps(b["detalhe"], ensure_ascii=False),
                    "delta_h": delta,
                    "causa": causa,
                    "quem_acerta": quem,
                    "mais_perto": perto,
                    "horas_planejadas": hplan,
                    "observacao": obs,
                }
            )
            res["dias_divergentes"] += 1
            res["soma_abs_horas"] += abs(delta)
            res["por_causa"][causa]["dias"] += 1
            res["por_causa"][causa]["horas"] += abs(delta)
            res["quem_acerta"][quem] += 1
            if perto:
                res["mais_perto"][perto] += 1
        if divergiu:
            res["pessoas_divergentes"] += 1

    for ln in linhas:
        await db.execute(_SQL_UPSERT, ln)
    vivos = [f"{ln['employee_id']}|{ln['dia']}" for ln in linhas] or ["-"]
    await db.execute(
        text(
            "DELETE FROM ponto_divergencia_regua WHERE competencia = :c "
            "AND (employee_id || '|' || dia::text) <> ALL(CAST(:v AS text[]))"
        ),
        {"c": comp, "v": vivos},
    )
    await db.commit()

    res["linhas"] = len(linhas)
    res["soma_abs_horas"] = round(res["soma_abs_horas"], 2)
    for c in res["por_causa"]:
        res["por_causa"][c]["horas"] = round(res["por_causa"][c]["horas"], 2)
    return res


async def resumo(db, competencia=None) -> dict:
    """Lê a última apuração (sem reapurar). Sem competência, o consolidado de todas."""
    await _ensure(db)
    where = "WHERE competencia = :c" if competencia else ""
    par = {"c": competencia_iso(competencia)} if competencia else {}
    rows = (
        await db.execute(
            text(
                "SELECT causa, count(*) dias, coalesce(sum(abs(delta_h)),0) horas, "
                "       count(DISTINCT employee_id) pessoas "
                f"  FROM ponto_divergencia_regua {where} GROUP BY causa ORDER BY 3 DESC"
            ),
            par,
        )
    ).fetchall()
    tot = (
        (
            await db.execute(
                text(
                    "SELECT count(*) dias, coalesce(sum(abs(delta_h)),0) horas, "
                    "       count(DISTINCT employee_id) pessoas, max(apurado_em) em, "
                    "       count(*) FILTER (WHERE quem_acerta='A') a, "
                    "       count(*) FILTER (WHERE quem_acerta='B') b, "
                    "       count(*) FILTER (WHERE quem_acerta='empate') e, "
                    "       count(*) FILTER (WHERE quem_acerta='ambas_erram') x, "
                    "       count(*) FILTER (WHERE quem_acerta='sem_turno') s, "
                    "       count(*) FILTER (WHERE mais_perto='A') pa, "
                    "       count(*) FILTER (WHERE mais_perto='B') pb "
                    f"  FROM ponto_divergencia_regua {where}"
                ),
                par,
            )
        )
        .mappings()
        .first()
    )
    return {
        "por_causa": [dict(r._mapping) for r in rows],
        "total": dict(tot) if tot else {},
    }
