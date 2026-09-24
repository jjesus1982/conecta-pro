"""Oráculo — Hora extra CLASSIFICADA: faturada ao cliente × custo nosso × cobertura (DGX W3, 24/09/2026).

Por que existe: a HE aparecia no espelho e na folha sem dizer POR QUE existiu. Sem isso ninguém
sabe quanto da HE é repassável ao cliente (cobertura que o condomínio pediu, evento extra) e
quanto é custo nosso (falta de gente, atraso, erro de escala). Medido em 24/09 no sandbox:
08/2026 = 393 dias-pessoa de HE (27.796 min) e 09/2026 = 195 (10.385 min), **zero** com
explicação registrada. O DGX resolve com `JustificarHoraExtra` (FATURADA / NÃO FATURADA /
COBERTURA + motivo) no fechamento do apontamento.

Os jeitos óbvios de mentir, e por isso cada afirmação existe:
  1. classificar "de lado" e deixar HE fora da lista (o dinheiro some do resumo) → (a);
  2. rodar o levantamento duas vezes e dobrar as horas → (b);
  3. inventar a sugestão (dizer "cobertura" sem cobertura) → (c), recontada por SQL próprio;
  4. mexer no valor da folha ao classificar → (d), paralelo cego contra `hr_payslips`;
  5. nascer repassável por omissão — HE sem prova nenhuma vira dinheiro do cliente → (e);
  6. um resumo por contrato que não bate com as linhas que o alimentam → (f).

O que afirma (recontado por SQL próprio, nunca pelo serviço):
  a. Toda HE da competência tem EXATAMENTE uma linha: `count(*)` e `sum(horas)` de
     `ponto_he_classificacao` == recontagem de `time_sheets.daily_summary` (overtime > 0),
     e nenhuma tripla (employee, data, tipo) repetida.
  b. `levantar()` é idempotente: rodar 2× não cria linha nem hora nova (novas = 0 na 2ª).
  c. Sugestão automática: numa cobertura de FÉRIAS registrada (F8, `substitutions`) no dia da
     HE, a linha nasce `cobertura_ferias` repassável, com `cobertura_id` da cobertura; o dia
     é recontado por SQL direto em `substitutions`, não pelo serviço.
  d. `confirmar()` não muda horas nem valor: Σ|Δ| dos holerites publicados da competência em
     `hr_payslips` (total_earnings, total_deductions, net_salary) = R$ 0,00 — e as horas de
     HE do espelho (`time_sheets.overtime_*`) idênticas antes e depois.
  e. HE sem cobertura (F8) e sem movimentação (F5) nasce `falta_de_efetivo` NÃO repassável.
     Nenhuma linha automática nasce repassável sem uma dessas duas provas.
  f. `resumo_por_contrato()` soma exatamente as linhas: horas e R$ estimado por contrato
     iguais à soma das linhas da competência (inclusive as sem contrato).

Estado medido no nascimento (staging `conecta_pro_staging`, 24/09/2026): a tabela
`ponto_he_classificacao` e o serviço `he_classificacao` não existiam → VERMELHO (ImportError).

Fixtures marcadas 'FIXTURE DGX W3' (`substitutions.notes`), apagadas no `finally`.
Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys

FIX = "FIXTURE DGX W3"
COMPETENCIA = "2026-08"  # a de maior volume de HE no sandbox

# ── recontagem independente: a HE como ela vive no espelho ──────────────────────────────
SQL_HE_ESPELHO = """
SELECT count(*) AS linhas, coalesce(sum(round(coalesce((x->>'overtime')::numeric, 0) / 60.0, 2)), 0) AS horas
  FROM time_sheets ts, jsonb_array_elements(coalesce(ts.daily_summary, '[]'::jsonb)) x
 WHERE coalesce(ts.is_deleted, false) = false
   AND ts.reference_year = :a AND ts.reference_month = :m
   AND coalesce((x->>'overtime')::numeric, 0) > 0
