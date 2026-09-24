"""Banco de horas × folha — a ponte que nunca existiu (DGX X1, 24/09/2026).

O que a W5 §7 mediu e originou esta frente: dos 15 eventos que o DGX modela, o nosso motor produz
8. Dois dos que faltam são `banco_horas_credito` e `banco_horas_debito` — e o banco de horas está
COMPLETO no Operacional (`time_bank`, telas `banco-horas*`, saldo, aprovação, compensação,
vencimento, alerta) e **nunca conversou com a folha**. Hora que vence sem ser paga nem compensada
é passivo trabalhista (CLT art. 59 §3) e hoje ninguém a vê.

**PARALELO CEGO ABSOLUTO.** Este módulo grava SÓ em `banco_horas_conferencia`. Não escreve em
folha, holerite, pagamento nem em `time_bank`. Não cria rubrica. O oráculo
(`test_oraculo_x1_banco_horas_folha.py`) fotografa `hr_payslips` antes e depois do `apurar` e
falha se um centavo mudar.

Duas fontes, porque a verdade está dividida entre elas — e isto é o achado da frente:
  · **`time_bank`** é o LEDGER (o banco de horas formal: crédito, débito, compensação, vencimento,
    aprovação). Medido em 24/09/2026: **0 linhas em produção e no sandbox**. O módulo inteiro do
    Operacional nunca recebeu um lançamento.
  · **`time_sheets`** é a MEDIÇÃO do ponto (`hours_balance_minutes` = trabalhado − previsto, escrito
    por `espelho_service.py`). Medido em 24/09/2026: **933,4 h de crédito** e **4.768,0 h de
    débito** em 7 competências de 2026.
Por isso `estado='sem_lancamento'` existe: a pessoa tem saldo medido pelo ponto e NENHUM lançamento
no banco de horas. Não é zero — é hora que existe e nunca entrou no banco. Zero por falta de dado
nunca é escrito como zero por ausência de saldo.

Prazo de compensação — a fonte, dita por extenso:
  · A CCT SINDECOMPRESTS AM000613/2025 (a que temos como DADO em `cct_convencoes`, `cct_beneficios`,
    `cct_cargos`, `cct_funcao_eventos`) **não tem cláusula de banco de horas**. Conferido em
    24/09/2026 — não há prazo de compensação declarado por ela no nosso banco.
  · O prazo aplicado é o que o próprio sistema já usa:
    `operacional/services/time_bank_service.TimeBankService.DEFAULT_EXPIRATION_DAYS = 180`,
    que é a **CLT art. 59 §5** (acordo individual, compensação em até 6 meses). Com acordo
    COLETIVO a CLT art. 59 §2 admite 1 ano (`COLLECTIVE_AGREEMENT_EXPIRATION_DAYS = 365`).
    Qual dos dois vale aqui é decisão do dono — §7 do relatório.
  · Crédito que vence sem compensar vira hora extra a pagar: **CLT art. 59 §3** (e art. 59-B),
    com o adicional mínimo de 50% — é a conta de `a_pagar_por_vencimento`.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: CLT art. 59 §5 — acordo individual. Espelha `TimeBankService.DEFAULT_EXPIRATION_DAYS`.
COMPENSACAO_DIAS = 180

#: Corte declarado pelo DONO: crédito de competência ≤ este mês está QUITADO (pago em dinheiro
#: fora do sistema) e não é passivo nem vence. Jordan, 24/09/2026: «ninguém tem banco de horas nem
#: valores a vencer porque eu já paguei tudo». Mora em `system_configs` (chave abaixo) e não no
#: código, porque é decisão de dono e muda sem deploy — o mesmo padrão do `contabil.corte_baseline`.
CHAVE_CORTE = "banco_horas.corte_quitado"


async def corte_quitado(db) -> date | None:
    """Última competência que o dono declarou QUITADA (ou None). `AAAA-MM` → último dia do mês."""
    from core.parametros import param  # noqa: PLC0415

    v = await param(db, CHAVE_CORTE, default=None)
    if not v:
        return None
    txt = str(v).strip()[:7]
    try:
        ano, mes = int(txt[:4]), int(txt[5:7])
    except ValueError:
        logger.warning("dgx x1: %s com valor inválido (%r) — corte ignorado", CHAVE_CORTE, v)
        return None
    return date(ano, 12, 31) if mes == 12 else date(ano, mes + 1, 1) - timedelta(days=1)
#: CLT art. 59 §3 — o crédito não compensado é pago como extra (adicional mínimo de 50%).
FATOR_HE = Decimal("1.5")
#: mesmo divisor do motor de folha (`calculo_service.DIVISOR_ESCALA`) — copiado, não importado,
#: porque importar `calculo_service` aqui puxaria o motor inteiro para um caminho de leitura.
DIVISOR_ESCALA = {"12x36": 180, "44h": 220}
DIVISOR_PADRAO = 220

DDL = """
CREATE TABLE IF NOT EXISTS banco_horas_conferencia (
  id bigserial PRIMARY KEY,
  employee_id uuid NOT NULL,
  competencia date NOT NULL,
  estado varchar(24) NOT NULL,
  fonte varchar(20) NOT NULL,
  saldo_inicial numeric(10,2) NOT NULL DEFAULT 0,
  creditado numeric(10,2) NOT NULL DEFAULT 0,
  debitado numeric(10,2) NOT NULL DEFAULT 0,
  compensado numeric(10,2) NOT NULL DEFAULT 0,
  vencido_no_periodo numeric(10,2) NOT NULL DEFAULT 0,
  saldo_final numeric(10,2) NOT NULL DEFAULT 0,
  saldo_ponto numeric(10,2) NOT NULL DEFAULT 0,
  he_ponto numeric(10,2) NOT NULL DEFAULT 0,
  valor_hora numeric(12,2),
  a_pagar_por_vencimento numeric(12,2) NOT NULL DEFAULT 0,
  ja_pago_como_he numeric(12,2) NOT NULL DEFAULT 0,
  vence_em date,
  calculado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_id, competencia)
)
"""
_IX = (
    "CREATE INDEX IF NOT EXISTS ix_banco_horas_conferencia_venc "
    "ON banco_horas_conferencia (vence_em) WHERE vence_em IS NOT NULL"
)

#: uma consulta só: ledger + espelho do ponto + HE do holerite + cadastro do empregado.
_SQL_APURAR = """
WITH ledger AS (
  SELECT employee_id::text AS eid,
    sum(CASE WHEN reference_date <  :ini AND entry_type IN ('credit','adjustment') THEN hours
             WHEN reference_date <  :ini THEN -hours ELSE 0 END)                       AS saldo_inicial,
    sum(CASE WHEN reference_date BETWEEN :ini AND :fim
              AND entry_type IN ('credit','adjustment') THEN hours ELSE 0 END)         AS creditado,
    sum(CASE WHEN reference_date BETWEEN :ini AND :fim
              AND entry_type = 'debit' THEN hours ELSE 0 END)                          AS debitado,
    sum(CASE WHEN reference_date BETWEEN :ini AND :fim
              AND entry_type = 'compensation' THEN hours ELSE 0 END)                   AS compensado,
    sum(CASE WHEN entry_type IN ('credit','adjustment') AND status <> 'used'
              AND expiration_date BETWEEN :ini AND :fim THEN hours ELSE 0 END)         AS vencido,
    count(*)                                                                           AS n
  FROM time_bank
  WHERE coalesce(is_active, true) AND status IN ('approved','used','expired')
  GROUP BY 1
), esp AS (
  SELECT employee_id::text AS eid,
    sum(coalesce(hours_balance_minutes,0)) / 60.0   AS saldo_ponto,
    sum(coalesce(overtime_total_minutes,0)) / 60.0  AS he_ponto
  FROM time_sheets WHERE reference_year = :ano AND reference_month = :mes GROUP BY 1
), he AS (
  SELECT p.employee_id::text AS eid, round(sum((e->>'valor')::numeric), 2) AS v
  FROM hr_payslips p, jsonb_array_elements(p.earnings) e
  WHERE p.reference_year = :ano AND p.reference_month = :mes
    AND coalesce(p.status,'') <> 'cancelled' AND p.payslip_code NOT LIKE '13O-%'
    AND (e->>'descricao') ILIKE '%extra%'
  GROUP BY 1
), pes AS (
  SELECT eid FROM ledger UNION SELECT eid FROM esp UNION SELECT eid FROM he
)
SELECT pes.eid, coalesce(emp.nome,'—'), coalesce(emp.salario_base,0), coalesce(emp.escala_padrao,''),
       coalesce(l.saldo_inicial,0), coalesce(l.creditado,0), coalesce(l.debitado,0),
       coalesce(l.compensado,0), coalesce(l.vencido,0), coalesce(l.n,0),
       coalesce(s.saldo_ponto,0), coalesce(s.he_ponto,0), coalesce(he.v,0),
       (s.eid IS NOT NULL)
