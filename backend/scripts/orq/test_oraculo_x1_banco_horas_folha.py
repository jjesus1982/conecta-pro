"""Oráculo — a ponte banco de horas × folha diz a verdade e não toca em dinheiro (DGX X1, 24/09/2026).

Por que existe: o banco de horas está completo no Operacional (`time_bank`, telas `banco-horas*`,
saldo, aprovação, compensação, vencimento) e **nunca conversou com a folha**. A W5 §7 mediu: dos 15
eventos que o DGX modela, o nosso motor produz 8, e dois dos que faltam são `banco_horas_credito` e
`banco_horas_debito`. Hora que vence sem ser paga nem compensada é passivo trabalhista (CLT art. 59
§3) e hoje ninguém a vê.

`banco_horas_conferencia` é a apuração dessa ponte, em PARALELO CEGO. Este oráculo é o que impede
a apuração de virar ficção — e, principalmente, o que prova que ela não mexe em folha.

O que afirma:
  (a) `apurar` é idempotente: rodar 2× na mesma competência não cria linha nova nem muda número;
  (b) `saldo_inicial`/`creditado`/`debitado`/`compensado` == recontados por SQL PRÓPRIO direto em
      `time_bank` (a fonte viva), não pelo serviço;
  (c) `ja_pago_como_he` == a soma das verbas de hora extra do holerite daquela competência,
      recontada por SQL próprio sobre `hr_payslips.earnings`;
  (d) **nenhuma linha de folha muda**: Σ|Δ| de `total_earnings + total_deductions + net_salary`
      sobre TODOS os `hr_payslips`, fotografado antes e depois do `apurar`, = R$ 0,00;
  (e) `vencido_no_periodo` nunca é negativo, e `a_pagar_por_vencimento` nunca é negativo;
  (f) fixture de crédito VENCIDO (`'FIXTURE DGX X1'`) aparece em `a_pagar_por_vencimento` com o
      valor CLT (horas × valor_hora × 1,5) — apagada ao fim, mesmo em falha;
  (g) fiação: `departamento_pessoal.build()` chama `_dgx_x1_banco_horas_folha.telas` e as três
      abas estão em `_dp_grupos` (tela sem porta não existe).

Zero por falta de dado ≠ zero por ausência de divergência: a linha de resumo conta a POPULAÇÃO
(pessoas apuradas, lançamentos no `time_bank`, horas medidas pelo espelho) antes de qualquer «0».

Estado medido no nascimento (sandbox = cópia de produção, 24/09/2026): `banco_horas_conferencia`
não existia e `banco_horas_folha` não importava → VERMELHO. `time_bank` com **0 linhas** em
produção E no sandbox: o banco de horas nunca recebeu um lançamento. O espelho de ponto, no
entanto, mediu **933,4 h de crédito** e **4.768,0 h de débito** em 7 competências de 2026 — horas
que existem no ponto, nunca entraram no banco e nunca foram pagas.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import date, timedelta
from decimal import Decimal

FIX = "FIXTURE DGX X1"
TOL = Decimal("0.01")

#: recontagem do ledger, por SQL PRÓPRIO (não importa nada do serviço)
SQL_LEDGER = """
SELECT employee_id::text,
  coalesce(sum(CASE WHEN reference_date < :ini AND entry_type IN ('credit','adjustment') THEN hours
                    WHEN reference_date < :ini AND entry_type IN ('debit','compensation','expiration') THEN -hours
                    ELSE 0 END), 0) AS saldo_inicial,
  coalesce(sum(CASE WHEN reference_date BETWEEN :ini AND :fim AND entry_type IN ('credit','adjustment')
                    THEN hours ELSE 0 END), 0) AS creditado,
  coalesce(sum(CASE WHEN reference_date BETWEEN :ini AND :fim AND entry_type = 'debit'
                    THEN hours ELSE 0 END), 0) AS debitado,
  coalesce(sum(CASE WHEN reference_date BETWEEN :ini AND :fim AND entry_type = 'compensation'
                    THEN hours ELSE 0 END), 0) AS compensado,
  coalesce(sum(CASE WHEN entry_type IN ('credit','adjustment') AND status <> 'used'
                     AND expiration_date BETWEEN :ini AND :fim THEN hours ELSE 0 END), 0) AS vencido
