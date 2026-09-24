"""Hora extra CLASSIFICADA — faturada ao cliente × custo nosso × cobertura (DGX W3, 24/09/2026).

Por que existe: a HE aparece no espelho e na folha sem dizer POR QUE existiu. Sem isso ninguém
sabe quanto dela é repassável ao cliente (cobertura que o condomínio pediu, evento extra) e
quanto é custo nosso (falta de gente, atraso do próprio, erro de escala). Medido no sandbox em
24/09/2026: 08/2026 = 393 dias-pessoa de HE (27.796 min) · 09/2026 = 195 (10.385 min), **zero**
com explicação registrada. No DGX isso é `JustificarHoraExtra` (FATURADA / NÃO FATURADA /
COBERTURA + motivo) dentro do fechamento do apontamento.

Onde a HE vive (medido, 24/09/2026) — e por que este é o lugar certo de ler:
  · `time_sheets.daily_summary` (espelho de ponto, `hr/services/espelho_service.py`) é a ÚNICA
    fonte com HE **por dia**: `{date, overtime (min), overtime_type 50|100, night_real, ...}`.
    A soma dos dias bate exatamente com `time_sheets.overtime_50_minutes/100` (conferido nas
    duas competências), então classificar dia a dia não perde nem inventa minuto.
  · A FOLHA (`folha/services/calculo_service.py`) NÃO lê `time_sheets` para HE: a verba 0040
    sai de `horas_reais_ponto()` (agregado do mês sobre `gp_clock_punches`, excedente acima do
    divisor da escala) e, de jan–jun, do backfill `folha_verba_espelho`. São réguas diferentes
    e é por isso que ESTA tabela não toca em dinheiro nenhum: aqui só se diz o MOTIVO.

Nada aqui muda cálculo de folha nem preço de contrato. O R$ das telas é ESTIMATIVA
(horas × fator × `time_sheets.hourly_rate` da pessoa) — dito na tela, com essa palavra.

A sugestão automática nunca decide sozinha: ela preenche `motivo` e `repassavel` a partir de
prova (cobertura da F8 em `substitutions`, ou movimentação de cobertura da F5 em
`employee_alocacoes`) e fica `origem='automatica'` com `classificado_por` vazio até um humano
confirmar. **Sem prova, nasce `falta_de_efetivo` NÃO repassável** — nunca repassável por omissão.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

# ───────────────────────────── vocabulário ─────────────────────────────
#: motivo → (rótulo, repassável por padrão). Repassável = custo que o cliente paga.
MOTIVOS: dict[str, tuple[str, bool]] = {
    "cobertura_ferias": ("Cobertura de férias", True),
    "cobertura_falta": ("Cobertura de falta", True),
    "cobertura_afastamento": ("Cobertura de afastamento", True),
    "pedido_cliente": ("Pedido do cliente", True),
    "evento_extra": ("Evento extra", True),
    "falta_de_efetivo": ("Falta de efetivo", False),
    "atraso_proprio": ("Atraso do próprio", False),
    "erro_de_escala": ("Erro de escala", False),
    "outro": ("Outro (a definir)", False),
}
TIPOS = {
    "he50": "HE 50%",
    "he100": "HE 100%",
    "noturno": "Adicional noturno",
    "intrajornada": "Intrajornada",
}
#: multiplicador sobre o valor-hora, só para a ESTIMATIVA em R$ das telas.
FATOR = {"he50": Decimal("1.5"), "he100": Decimal("2.0"), "noturno": Decimal("0.2"), "intrajornada": Decimal("1.5")}
ORIGENS = ("automatica", "manual")

#: `substitutions.reason` (F8) → motivo. Só os três que são prova de cobertura de ausência do
#: coberto. Volante/folga/atividade externa/treinamento são escala nossa: caem em `outro`
#: (não repassável) com o rótulo na observação, para o humano decidir.
_REASON_MOTIVO = {
    "vacation": "cobertura_ferias",
    "afastamento": "cobertura_afastamento",
    "sick_leave": "cobertura_afastamento",
    "no_show": "cobertura_falta",
}
#: `employee_alocacoes.motivo` (F5) → motivo.
_MOV_MOTIVO = {
    "cobertura_de_ferias": "cobertura_ferias",
    "cobertura_de_afastamento": "cobertura_afastamento",
    "cobertura_de_falta": "cobertura_falta",
}

_DDL = (
    "CREATE TABLE IF NOT EXISTS ponto_he_classificacao ("
    " id serial PRIMARY KEY,"
    " employee_id varchar(50) NOT NULL,"
    " competencia varchar(7) NOT NULL,"
    " data date NOT NULL,"
    " horas numeric(6,2) NOT NULL DEFAULT 0,"
    " tipo varchar(16) NOT NULL,"
    " motivo varchar(32) NOT NULL,"
    " repassavel boolean NOT NULL DEFAULT false,"
    " contrato_id uuid, posto_id uuid, cobertura_id uuid,"
    " observacao text,"
    " classificado_por varchar(120), classificado_em timestamptz,"
    " origem varchar(12) NOT NULL DEFAULT 'automatica',"
    " created_at timestamptz DEFAULT now())",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_he_class ON ponto_he_classificacao (employee_id, data, tipo)",
    "CREATE INDEX IF NOT EXISTS ix_ponto_he_class_comp ON ponto_he_classificacao (competencia, motivo)",
)
_ensured = False


async def _ensure(db) -> None:
    global _ensured  # noqa: PLW0603 — uma vez por processo, como `fechamento._ensure`
    if _ensured:
        return
    for stmt in _DDL:
        await db.execute(text(stmt))
    await db.commit()
    _ensured = True


class HEClassificacaoErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def competencia_valida(competencia: str) -> tuple[int, int]:
    """'AAAA-MM' → (ano, mês). Levanta 400 se não for."""
    s = str(competencia or "").strip()
    try:
        ano, mes = int(s[:4]), int(s[5:7])
        if s[4] != "-" or not (1 <= mes <= 12) or not (2000 <= ano <= 2100):
            raise ValueError
    except Exception as exc:  # noqa: BLE001
        raise HEClassificacaoErro(400, f"Competência inválida: {competencia!r} (use AAAA-MM).") from exc
    return ano, mes


# ─────────────────── levantamento: lê a HE onde ela já vive ───────────────────
# UMA consulta traz o dia de HE + a prova de cobertura (F8), a movimentação (F5) e o posto do
# turno. Por-linha seriam ~1.800 idas ao banco numa competência de 600 dias-pessoa.
_SQL_LEVANTAR = """
WITH he AS (
  SELECT ts.employee_id,
         (x->>'date')::date AS dia,
         round(coalesce((x->>'overtime')::numeric, 0) / 60.0, 2) AS horas,
         CASE WHEN (x->>'overtime_type') = '100' THEN 'he100' ELSE 'he50' END AS tipo
    FROM time_sheets ts, jsonb_array_elements(coalesce(ts.daily_summary, '[]'::jsonb)) x
   WHERE coalesce(ts.is_deleted, false) = false
     AND ts.reference_year = :a AND ts.reference_month = :m
     AND coalesce((x->>'overtime')::numeric, 0) > 0
)
SELECT he.employee_id, he.dia, he.horas, he.tipo,
       c.reason, c.cob_id::text, c.post_id::text,
       mv.motivo, mv.posto_id::text,
       sh.post_id::text
  FROM he
  LEFT JOIN LATERAL (
      SELECT s.reason, coalesce(s.cobertura_id, s.id) AS cob_id, s.post_id
        FROM substitutions s
       WHERE s.is_active AND s.substitute_employee_id::text = he.employee_id
         AND s.substitution_date = he.dia
       ORDER BY s.created_at DESC LIMIT 1) c ON true
  LEFT JOIN LATERAL (
      SELECT a.motivo, a.posto_id
        FROM employee_alocacoes a
       WHERE a.employee_id::text = he.employee_id
         AND a.motivo IN ('cobertura_de_ferias', 'cobertura_de_afastamento', 'cobertura_de_falta')
         AND he.dia BETWEEN a.data_inicio AND coalesce(a.data_fim, DATE '9999-12-31')
       ORDER BY a.data_inicio DESC LIMIT 1) mv ON true
  LEFT JOIN LATERAL (
      SELECT s.post_id FROM shifts s
       WHERE s.employee_id::text = he.employee_id AND s.shift_date = he.dia
         AND lower(coalesce(s.status, '')) <> 'cancelled' AND NOT coalesce(s.is_off_day, false)
       ORDER BY s.planned_start_time LIMIT 1) sh ON true