FROM pes
LEFT JOIN ledger    l   ON l.eid   = pes.eid
LEFT JOIN esp       s   ON s.eid   = pes.eid
LEFT JOIN he            ON he.eid  = pes.eid
LEFT JOIN employees emp ON emp.id::text = pes.eid
WHERE pes.eid ~ '^[0-9a-f-]{36}$'
ORDER BY 2
"""

_SQL_UPSERT = """
INSERT INTO banco_horas_conferencia
  (employee_id, competencia, estado, fonte, saldo_inicial, creditado, debitado, compensado,
   vencido_no_periodo, saldo_final, saldo_ponto, he_ponto, valor_hora,
   a_pagar_por_vencimento, ja_pago_como_he, vence_em, calculado_em)
VALUES (:eid, :comp, :estado, :fonte, :si, :cr, :db_, :cp, :vc, :sf, :sp, :hp, :vh, :ap, :he, :venc, now())
ON CONFLICT (employee_id, competencia) DO UPDATE SET
  estado = EXCLUDED.estado, fonte = EXCLUDED.fonte,
  saldo_inicial = EXCLUDED.saldo_inicial, creditado = EXCLUDED.creditado,
  debitado = EXCLUDED.debitado, compensado = EXCLUDED.compensado,
  vencido_no_periodo = EXCLUDED.vencido_no_periodo, saldo_final = EXCLUDED.saldo_final,
  saldo_ponto = EXCLUDED.saldo_ponto, he_ponto = EXCLUDED.he_ponto,
  valor_hora = EXCLUDED.valor_hora, a_pagar_por_vencimento = EXCLUDED.a_pagar_por_vencimento,
  ja_pago_como_he = EXCLUDED.ja_pago_como_he, vence_em = EXCLUDED.vence_em,
  calculado_em = now()
