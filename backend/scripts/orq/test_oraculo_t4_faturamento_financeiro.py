"""Oráculo — Faturamento/Financeiro, o que o DGX faz e aqui faltava (passagem T4, 24/09/2026).

Por que existe: cinco coisas que o DGX faz e o Conecta PRO não fazia, cada uma com o seu jeito de
mentir: um lembrete de cobrança que sai para quem não está na janela dos parâmetros (ou sai duas
vezes no dia), um OFX que entra duas vezes e duplica o saldo, uma agenda de caixa cujo saldo não
fecha com as contas, um recebível "proporcional" que muda o valor de quem começou no dia 1, e um
fechamento de comissões que vira DUAS contas a pagar.

O que afirma (um bloco por item):
  a) `_dgx_t4_faturamento_financeiro.telas()` devolve as 4 telas e cada uma tem aba em `_fin_grupos`.
  b) Cobrança por e-mail: com `financeiro.cobranca_dias_a_vencer_email=5` e `_vencidos_email=3`, os
     candidatos são EXATAMENTE os recebíveis em aberto que vencem em até 5 dias ou venceram há 3+ dias;
     quem vence em 10 dias ou venceu ontem fica de fora. O e-mail montado traz valor e vencimento.
     Nada é enviado (SMTP não é chamado).
  c) OFX: importar o MESMO arquivo duas vezes cria as transações UMA vez (external_id único por
     banco|conta|fitid); crédito entra positivo e débito negativo; a conta é reconhecida por BANKID/ACCTID.
  d) Agenda de caixa: para (dia D) saldo projetado = saldo dos bancos + Σ recebíveis em aberto com
     vencimento ≤ D − Σ pagáveis em aberto com vencimento ≤ D, recontado por SQL próprio.
  e) Recebível proporcional: `valor_proporcional()` dá 15/30 para contrato iniciado no dia 16 com base
     30; base vazia → valor cheio; mês inteiro coberto → valor cheio. PARALELO CEGO: com o parâmetro
     vazio (estado de produção), `gerar_recebiveis(preview)` soma exatamente Σ monthly_value dos
     contratos elegíveis, recontado por SQL — o valor de ninguém muda.
  f) Comissões → conta a pagar: gerar a conta de um fechamento cria UM pagável; gerar de novo é recusado
     e continua UM.

Estado medido no nascimento (sandbox 24/09/2026): módulo não existia → VERMELHO em tudo.
Fixtures marcadas 'FIXTURE DGX T4' (competência 2099-01 / FITID FIXTUREDGXT4) e apagadas ao fim,
inclusive em falha. Os dois parâmetros são restaurados ao valor que tinham.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from decimal import Decimal

FIX = "FIXTURE DGX T4"
P_AV, P_VE = "financeiro.cobranca_dias_a_vencer_email", "financeiro.cobranca_dias_vencidos_email"
COND = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL
<BANKACCTFROM><BANKID>403<ACCTID>7382527<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20990101<DTEND>20990131
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20990110<TRNAMT>1000.00<FITID>FIXTUREDGXT4-1<MEMO>FIXTURE DGX T4 credito</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20990112<TRNAMT>-500.00<FITID>FIXTUREDGXT4-2<MEMO>FIXTURE DGX T4 debito</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


async def _limpar(db) -> None:
    from sqlalchemy import text

    for sql in (
        "DELETE FROM receivable_accounts WHERE description LIKE :f",
        "DELETE FROM payable_accounts WHERE description LIKE :f OR description LIKE 'Comissões 01/2099%'",
        "DELETE FROM bank_transactions WHERE external_id LIKE 'ofx:%FIXTUREDGXT4%'",
        "DELETE FROM fin_comissoes_fechamentos WHERE competencia = '2099-01' AND fechado_por = :fx",
    ):
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%", "fx": FIX})
        except Exception:  # noqa: BLE001
            await db.rollback()
    await db.commit()


async def _rec(db, venc: date, valor: str, tag: str) -> str:
    from sqlalchemy import text

    return (
        await db.execute(
            text(
                "INSERT INTO receivable_accounts (id, condominio_id, description, customer_name, gross_value, net_value, "
                "issue_date, due_date, status, created_at, updated_at) VALUES (gen_random_uuid(), CAST(:c AS uuid), :d, :n, :v, :v, "
                "CURRENT_DATE, :due, 'pendente', now(), now()) RETURNING id::text"
            ),
            {"c": COND, "d": f"{FIX} {tag}", "n": f"{FIX} cliente", "v": valor, "due": venc},
        )
    ).scalar()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    total = 0

    try:
        from modules.operacional.controllers.redesign_builders import _dgx_t4_faturamento_financeiro as t4
        from modules.operacional.controllers.redesign_builders._fin_grupos import GRUPOS
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: módulo _dgx_t4_faturamento_financeiro não importa: {e}")
        print("TOTAL t4_faturamento_financeiro: 1 falha")
        return 1
    abas = {tid for _g, _t, _s, tabs in GRUPOS for tid, _l in tabs}

    async with async_session_factory() as db:
        await _limpar(db)
        antes = {
            k: (await db.execute(text("SELECT valor FROM system_configs WHERE chave=:c"), {"c": k})).scalar()
            for k in (P_AV, P_VE)
        }
        try:
            # a) telas + abas
            telas = await t4.telas(db, {})
            for tid in t4.IDS:
                total += 1
                if tid not in telas:
                    falhas.append(f"a) telas() não devolve '{tid}'")
                elif tid not in abas:
                    falhas.append(f"a) tela '{tid}' sem aba em _fin_grupos (tela sem porta não existe)")

            # b) cobrança por e-mail — janela pelos parâmetros
            from core.parametros import invalidar

            for k, v in ((P_AV, "5"), (P_VE, "3")):
                await db.execute(text("UPDATE system_configs SET valor=:v WHERE chave=:c"), {"v": v, "c": k})
            await db.commit()
            invalidar()
            hoje = date.today()
            r_in1 = await _rec(db, hoje + timedelta(days=3), "700.00", "vence em 3d")
            r_out1 = await _rec(db, hoje + timedelta(days=10), "701.00", "vence em 10d")
            r_in2 = await _rec(db, hoje - timedelta(days=5), "702.00", "venceu ha 5d")
            r_out2 = await _rec(db, hoje - timedelta(days=1), "703.00", "venceu ontem")
            await db.commit()
            cands = await t4.candidatos_cobranca(db)
            ids = {c["id"] for c in cands if FIX in (c.get("cliente") or "")}
            total += 1
            if ids != {r_in1, r_in2}:
                falhas.append(f"b) candidatos entre as fixtures = {ids}, esperado só {{3d a vencer, 5d vencido}}")
            total += 1
            est = {c["id"]: c["estagio"] for c in cands}
            if est.get(r_in1) != "a_vencer" or est.get(r_in2) != "vencido":
                falhas.append(f"b) estágio errado: {est.get(r_in1)} / {est.get(r_in2)}")
            total += 1
            item = next((c for c in cands if c["id"] == r_in2), None)
            assunto, html = t4.montar_email(item) if item else ("", "")
            if "702,00" not in html or (hoje - timedelta(days=5)).strftime("%d/%m/%Y") not in html:
                falhas.append("b) e-mail montado sem o valor R$ 702,00 ou sem o vencimento em DD/MM/AAAA")
            total += 1
            if r_out1 in ids or r_out2 in ids:
                falhas.append("b) quem vence em 10d ou venceu ontem NÃO pode estar na janela 5/3")

            # c) OFX idempotente
            r1 = await t4.importar_ofx(db, OFX, None, conciliar=False)
            r2 = await t4.importar_ofx(db, OFX, None, conciliar=False)
            n = (
                await db.execute(
                    text("SELECT count(*) FROM bank_transactions WHERE external_id LIKE 'ofx:%FIXTUREDGXT4%'")
                )
            ).scalar()
            total += 1
            if r1.get("inseridas") != 2 or r2.get("inseridas") != 0 or n != 2:
                falhas.append(
                    f"c) OFX 2× → inseridas {r1.get('inseridas')} e {r2.get('inseridas')}, no banco {n} (esperado 2, 0, 2)"
                )
            total += 1
            vals = dict(
                (
                    await db.execute(
                        text(
                            "SELECT external_id, amount FROM bank_transactions WHERE external_id LIKE 'ofx:%FIXTUREDGXT4%'"
                        )
                    )
                ).fetchall()
            )
            if {float(v) for v in vals.values()} != {1000.0, -500.0}:
                falhas.append(f"c) sinais errados: {vals}")
            total += 1
            conta = (
                (
                    await db.execute(
                        text(
                            "SELECT DISTINCT a.bank_code||'/'||a.account_number FROM bank_transactions t JOIN bank_accounts a ON a.id=t.bank_account_id "
                            "WHERE t.external_id LIKE 'ofx:%FIXTUREDGXT4%'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            if conta != ["403/7382527"]:
                falhas.append(f"c) conta reconhecida = {conta}, esperado 403/7382527")

            # d) agenda — saldo projetado recontado
            await _rec(db, date(2099, 1, 10), "100.00", "agenda entrada")
            await db.execute(
                text(
                    "INSERT INTO payable_accounts (id, condominio_id, description, gross_value, net_value, issue_date, due_date, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), CAST(:c AS uuid), :d, 40, 40, CURRENT_DATE, '2099-01-12', 'pendente', now(), now())"
                ),
                {"c": COND, "d": f"{FIX} agenda saida"},
            )
            await db.commit()
            ag = {r["dia"]: r for r in await t4.agenda_fluxo(db, 2099, 1)}
            total += 1
            if (
                float(ag.get(date(2099, 1, 10), {}).get("entradas", 0)) < 100
                or float(ag.get(date(2099, 1, 12), {}).get("saidas", 0)) < 40
            ):
                falhas.append("d) agenda não mostra a entrada de 10/01/2099 (100) ou a saída de 12/01/2099 (40)")
            esperado = (
                await db.execute(
                    text(
                        "SELECT coalesce((SELECT sum(current_balance) FROM bank_accounts WHERE ativo),0)"
                        " + coalesce((SELECT sum(net_value) FROM receivable_accounts WHERE due_date <= '2099-01-12' AND status NOT IN ('paga','cancelada','recebida')),0)"
                        " - coalesce((SELECT sum(net_value) FROM payable_accounts WHERE due_date <= '2099-01-12' AND status NOT IN ('pago','cancelado','cancelled','cancelada','baixada')),0)"
                    )
                )
            ).scalar()
            total += 1
            saldo = ag.get(date(2099, 1, 12), {}).get("saldo")
            if saldo is None or abs(Decimal(str(saldo)) - Decimal(str(esperado))) > Decimal("0.01"):
                falhas.append(f"d) saldo projetado em 12/01/2099 = {saldo}, recontado = {esperado}")

            # e) proporcional — regra pura + paralelo cego
            from modules.financial.services.receivable_contract_service import gerar_recebiveis, valor_proporcional

            total += 1
            v = valor_proporcional(Decimal("3000"), date(2026, 9, 16), None, date(2026, 9, 1), date(2026, 9, 30), 30)
            if v != Decimal("1500.00"):
                falhas.append(f"e) contrato iniciado dia 16, base 30 → {v} (esperado 1500.00)")
            total += 1
            if valor_proporcional(
                Decimal("3000"), date(2026, 9, 16), None, date(2026, 9, 1), date(2026, 9, 30), None
            ) != Decimal("3000"):
                falhas.append("e) base vazia tem de devolver o valor cheio")
            total += 1
            if valor_proporcional(
                Decimal("3000"), date(2026, 1, 1), None, date(2026, 10, 1), date(2026, 10, 31), 30
            ) != Decimal("3000"):
                falhas.append("e) mês inteiro coberto (31 dias, base 30) tem de devolver o valor cheio")
            total += 1
            if valor_proporcional(
                Decimal("3000"), date(2026, 1, 1), date(2026, 9, 10), date(2026, 9, 1), date(2026, 9, 30), 30
            ) != Decimal("1000.00"):
                falhas.append("e) contrato encerrado dia 10 → 10/30")
            base_prod = (
                await db.execute(
                    text(
                        "SELECT nullif(trim(valor),'') FROM system_configs WHERE chave='fiscal.nfse_valor_proporcional_dias'"
                    )
                )
            ).scalar()
            total += 1
            if base_prod:
                falhas.append(
                    f"e) parâmetro fiscal.nfse_valor_proporcional_dias = {base_prod} neste banco — o paralelo cego só vale com ele vazio"
                )
            else:
                prev = gerar_recebiveis(hoje.month, hoje.year, preview=True)
                soma_sql = (
                    await db.execute(
                        text(
                            "SELECT coalesce(sum(c.monthly_value),0) FROM contracts c WHERE c.status='active' AND coalesce(c.monthly_value,0)>0 "
                            "AND c.start_date <= :u AND (c.end_date IS NULL OR c.end_date >= :p) "
                            "AND NOT EXISTS (SELECT 1 FROM receivable_accounts r WHERE r.code = 'REC-'||left(c.id::text,8)||'-'||:am)"
                        ),
                        {
                            "u": date(hoje.year, hoje.month, 28),
                            "p": date(hoje.year, hoje.month, 1),
                            "am": f"{hoje.year}{hoje.month:02d}",
                        },
                    )
                ).scalar()
                if abs(Decimal(str(prev.get("valor_total", 0))) - Decimal(str(soma_sql))) > Decimal("0.01"):
                    falhas.append(f"e) paralelo cego: gerar_recebiveis soma {prev.get('valor_total')} ≠ SQL {soma_sql}")

            # f) comissões → conta a pagar, uma vez só
            import core.models  # noqa: F401
            import modules.clients.models  # noqa: F401
            import modules.financial.models  # noqa: F401

            uid = (await db.execute(text("SELECT id FROM users WHERE email='jjesus@conectamais.pro'"))).scalar()
            fid = (
                await db.execute(
                    text(
                        "INSERT INTO fin_comissoes_fechamentos (competencia, seller_id, qtd, total, fechado_por) "
                        "VALUES ('2099-01', :s, 1, 123.45, :p) RETURNING id"
                    ),
                    {"s": uid, "p": FIX},
                )
            ).scalar()
            await db.commit()
            await t4.gerar_conta_comissoes(db, int(fid), uid)
            recusou = False
            try:
                await t4.gerar_conta_comissoes(db, int(fid), uid)
            except ValueError:
                recusou = True
                await db.rollback()
            n = (
                await db.execute(
                    text("SELECT count(*) FROM payable_accounts WHERE description LIKE 'Comissões 01/2099%'")
                )
            ).scalar()
            total += 1
            if n != 1 or not recusou:
                falhas.append(f"f) gerar conta 2× → {n} pagável(is), recusou={recusou} (esperado 1, True)")
        except Exception as e:  # noqa: BLE001 — exceção é vermelho explicado, não traceback mudo no finally
            import traceback

            traceback.print_exc()
            falhas.append(f"EXCEÇÃO: {e!r}"[:300])
        finally:
            await db.rollback()
            for k, v in antes.items():
                await db.execute(text("UPDATE system_configs SET valor=:v WHERE chave=:c"), {"v": v, "c": k})
            await db.commit()
            invalidar()
            await _limpar(db)

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL t4_faturamento_financeiro: {total} checagens · {len(falhas)} falha(s)")
    if not falhas:
        print(
            "OK t4: telas com porta, janela de cobrança pelos parâmetros, OFX sem duplicar, agenda fecha com as contas, proporcional cego, comissão vira uma conta só"
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