"""

_SQL_INSERT = """
INSERT INTO ponto_he_classificacao
  (employee_id, competencia, data, horas, tipo, motivo, repassavel, contrato_id, posto_id, cobertura_id, observacao, origem)
VALUES
  (:e, :c, :d, :h, :t, :motivo, :repassavel, CAST(:contrato AS uuid), CAST(:posto AS uuid),
   CAST(:cobertura AS uuid), :obs, 'automatica')
ON CONFLICT (employee_id, data, tipo) DO NOTHING
"""

# posto → contrato: `posts.contract_id` quando aponta para um contrato QUE EXISTE (medido em
# 24/09: 6 postos da Conecta Village carregam um `contract_id` órfão — a linha de `contracts`
# não está lá; aceitá-lo cru daria um contrato fantasma no resumo); senão o ÚNICO contrato
# ativo do cliente do posto (cliente com 2 contratos ativos fica sem — chutar qual é mentir).
_SQL_POSTO_CONTRATO = """
SELECT p.id::text,
       coalesce((SELECT c1.id::text FROM contracts c1 WHERE c1.id = p.contract_id),
                CASE WHEN (SELECT count(*) FROM contracts c2 WHERE c2.client_id = p.client_id AND c2.status = 'active') = 1
                     THEN (SELECT c3.id::text FROM contracts c3 WHERE c3.client_id = p.client_id AND c3.status = 'active' LIMIT 1)
                END)
  FROM posts p