FROM time_bank
WHERE coalesce(is_active, true) AND status IN ('approved','used','expired')
GROUP BY 1
"""

#: recontagem da HE paga, por SQL PRÓPRIO sobre o holerite
SQL_HE_HOLERITE = """
SELECT p.employee_id::text, round(sum((e->>'valor')::numeric), 2)
FROM hr_payslips p, jsonb_array_elements(p.earnings) e
WHERE p.reference_year = :ano AND p.reference_month = :mes
  AND coalesce(p.status,'') <> 'cancelled' AND p.payslip_code NOT LIKE '13O-%'
  AND (e->>'descricao') ILIKE '%extra%'
GROUP BY 1
"""

#: a fotografia da folha — se UM centavo mudar, o paralelo cego deixou de ser cego
SQL_FOTO_FOLHA = """
SELECT coalesce(sum(coalesce(total_earnings,0) + coalesce(total_deductions,0)
                    + coalesce(net_salary,0)), 0), count(*)
FROM hr_payslips
"""


def _d(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _brl(v: Decimal) -> str:
    s = f"{v:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    return f"R$ {s}"


async def _corte_do_dono(db, falhas: list[str], resumo: list[str]) -> None:
    """(g) O corte declarado pelo DONO manda: competência quitada não vence e não é passivo.

    Jordan, 24/09/2026: «ninguém tem banco de horas nem valores a vencer porque eu já paguei
    tudo». Virou `banco_horas.corte_quitado` em `system_configs`. Esta afirmação existe para o
    número não ressuscitar sozinho no próximo «Apurar» — e para que, se alguém APAGAR o corte,
    apareça vermelho em vez de o passivo voltar calado.
    """
    from sqlalchemy import text as _t  # noqa: PLC0415

    from modules.people_management.folha.services import banco_horas_folha as bh  # noqa: PLC0415

    corte = await bh.corte_quitado(db)
    if corte is None:
        resumo.append("(g) corte do dono: NAO declarado — todo crédito volta a vencer")
        return
    resumo.append(f"(g) corte do dono: crédito até {corte:%d/%m/%Y} declarado QUITADO")
    ruim = (await db.execute(_t(
        "SELECT count(*) FROM banco_horas_conferencia "
        "WHERE competencia <= :c AND (vence_em IS NOT NULL OR a_pagar_por_vencimento <> 0)"), {"c": corte})).scalar() or 0
    if ruim:
        falhas.append(f"(g) {ruim} linha(s) de competência quitada ainda vencem ou cobram — corte não respeitado")
    n_q = (await db.execute(_t(
        "SELECT count(*) FROM banco_horas_conferencia WHERE competencia <= :c AND estado <> 'quitado_pelo_dono'"),
        {"c": corte})).scalar() or 0
    if n_q:
        falhas.append(f"(g) {n_q} linha(s) de competência quitada sem o estado `quitado_pelo_dono` (reapure)")


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    try:
        from modules.people_management.folha.services import banco_horas_folha as bh
    except Exception as exc:  # noqa: BLE001
        print(f"FALHOU: banco_horas_folha não importa: {type(exc).__name__}: {exc}")
        print("TOTAL desvios: 1")
        return 1

    async with async_session_factory() as db:
        await bh._ensure(db)

        # competência a apurar: a última do espelho de ponto (a fonte que tem dado)
        r = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM time_sheets "
                    "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                )
            )
        ).first()
        if not r:
            print("FALHOU: sem nenhuma linha em time_sheets — nada a apurar")
            print("TOTAL desvios: 1")
            return 1
        ano, mes = int(r[0]), int(r[1])
        # A fixture de crédito VENCIDO precisa viver DEPOIS do corte que o dono declarou quitado
        # (`banco_horas.corte_quitado`, 24/09/2026), senão a regra da CLT que ela prova é anulada
        # pelo próprio corte — e o oráculo passaria a exigir passivo onde o dono já pagou.
        from modules.people_management.folha.services import banco_horas_folha as _bh  # noqa: PLC0415

        _corte = await _bh.corte_quitado(db)
        if _corte and date(ano, mes, 1) <= _corte:
            ano, mes = (_corte.year + (_corte.month == 12), (_corte.month % 12) + 1)
        comp = f"{ano}-{mes:02d}"
        ini = date(ano, mes, 1)
        fim = date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)

        # população, ANTES de qualquer zero
        n_ledger = (await db.execute(text("SELECT count(*) FROM time_bank"))).scalar() or 0
        n_esp = (
            await db.execute(
                text("SELECT count(*) FROM time_sheets WHERE reference_year=:a AND reference_month=:m"),
                {"a": ano, "m": mes},
            )
        ).scalar() or 0

        # ── (f) fixture: crédito de 200 dias atrás, já vencido dentro da competência ───────
        emp = (
            await db.execute(
                text(
                    "SELECT id::text, coalesce(salario_base,0), coalesce(escala_padrao,'') "
                    "FROM employees WHERE coalesce(status,'')='ativo' AND coalesce(salario_base,0) > 0 "
                    "ORDER BY nome LIMIT 1"
                )
            )
        ).first()
        fix_id = None
        if emp:
            venc = fim - timedelta(days=1)
            await db.execute(
                text(
                    "INSERT INTO time_bank (id, employee_id, entry_type, status, hours, "
                    "  balance_before, balance_after, reference_date, expiration_date, "
                    "  description, is_active, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :e, 'credit', 'approved', 10, 0, 10, :ref, :venc, "
                    "  :desc, true, now(), now()) RETURNING id::text"
                ),
                {
                    "e": emp[0],
                    "ref": venc - timedelta(days=180),
                    "venc": venc,
                    "desc": FIX,
                },
            )
            await db.commit()
            fix_id = emp[0]

        try:
            foto_antes = (await db.execute(text(SQL_FOTO_FOLHA))).first()

            # ── (a) idempotência: apurar 2× ────────────────────────────────────────────────
            await bh.apurar(db, comp)
            n1 = (
                await db.execute(
                    text("SELECT count(*) FROM banco_horas_conferencia WHERE competencia=:c"),
                    {"c": ini},
                )
            ).scalar() or 0
            soma1 = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(creditado+debitado+compensado+vencido_no_periodo"
                        "+a_pagar_por_vencimento+ja_pago_como_he),0) "
                        "FROM banco_horas_conferencia WHERE competencia=:c"
                    ),
                    {"c": ini},
                )
            ).scalar()
            await bh.apurar(db, comp)
            n2 = (
                await db.execute(
                    text("SELECT count(*) FROM banco_horas_conferencia WHERE competencia=:c"),
                    {"c": ini},
                )
            ).scalar() or 0
            soma2 = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(creditado+debitado+compensado+vencido_no_periodo"
                        "+a_pagar_por_vencimento+ja_pago_como_he),0) "
                        "FROM banco_horas_conferencia WHERE competencia=:c"
                    ),
                    {"c": ini},
                )
            ).scalar()
            if n1 != n2:
                falhas.append(f"(a) apurar 2× mudou a contagem: {n1} → {n2}")
            if _d(soma1) != _d(soma2):
                falhas.append(f"(a) apurar 2× mudou os números: {_d(soma1)} → {_d(soma2)}")
            if n1 == 0:
                falhas.append(f"(a) apurar não gravou nenhuma linha em {comp} (espelho tem {n_esp})")

            linhas = (
                await db.execute(
                    text(
                        "SELECT employee_id::text, saldo_inicial, creditado, debitado, compensado, "
                        "vencido_no_periodo, a_pagar_por_vencimento, ja_pago_como_he, valor_hora "
                        "FROM banco_horas_conferencia WHERE competencia=:c"
                    ),
                    {"c": ini},
                )
            ).fetchall()
            por_emp = {x[0]: x for x in linhas}

            # ── (b) ledger recontado por SQL próprio ───────────────────────────────────────
            ledger = {x[0]: x for x in (await db.execute(text(SQL_LEDGER), {"ini": ini, "fim": fim})).fetchall()}
            for eid, lg in ledger.items():
                ln = por_emp.get(eid)
                if ln is None:
                    falhas.append(f"(b) {eid} tem lançamento no time_bank e não foi apurado")
                    continue
                for i, nome in ((1, "saldo_inicial"), (2, "creditado"), (3, "debitado"), (4, "compensado")):
                    if abs(_d(ln[i]) - _d(lg[i])) > TOL:
                        falhas.append(f"(b) {eid} {nome}: apurado {_d(ln[i])} × recontado {_d(lg[i])}")
                if abs(_d(ln[5]) - _d(lg[5])) > TOL:
                    falhas.append(f"(b) {eid} vencido_no_periodo: apurado {_d(ln[5])} × recontado {_d(lg[5])}")

            # ── (c) HE paga recontada do holerite ──────────────────────────────────────────
            he = {
                x[0]: _d(x[1]) for x in (await db.execute(text(SQL_HE_HOLERITE), {"ano": ano, "mes": mes})).fetchall()
            }
            for eid, ln in por_emp.items():
                esperado = he.get(eid, Decimal("0.00"))
                if abs(_d(ln[7]) - esperado) > TOL:
                    falhas.append(f"(c) {eid} ja_pago_como_he: apurado {_brl(_d(ln[7]))} × holerite {_brl(esperado)}")
            for eid in he:
                if eid not in por_emp:
                    falhas.append(f"(c) {eid} tem HE no holerite de {comp} e não foi apurado")

            # ── (e) nada negativo ──────────────────────────────────────────────────────────
            for eid, ln in por_emp.items():
                if _d(ln[5]) < 0:
                    falhas.append(f"(e) {eid} vencido_no_periodo negativo: {_d(ln[5])}")
                if _d(ln[6]) < 0:
                    falhas.append(f"(e) {eid} a_pagar_por_vencimento negativo: {_d(ln[6])}")

            # ── (f) a fixture vencida tem que aparecer a pagar ─────────────────────────────
            if fix_id:
                ln = por_emp.get(fix_id)
                if ln is None:
                    falhas.append("(f) a fixture com crédito vencido não foi apurada")
                else:
                    if _d(ln[5]) < Decimal("10.00"):
                        falhas.append(
                            f"(f) crédito vencido da fixture não entrou: vencido_no_periodo={_d(ln[5])} (esperado ≥ 10)"
                        )
                    vh = _d(ln[8])
                    esperado = (vh * _d(ln[5]) * Decimal("1.5")).quantize(Decimal("0.01"))
                    if vh > 0 and abs(_d(ln[6]) - esperado) > Decimal("0.05"):
                        falhas.append(
                            f"(f) a_pagar_por_vencimento {_brl(_d(ln[6]))} ≠ horas × valor_hora × 1,5 = {_brl(esperado)}"
                        )

            # ── (d) a folha NÃO mudou ──────────────────────────────────────────────────────
            foto_depois = (await db.execute(text(SQL_FOTO_FOLHA))).first()
            delta = abs(_d(foto_antes[0]) - _d(foto_depois[0]))
            if delta > Decimal("0.00"):
                falhas.append(f"(d) a folha MUDOU: Σ|Δ| = {_brl(delta)} — o paralelo deixou de ser cego")
            if foto_antes[1] != foto_depois[1]:
                falhas.append(f"(d) o número de holerites mudou: {foto_antes[1]} → {foto_depois[1]}")

            # ── (g) fiação ─────────────────────────────────────────────────────────────────
            try:
                # ORDEM IMPORTA (não deixe o isort reordenar): o builder do DP tem que entrar
                # ANTES da frente. Importar a frente primeiro faz o discovery do
                # `redesign_data_controller` carregar o `departamento_pessoal` no meio da
                # inicialização dela → import circular. O `safe_import` engole e segue, mas
                # imprime um aviso confuso. Vale para TODA `_dgx_*` (medido com a W3 em
                # 24/09/2026) — não é próprio da X1.
                from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp  # isort: skip
                from modules.operacional.controllers.redesign_builders import _dgx_x1_banco_horas_folha as x1  # isort: skip  # noqa: I001

                src = inspect.getsource(dp.build)
                if "_dgx_x1_banco_horas_folha" not in src and "_telas_x1" not in src:
                    falhas.append("(g) departamento_pessoal.build() não chama a frente X1")
                grupos = inspect.getsource(
                    __import__(
                        "modules.operacional.controllers.redesign_builders._dp_grupos",
                        fromlist=["_dp_grupos"],
                    )
                )
                for tid, _ in x1.ABAS:
                    if tid not in grupos:
                        falhas.append(f"(g) aba '{tid}' não está em _dp_grupos — tela sem porta")
            except Exception as exc:  # noqa: BLE001
                falhas.append(f"(g) fiação não verificável: {type(exc).__name__}: {exc}")

            # resumo — a população antes do zero
            tot_venc = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(vencido_no_periodo),0), coalesce(sum(a_pagar_por_vencimento),0), "
                        "coalesce(sum(ja_pago_como_he),0), coalesce(sum(saldo_ponto),0) "
                        "FROM banco_horas_conferencia WHERE competencia=:c"
                    ),
                    {"c": ini},
                )
            ).first()
            print(
                f"{mes:02d}/{ano} · {n1} pessoa(s) apurada(s) · time_bank: {n_ledger} lançamento(s) · "
                f"espelho: {n_esp} linha(s) · saldo do ponto: {_d(tot_venc[3])} h · "
                f"vencido: {_d(tot_venc[0])} h ({_brl(_d(tot_venc[1]))}) · "
                f"já pago como HE: {_brl(_d(tot_venc[2]))} · Σ|Δ| folha = {_brl(delta)}"
            )
        finally:
            await db.rollback()
            await db.execute(
                text("DELETE FROM time_bank WHERE coalesce(description,'') LIKE :f"),
                {"f": f"{FIX}%"},
            )
            await db.commit()
            if fix_id:
                # a conferência da fixture some junto (é derivada dela)
                await db.execute(
                    text(
                        "DELETE FROM banco_horas_conferencia WHERE employee_id = CAST(:e AS uuid) AND competencia = :c"
                    ),
                    {"e": fix_id, "c": ini},
                )
                await db.commit()

        n_fix = (
            await db.execute(
                text("SELECT count(*) FROM time_bank WHERE coalesce(description,'') LIKE :f"),
                {"f": f"{FIX}%"},
            )
        ).scalar() or 0
        if n_fix:
            falhas.append(f"(f) {n_fix} fixture(s) '{FIX}' não foram apagadas")

        # (g) o corte declarado pelo dono manda — fora do try/finally das fixtures
        _resumo_g: list[str] = []
        await _corte_do_dono(db, falhas, _resumo_g)
        for _r in _resumo_g:
            print(_r)

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na ponte banco de horas × folha")
    print(
        "OK banco de horas × folha: apuração idempotente, saldo == recontado no time_bank, "
        "HE == a do holerite, vencido ≥ 0, crédito vencido vira a pagar (CLT art. 59 §3), "
        "e nenhuma linha de folha mudou (Σ|Δ| = R$ 0,00)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