"""
SQL_TABELA = "SELECT count(*), coalesce(sum(horas), 0) FROM ponto_he_classificacao WHERE competencia = :c"
SQL_DUPLICADAS = (
    "SELECT count(*) FROM (SELECT employee_id, data, tipo FROM ponto_he_classificacao "
    "WHERE competencia = :c GROUP BY 1, 2, 3 HAVING count(*) > 1) d"
)
SQL_REPASSAVEL_SEM_PROVA = """
SELECT count(*) FROM ponto_he_classificacao h
 WHERE h.competencia = :c AND h.repassavel IS TRUE AND h.origem = 'automatica'
   AND NOT EXISTS (SELECT 1 FROM substitutions s WHERE s.is_active
                     AND s.substitute_employee_id::text = h.employee_id AND s.substitution_date = h.data)
   AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a
                     WHERE a.employee_id::text = h.employee_id
                       AND a.motivo IN ('cobertura_de_ferias', 'cobertura_de_afastamento', 'cobertura_de_falta')
                       AND h.data BETWEEN a.data_inicio AND coalesce(a.data_fim, DATE '9999-12-31'))
"""
# um dia de HE de alguém que NÃO tem cobertura nem movimentação no dia — a fixture de (c) e (e)
SQL_DIA_SEM_PROVA = """
SELECT ts.employee_id, (x->>'date')::date AS dia,
       CASE WHEN (x->>'overtime_type') = '100' THEN 'he100' ELSE 'he50' END AS tipo
  FROM time_sheets ts, jsonb_array_elements(coalesce(ts.daily_summary, '[]'::jsonb)) x
 WHERE coalesce(ts.is_deleted, false) = false
   AND ts.reference_year = :a AND ts.reference_month = :m
   AND coalesce((x->>'overtime')::numeric, 0) > 0
   AND NOT EXISTS (SELECT 1 FROM substitutions s WHERE s.is_active
                     AND s.substitute_employee_id::text = ts.employee_id AND s.substitution_date = (x->>'date')::date)
   AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a
                     WHERE a.employee_id::text = ts.employee_id
                       AND a.motivo IN ('cobertura_de_ferias', 'cobertura_de_afastamento', 'cobertura_de_falta')
                       AND (x->>'date')::date BETWEEN a.data_inicio AND coalesce(a.data_fim, DATE '9999-12-31'))
 ORDER BY ts.employee_id, dia LIMIT 1
"""
SQL_LINHA = (
    "SELECT motivo, repassavel, cobertura_id::text, origem, horas FROM ponto_he_classificacao "
    "WHERE employee_id = :e AND data = :d AND tipo = :t"
)
SQL_COBERTURA_RECONTADA = """
SELECT s.reason, coalesce(s.cobertura_id, s.id)::text
  FROM substitutions s
 WHERE s.is_active AND s.substitute_employee_id::text = :e AND s.substitution_date = :d
 LIMIT 1
"""
SQL_FOLHA = """
SELECT count(*), coalesce(sum(total_earnings), 0), coalesce(sum(total_deductions), 0), coalesce(sum(net_salary), 0)
  FROM hr_payslips WHERE reference_year = :a AND reference_month = :m
"""
SQL_ESPELHO_HORAS = """
SELECT coalesce(sum(overtime_50_minutes), 0), coalesce(sum(overtime_100_minutes), 0)
  FROM time_sheets WHERE reference_year = :a AND reference_month = :m AND coalesce(is_deleted, false) = false