"""


async def levantar(db, competencia: str) -> dict[str, Any]:
    """Lê a HE da competência no espelho, cruza com cobertura/movimentação e grava o que falta.

    Idempotente por (employee_id, data, tipo): rodar de novo não duplica e não mexe no que já
    está lá (inclusive no que um humano reclassificou).
    """
    ano, mes = competencia_valida(competencia)
    await _ensure(db)
    postos = dict((await db.execute(text(_SQL_POSTO_CONTRATO))).all())
    linhas = (await db.execute(text(_SQL_LEVANTAR), {"a": ano, "m": mes})).fetchall()

    params: list[dict[str, Any]] = []
    for emp, dia, horas, tipo, reason, cob_id, cob_post, mov_motivo, mov_posto, turno_post in linhas:
        obs = None
        cobertura_id = None
        if reason:
            cobertura_id = cob_id
            motivo = _REASON_MOTIVO.get(reason)
            if not motivo:
                motivo, obs = "outro", f"Cobertura registrada como «{reason}» — confirme o motivo."
        elif mov_motivo:
            motivo = _MOV_MOTIVO[mov_motivo]
            obs = "Sugerido pela movimentação (F5)."
        else:
            motivo = "falta_de_efetivo"
            obs = "Sem cobertura (F8) nem movimentação (F5) no dia — sugestão conservadora."
        posto = cob_post or turno_post or mov_posto
        params.append(
            {
                "e": str(emp),
                "c": f"{ano:04d}-{mes:02d}",
                "d": dia,
                "h": horas,
                "t": tipo,
                "motivo": motivo,
                "repassavel": MOTIVOS[motivo][1],
                "contrato": postos.get(posto) if posto else None,
                "posto": posto,
                "cobertura": cobertura_id,
                "obs": obs,
            }
        )
    antes = await _contar(db, f"{ano:04d}-{mes:02d}")
    if params:
        await db.execute(text(_SQL_INSERT), params)
        await db.commit()
    depois = await _contar(db, f"{ano:04d}-{mes:02d}")
    return {
        "competencia": f"{ano:04d}-{mes:02d}",
        "linhas_he": len(params),
        "novas": depois - antes,
        "ja_classificadas": antes,
    }


async def _contar(db, competencia: str) -> int:
    return int(
        (
            await db.execute(
                text("SELECT count(*) FROM ponto_he_classificacao WHERE competencia = :c"), {"c": competencia}
            )
        ).scalar()
        or 0
    )


# ─────────────────── confirmar / reclassificar (linha ou lote) ───────────────────
def _filtro(ids, competencia, motivo, so_pendentes: bool) -> tuple[str, dict[str, Any]]:
    onde, p = [], {}
    if ids:
        onde.append("id = ANY(:ids)")
        p["ids"] = [int(i) for i in ids]
    if competencia:
        ano, mes = competencia_valida(competencia)
        onde.append("competencia = :c")
        p["c"] = f"{ano:04d}-{mes:02d}"
    if motivo:
        if motivo not in MOTIVOS:
            raise HEClassificacaoErro(400, f"Motivo inválido: {motivo!r}.")
        onde.append("motivo = :mf")
        p["mf"] = motivo
    if so_pendentes:
        onde.append("classificado_em IS NULL")
    if not onde:
        raise HEClassificacaoErro(400, "Informe ao menos a competência ou as linhas.")
    return " AND ".join(onde), p


async def confirmar(db, *, ids=None, competencia=None, motivo=None, quem: str = "", so_pendentes: bool = True) -> int:
    """Humano assina a sugestão. NÃO muda horas, motivo, repassável nem valor nenhum."""
    await _ensure(db)
    onde, p = _filtro(ids, competencia, motivo, so_pendentes)
    r = await db.execute(
        text(f"UPDATE ponto_he_classificacao SET classificado_por = :q, classificado_em = now() WHERE {onde}"),
        {**p, "q": (quem or "")[:120]},
    )
    await db.commit()
    return int(r.rowcount or 0)


async def reclassificar(
    db,
    *,
    novo_motivo: str,
    ids=None,
    competencia=None,
    motivo=None,
    repassavel: bool | None = None,
    observacao: str | None = None,
    quem: str = "",
) -> int:
    """Troca o motivo (e o repassável). Vira `origem='manual'` — a sugestão perdeu."""
    if novo_motivo not in MOTIVOS:
        raise HEClassificacaoErro(400, f"Motivo inválido: {novo_motivo!r}. Use um de {', '.join(MOTIVOS)}.")
    await _ensure(db)
    onde, p = _filtro(ids, competencia, motivo, so_pendentes=False)
    rep = MOTIVOS[novo_motivo][1] if repassavel is None else bool(repassavel)
    r = await db.execute(
        text(
            "UPDATE ponto_he_classificacao SET motivo = :nm, repassavel = :rp, origem = 'manual', "
            " observacao = coalesce(:obs, observacao), classificado_por = :q, classificado_em = now() "
            f"WHERE {onde}"
        ),
        {**p, "nm": novo_motivo, "rp": rep, "obs": (observacao or None), "q": (quem or "")[:120]},
    )
    await db.commit()
    return int(r.rowcount or 0)


# ─────────────────── leitura para as telas ───────────────────
_SQL_LINHAS = """
SELECT h.id, h.employee_id, coalesce(e.nome, h.employee_id) AS nome, h.data, h.horas, h.tipo, h.motivo,
       h.repassavel, h.origem, h.classificado_por, h.classificado_em AT TIME ZONE 'America/Manaus',
       coalesce(p.name, '—') AS posto, coalesce(ct.contract_number, '—') AS contrato,
       coalesce(ts.hourly_rate, 0) AS valor_hora, h.observacao, h.cobertura_id::text
  FROM ponto_he_classificacao h
  LEFT JOIN employees e ON e.id::text = h.employee_id
  LEFT JOIN posts p ON p.id = h.posto_id
  LEFT JOIN contracts ct ON ct.id = h.contrato_id
  LEFT JOIN time_sheets ts ON ts.employee_id = h.employee_id
       AND ts.reference_year = :a AND ts.reference_month = :m AND coalesce(ts.is_deleted, false) = false
 WHERE h.competencia = :c
 ORDER BY h.repassavel DESC, nome, h.data