"""


def _h(v) -> Decimal:
    """Horas, 2 casas."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _r(v) -> Decimal:
    """Reais, 2 casas, meio para cima — o mesmo arredondamento do motor."""
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def competencia_periodo(competencia: str | date) -> tuple[int, int, date, date]:
    """'AAAA-MM' | 'MM/AAAA' | date → (ano, mês, primeiro dia, último dia)."""
    if isinstance(competencia, date):
        ano, mes = competencia.year, competencia.month
    else:
        s = str(competencia).strip()
        if "/" in s:  # MM/AAAA
            mes_s, ano_s = s.split("/", 1)
        else:  # AAAA-MM
            ano_s, mes_s = s.split("-")[:2]
        ano, mes = int(ano_s), int(mes_s)
    if not (1 <= mes <= 12) or not (2000 <= ano <= 2100):
        raise ValueError(f"competência inválida: {competencia!r}")
    ini = date(ano, mes, 1)
    fim = date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)
    return ano, mes, ini, fim


def valor_hora(salario_base, escala: str | None) -> Decimal:
    """Valor-hora pela escala — mesma conta do motor (`calculo_service` L404-406)."""
    div = DIVISOR_ESCALA.get((escala or "").strip(), DIVISOR_PADRAO)
    return _r(Decimal(str(salario_base or 0)) / Decimal(div))


async def _ensure(db) -> None:
    """DDL idempotente. Chamada por `apurar` e pelas telas."""
    await db.execute(text(DDL))
    await db.execute(text(_IX))
    await db.commit()