"""
SQL_POSTO_ATIVO = "SELECT id::text FROM posts WHERE is_active ORDER BY name LIMIT 1"
LIMPA = ("DELETE FROM substitutions WHERE notes LIKE :f",)


async def main() -> int:  # noqa: PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    try:
        from modules.people_management.ponto import he_classificacao as hc

        hc.levantar, hc.confirmar, hc.reclassificar, hc.resumo_por_contrato  # noqa: B018
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ (a–f) serviço da W3 não importa: {type(exc).__name__}: {exc}")
        print("TOTAL falhas W3 HE classificada: 1")
        return 1

    ano, mes = int(COMPETENCIA[:4]), int(COMPETENCIA[5:7])
    p_comp = {"a": ano, "m": mes}

    async def limpar(db) -> None:
        await db.rollback()
        for sql in LIMPA:
            try:
                await db.execute(text(sql), {"f": FIX + "%"})
            except Exception:  # noqa: BLE001
                await db.rollback()
        await db.commit()

    async with async_session_factory() as db:
        await hc._ensure(db)
        await limpar(db)

        folha_antes = (await db.execute(text(SQL_FOLHA), p_comp)).fetchone()
        espelho_antes = (await db.execute(text(SQL_ESPELHO_HORAS), p_comp)).fetchone()

        alvo = (await db.execute(text(SQL_DIA_SEM_PROVA), p_comp)).fetchone()
        try:
            # ── a. toda HE tem exatamente uma linha ──
            r1 = await hc.levantar(db, COMPETENCIA)
            esp = (await db.execute(text(SQL_HE_ESPELHO), p_comp)).fetchone()
            tab = (await db.execute(text(SQL_TABELA), {"c": COMPETENCIA})).fetchone()
            dup = (await db.execute(text(SQL_DUPLICADAS), {"c": COMPETENCIA})).scalar()
            ok(
                int(tab[0]) == int(esp[0]) and abs(float(tab[1]) - float(esp[1])) < 0.01,
                f"(a) linhas classificadas = HE do espelho: {tab[0]} == {esp[0]} · "
                f"horas {float(tab[1]):.2f} == {float(esp[1]):.2f}",
            )
            ok(dup == 0, f"(a) nenhuma tripla (pessoa, dia, tipo) repetida: {dup}")

            # ── b. idempotente ──
            r2 = await hc.levantar(db, COMPETENCIA)
            tab2 = (await db.execute(text(SQL_TABELA), {"c": COMPETENCIA})).fetchone()
            ok(
                r2["novas"] == 0 and int(tab2[0]) == int(tab[0]) and abs(float(tab2[1]) - float(tab[1])) < 0.01,
                f"(b) levantar 2×: novas={r2['novas']} (esperado 0) · linhas {tab[0]}→{tab2[0]} · "
                f"horas {float(tab[1]):.2f}→{float(tab2[1]):.2f} (1ª rodada criou {r1['novas']})",
            )

            # ── e. sem prova nenhuma → falta_de_efetivo NÃO repassável ──
            sem_prova = (await db.execute(text(SQL_REPASSAVEL_SEM_PROVA), {"c": COMPETENCIA})).scalar()
            ok(sem_prova == 0, f"(e) automáticas repassáveis sem cobertura nem movimentação: {sem_prova} (esperado 0)")
            if alvo:
                lin = (await db.execute(text(SQL_LINHA), {"e": alvo[0], "d": alvo[1], "t": alvo[2]})).fetchone()
                ok(
                    bool(lin) and lin[0] == "falta_de_efetivo" and lin[1] is False,
                    f"(e) HE sem cobertura/movimentação nasce: {lin[0] if lin else 'SEM LINHA'} "
                    f"repassável={lin[1] if lin else '?'} (esperado falta_de_efetivo / False)",
                )
            else:
                ok(False, "(e) fixture impossível: nenhum dia de HE sem cobertura/movimentação na competência")

            # ── f. resumo por contrato soma exatamente as linhas ──
            res = await hc.resumo_por_contrato(db, COMPETENCIA)
            soma_h = sum(r["horas_repassavel"] + r["horas_nao_repassavel"] for r in res)
            soma_r = sum(r["reais_repassavel"] + r["reais_nao_repassavel"] for r in res)
            reais_tab = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(h.horas), 0), coalesce(sum(h.horas * :f50 * coalesce(ts.hourly_rate, 0)) "
                        "  FILTER (WHERE h.tipo = 'he50'), 0) + coalesce(sum(h.horas * :f100 * coalesce(ts.hourly_rate, 0)) "
                        "  FILTER (WHERE h.tipo = 'he100'), 0) "
                        "  FROM ponto_he_classificacao h "
                        "  LEFT JOIN time_sheets ts ON ts.employee_id = h.employee_id "
                        "   AND ts.reference_year = :a AND ts.reference_month = :m AND coalesce(ts.is_deleted, false) = false "
                        " WHERE h.competencia = :c"
                    ),
                    {"c": COMPETENCIA, "f50": hc.FATOR["he50"], "f100": hc.FATOR["he100"], **p_comp},
                )
            ).fetchone()
            ok(
                abs(soma_h - float(reais_tab[0])) < 0.05,
                f"(f) horas do resumo == horas das linhas: {soma_h:.2f} == {float(reais_tab[0]):.2f} "
                f"({len(res)} contrato(s)/agrupamento(s))",
            )
            ok(
                abs(soma_r - float(reais_tab[1])) < 0.05,
                f"(f) R$ do resumo == R$ recontado das linhas: {soma_r:.2f} == {float(reais_tab[1]):.2f}",
            )

            # ── c. sugestão automática bate com a cobertura ──
            posto = (await db.execute(text(SQL_POSTO_ATIVO))).scalar()
            if alvo and posto:
                # coberto = alguém diferente (qualquer colaborador ativo que não seja o alvo)
                coberto = (
                    await db.execute(
                        text(
                            "SELECT id::text FROM employees WHERE status = 'ativo' AND id::text <> :e ORDER BY nome LIMIT 1"
                        ),
                        {"e": alvo[0]},
                    )
                ).scalar()
                await db.execute(
                    text(
                        "INSERT INTO substitutions (id, post_id, original_employee_id, substitute_employee_id, reason, "
                        " status, substitution_date, is_active, notes) VALUES "
                        " (gen_random_uuid(), CAST(:p AS uuid), CAST(:o AS uuid), CAST(:s AS uuid), 'vacation', "
                        "  'completed', :d, true, :n)"
                    ),
                    {"p": posto, "o": coberto, "s": alvo[0], "d": alvo[1], "n": FIX + " cobertura de férias"},
                )
                await db.execute(
                    text("DELETE FROM ponto_he_classificacao WHERE employee_id = :e AND data = :d"),
                    {"e": alvo[0], "d": alvo[1]},
                )
                await db.commit()
                await hc.levantar(db, COMPETENCIA)
                lin = (await db.execute(text(SQL_LINHA), {"e": alvo[0], "d": alvo[1], "t": alvo[2]})).fetchone()
                rec = (await db.execute(text(SQL_COBERTURA_RECONTADA), {"e": alvo[0], "d": alvo[1]})).fetchone()
                ok(
                    bool(lin) and lin[0] == "cobertura_ferias" and lin[1] is True,
                    f"(c) HE no dia de cobertura de férias → {lin[0] if lin else 'SEM LINHA'} "
                    f"repassável={lin[1] if lin else '?'} (esperado cobertura_ferias / True)",
                )
                ok(
                    bool(lin) and bool(rec) and lin[2] == rec[1],
                    f"(c) cobertura_id da linha == cobertura recontada por SQL ({rec[0] if rec else '?'}): "
                    f"{(lin[2] if lin else None)} == {(rec[1] if rec else None)}",
                )

                # ── d. confirmar não muda horas nem valor ──
                horas_antes = float(lin[4])
                n = await hc.confirmar(db, competencia=COMPETENCIA, quem="oráculo W3")
                lin2 = (await db.execute(text(SQL_LINHA), {"e": alvo[0], "d": alvo[1], "t": alvo[2]})).fetchone()
                ok(
                    n > 0 and abs(float(lin2[4]) - horas_antes) < 0.001 and lin2[0] == lin[0],
                    f"(d) confirmar {n} linha(s): horas {horas_antes:.2f} → {float(lin2[4]):.2f}, motivo intacto ({lin2[0]})",
                )
                folha_depois = (await db.execute(text(SQL_FOLHA), p_comp)).fetchone()
                delta = sum(abs(float(folha_depois[i]) - float(folha_antes[i])) for i in (1, 2, 3))
                ok(
                    int(folha_depois[0]) == int(folha_antes[0]) and delta < 0.005,
                    f"(d) paralelo cego na folha: {folha_antes[0]} holerite(s) em {COMPETENCIA}, Σ|Δ| = R$ {delta:.2f} (esperado 0,00)",
                )
                espelho_depois = (await db.execute(text(SQL_ESPELHO_HORAS), p_comp)).fetchone()
                ok(
                    tuple(int(v) for v in espelho_depois) == tuple(int(v) for v in espelho_antes),
                    f"(d) HE do espelho intacta: 50%={espelho_antes[0]}→{espelho_depois[0]} min · "
                    f"100%={espelho_antes[1]}→{espelho_depois[1]} min",
                )
            else:
                ok(False, "(c/d) fixture impossível: falta dia de HE livre ou posto ativo")
        finally:
            await limpar(db)
            # o (d) confirma a competência inteira em nome do oráculo — desfaz a assinatura
            await db.execute(
                text(
                    "UPDATE ponto_he_classificacao SET classificado_por = NULL, classificado_em = NULL "
                    "WHERE classificado_por = 'oráculo W3'"
                )
            )
            await db.commit()
            if alvo:
                await db.execute(
                    text("DELETE FROM ponto_he_classificacao WHERE employee_id = :e AND data = :d"),
                    {"e": alvo[0], "d": alvo[1]},
                )
                await db.commit()
                await hc.levantar(db, COMPETENCIA)  # devolve a linha ao estado sem prova
            sobras = (
                await db.execute(text("SELECT count(*) FROM substitutions WHERE notes LIKE :f"), {"f": FIX + "%"})
            ).scalar() or 0
            ok(sobras == 0, f"fixtures apagadas ao fim: {sobras} sobrando")

    print(f"TOTAL falhas W3 HE classificada: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