"""


def estimativa_reais(horas, tipo: str, valor_hora) -> float:
    """R$ ESTIMADO da linha: horas × fator do tipo × valor-hora da pessoa no espelho.

    Não é o valor pago: a folha calcula HE por outra régua (`calculo_service`, verba 0040,
    excedente mensal sobre o divisor da escala). Serve para dimensionar o que está na mesa.
    """
    vh = Decimal(str(valor_hora or 0))
    return float(Decimal(str(horas or 0)) * FATOR.get(tipo, Decimal("1.5")) * vh)


async def linhas(db, competencia: str) -> list[dict[str, Any]]:
    ano, mes = competencia_valida(competencia)
    await _ensure(db)
    rows = (await db.execute(text(_SQL_LINHAS), {"c": f"{ano:04d}-{mes:02d}", "a": ano, "m": mes})).fetchall()
    return [
        {
            "id": r[0],
            "employee_id": r[1],
            "nome": r[2],
            "data": r[3],
            "horas": float(r[4] or 0),
            "tipo": r[5],
            "motivo": r[6],
            "repassavel": bool(r[7]),
            "origem": r[8],
            "classificado_por": r[9],
            "classificado_em": r[10],
            "posto": r[11],
            "contrato": r[12],
            "valor_hora": float(r[13] or 0),
            "reais": round(estimativa_reais(r[4], r[5], r[13]), 2),
            "observacao": r[14],
            "cobertura_id": r[15],
        }
        for r in rows
    ]


async def resumo_por_contrato(db, competencia: str) -> list[dict[str, Any]]:
    """Contrato × repassável × não repassável × R$ estimado. Soma exatamente as linhas."""
    agg: dict[str, dict[str, Any]] = {}
    for ln in await linhas(db, competencia):
        k = ln["contrato"]
        a = agg.setdefault(
            k,
            {
                "contrato": k,
                "linhas": 0,
                "horas_repassavel": 0.0,
                "horas_nao_repassavel": 0.0,
                "reais_repassavel": 0.0,
                "reais_nao_repassavel": 0.0,
                "pendentes": 0,
                "sem_valor_hora": 0,
            },
        )
        a["linhas"] += 1
        suf = "repassavel" if ln["repassavel"] else "nao_repassavel"
        a[f"horas_{suf}"] += ln["horas"]
        a[f"reais_{suf}"] += ln["reais"]
        if not ln["classificado_em"]:
            a["pendentes"] += 1
        if not ln["valor_hora"]:
            a["sem_valor_hora"] += 1
    for a in agg.values():
        for k in ("horas_repassavel", "horas_nao_repassavel", "reais_repassavel", "reais_nao_repassavel"):
            a[k] = round(a[k], 2)
    return sorted(agg.values(), key=lambda a: -a["reais_repassavel"])


async def repassavel_por_contrato(db, competencia: str) -> dict[str, float]:
    """`{contract_number: R$ repassável estimado}` — o que o CRM mostra como «não faturada».

    Só leitura, e só a estimativa: não existe, hoje, item de NFS-e que diga "HE repassada",
    então não há como abater o que já foi cobrado. A coluna do CRM diz isso com essas palavras.
    """
    return {
        a["contrato"]: a["reais_repassavel"]
        for a in await resumo_por_contrato(db, competencia)
        if a["contrato"] != "—" and a["reais_repassavel"]
    }


async def competencias(db, limite: int = 12) -> list[str]:
    """Competências com HE no espelho (mais recentes primeiro) — alimenta os selects."""
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT reference_year, reference_month FROM time_sheets "
                " WHERE coalesce(is_deleted, false) = false AND coalesce(overtime_total_minutes, 0) > 0 "
                " ORDER BY 1 DESC, 2 DESC LIMIT :n"
            ),
            {"n": limite},
        )
    ).fetchall()
    return [f"{a:04d}-{m:02d}" for a, m in rows]


def demo() -> None:
    """Checagem local das partes puras (não toca no banco)."""
    assert competencia_valida("2026-08") == (2026, 8)
    for ruim in ("2026/08", "2026-13", "", "agosto"):
        try:
            competencia_valida(ruim)
        except HEClassificacaoErro:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"aceitou competência inválida: {ruim!r}")
    # nenhum motivo de custo nosso pode nascer repassável
    for m in ("falta_de_efetivo", "atraso_proprio", "erro_de_escala", "outro"):
        assert MOTIVOS[m][1] is False, m
    for m in ("cobertura_ferias", "cobertura_falta", "cobertura_afastamento", "pedido_cliente", "evento_extra"):
        assert MOTIVOS[m][1] is True, m
    # todo motivo sugerido automaticamente existe no vocabulário
    for m in list(_REASON_MOTIVO.values()) + list(_MOV_MOTIVO.values()):
        assert m in MOTIVOS, m
    assert abs(estimativa_reais(2, "he50", 10) - 30.0) < 1e-9
    assert abs(estimativa_reais(2, "he100", 10) - 40.0) < 1e-9
    assert estimativa_reais(2, "he50", None) == 0.0
    onde, p = _filtro([1, 2], "2026-08", None, True)
    assert "id = ANY(:ids)" in onde and "classificado_em IS NULL" in onde and p["c"] == "2026-08"
    print("he_classificacao.demo: ok")


if __name__ == "__main__":  # pragma: no cover
    demo()