async def apurar(db, competencia: str | date) -> dict:
    """Apura a ponte banco de horas × folha de uma competência. NADA escreve em folha.

    Grava (idempotente por employee × competência) em `banco_horas_conferencia` e devolve
    `{'competencia', 'pessoas', 'linhas': [...]}`, cada linha com as chaves do contrato:
    `saldo_inicial`, `creditado`, `debitado`, `compensado`, `vencido_no_periodo`,
    `a_pagar_por_vencimento`, `ja_pago_como_he` — mais `saldo_final`, `saldo_ponto`, `he_ponto`,
    `valor_hora`, `vence_em`, `estado` e `fonte`, que são o que a tela precisa dizer com honestidade.
    """
    await _ensure(db)
    ano, mes, ini, fim = competencia_periodo(competencia)
    rows = (await db.execute(text(_SQL_APURAR), {"ini": ini, "fim": fim, "ano": ano, "mes": mes})).fetchall()

    corte = await corte_quitado(db)
    quitada = bool(corte and fim <= corte)
    # Competência quitada pelo dono: o crédito existiu e foi PAGO em dinheiro. Ele continua medido
    # (a tela mostra as horas), mas não vence e não é passivo — zerar `a_pagar` e `vence_em` é o
    # que separa «já resolvido» de «esquecido».
    vence_em = None if quitada else fim + timedelta(days=COMPENSACAO_DIAS)
    linhas: list[dict] = []
    for (
        eid,
        nome,
        salario,
        escala,
        si,
        cr,
        db_,
        cp,
        vc,
        n_led,
        sp,
        hp,
        he_rs,
        tem_espelho,
    ) in rows:
        si, cr, db_, cp = _h(si), _h(cr), _h(db_), _h(cp)
        # vencido nunca é negativo: a SOMA do ledger pode empatar, a hora vencida não pode ser < 0
        vc = max(_h(vc), Decimal("0.00"))
        sf = si + cr - db_ - cp - vc
        vh = valor_hora(salario, escala)
        ap = _r(vc * vh * FATOR_HE)
        if n_led:
            estado, fonte = "apurado", "time_bank"
        elif tem_espelho and _h(sp) != 0:
            # a hora existe no ponto e NUNCA entrou no banco de horas — não é zero, é ausência
            estado, fonte = "sem_lancamento", "espelho"
        elif tem_espelho:
            estado, fonte = "sem_saldo", "espelho"
        else:
            estado, fonte = "sem_dado", "sem_dado"
        if quitada:
            # o dono declarou pago: a hora continua visível, mas não é pendência
            estado = "quitado_pelo_dono"
        linha = {
            "employee_id": eid,
            "nome": nome,
            "estado": estado,
            "fonte": fonte,
            "saldo_inicial": float(si),
            "creditado": float(cr),
            "debitado": float(db_),
            "compensado": float(cp),
            "vencido_no_periodo": float(vc),
            "saldo_final": float(sf),
            "saldo_ponto": float(_h(sp)),
            "he_ponto": float(_h(hp)),
            "valor_hora": float(vh),
            "a_pagar_por_vencimento": 0.0 if quitada else float(ap),
            "ja_pago_como_he": float(_r(he_rs)),
            "vence_em": vence_em,
        }
        linhas.append(linha)
        await db.execute(
            text(_SQL_UPSERT),
            {
                "eid": eid,
                "comp": ini,
                "estado": estado,
                "fonte": fonte,
                "si": si,
                "cr": cr,
                "db_": db_,
                "cp": cp,
                "vc": vc,
                "sf": sf,
                "sp": _h(sp),
                "hp": _h(hp),
                "vh": vh,
                "ap": Decimal("0") if quitada else ap,
                "he": _r(he_rs),
                # vence quando há crédito a compensar — do ledger OU, na sua ausência, do ponto
                "venc": None if quitada else (vence_em if (cr > 0 or si > 0 or _h(sp) > 0) else None),
            },
        )
    await db.commit()
    logger.info("dgx x1: apuradas %d pessoa(s) em %02d/%d", len(linhas), mes, ano)
    return {
        "competencia": f"{ano}-{mes:02d}",
        "pessoas": len(linhas),
        "linhas": linhas,
        "quitada_pelo_dono": quitada,
        "corte": corte.isoformat() if corte else None,
    }


async def competencias(db) -> list[str]:
    """Competências com dado apurável ('AAAA-MM'), mais recente primeiro."""
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT to_char(competencia,'YYYY-MM') FROM banco_horas_conferencia "
                "UNION SELECT to_char(make_date(reference_year, reference_month, 1),'YYYY-MM') "
                "FROM time_sheets ORDER BY 1 DESC LIMIT 36"
            )
        )
    ).fetchall()
    return [r[0] for r in rows if r[0]]
