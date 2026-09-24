"""Oráculo — Financeiro/Faturamento, cadastros do DGX (frente F11, 24/09/2026).

Por que existe: o DGX tem sete cadastros pequenos que aqui viviam soltos ou não existiam
(condição de pagamento, conta fixa que GERA o título, CFOP/código de serviço, recibo de venda
numerado, fechamento de comissões, orçado × realizado por centro, pensionista como beneficiário).
Cada um tem um jeito próprio de mentir: gerar o título duas vezes, numerar recibo com buraco,
fechar o mesmo período duas vezes, mostrar um "realizado" que não fecha com o extrato, e um
desconto de pensão que existe sem ninguém para receber.

O que afirma (um bloco por item):
  a) `_dgx_f11_financeiro.telas()` existe, devolve as telas e cada uma tem aba em `_fin_grupos`.
  b) Condições: as 4 semeadas existem; `vencimentos()` conta os dias a partir da data-base
     (30/60 em 31/01 → 02/03 e 01/04) e `parcelas()` fecha o total ao centavo.
  c) Contas fixas: `gerar_titulos_do_mes` duas vezes na mesma competência cria UM título
     por custo (recontado em `payable_accounts` e no vínculo `fin_contas_fixas_geradas`).
  d) Recibos: dois emitidos em sequência recebem números consecutivos e a numeração não tem
     buraco (count == max − min + 1, por SQL).
  e) Fechamento: fechar um período cria `commission_payments` e marca `approved`; fechar de
     novo NÃO cria segundo pagamento nem segundo fechamento.
  f) Orçado × realizado: o "realizado" da tela para (centro, mês) é igual à soma das saídas
     classificadas do extrato recontada por SQL próprio; o desvio é orçado − realizado.
  g) Pensionistas: desconto de pensão sem beneficiário `tipo='pensionista'` vinculado é
     contado como "sem beneficiário"; ao cadastrar o beneficiário, a contagem cai.

Estado medido no nascimento (sandbox 24/09/2026): módulo não existia → VERMELHO em tudo.
Fixtures marcadas 'FIXTURE DGX F11' e apagadas ao fim (inclusive em falha).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date
from decimal import Decimal

FIX = "FIXTURE DGX F11"
COMP_FIX = "2099-01"  # competência que nenhum dado real ocupa


async def _limpar(db) -> None:
    from sqlalchemy import text

    for sql in (
        "DELETE FROM commission_payments WHERE commission_id IN (SELECT id FROM commissions WHERE description LIKE :f)",
        "DELETE FROM fin_comissoes_fechamentos WHERE competencia = :c",
        "DELETE FROM commissions WHERE description LIKE :f",
        "DELETE FROM payable_accounts WHERE id IN (SELECT payable_id FROM fin_contas_fixas_geradas g "
        "  JOIN financial_custos_recorrentes c ON c.id = g.custo_id WHERE c.descricao LIKE :f)",
        "DELETE FROM fin_contas_fixas_geradas WHERE custo_id IN (SELECT id FROM financial_custos_recorrentes WHERE descricao LIKE :f)",
        "DELETE FROM financial_custos_recorrentes WHERE descricao LIKE :f",
        "DELETE FROM fin_recibos WHERE referente_a LIKE :f",
        "DELETE FROM financial_orcamentos WHERE chave LIKE 'cc:%' AND updated_by = :fx",
        "DELETE FROM financial_beneficiarios WHERE nome LIKE :f",
        "DELETE FROM employee_deductions WHERE descricao LIKE :f",
    ):
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%", "c": COMP_FIX, "fx": FIX})
        except Exception:  # noqa: BLE001 — tabela pode não existir na 1ª rodada (vermelho)
            await db.rollback()
    await db.commit()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    total = 0

    # a) módulo + telas + abas
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f11_financeiro as f11
        from modules.operacional.controllers.redesign_builders._fin_grupos import GRUPOS
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: módulo _dgx_f11_financeiro não importa: {e}")
        print("TOTAL financeiro_cadastros: 1 falha")
        return 1
    abas = {tid for _g, _t, _s, tabs in GRUPOS for tid, _l in tabs}

    async with async_session_factory() as db:
        await _limpar(db)
        try:
            telas = await f11.telas(db, {})
            for tid in f11.IDS:
                total += 1
                if tid not in telas:
                    falhas.append(f"a) telas() não devolve '{tid}'")
                elif tid not in abas:
                    falhas.append(f"a) tela '{tid}' sem aba em _fin_grupos (tela sem porta não existe)")

            # b) condições de pagamento
            n = (await db.execute(text("SELECT count(*) FROM fin_condicoes_pagamento WHERE ativo"))).scalar()
            total += 1
            if (n or 0) < 4:
                falhas.append(f"b) esperava ≥ 4 condições semeadas, há {n}")
            total += 1
            v = f11.vencimentos([30, 60], date(2026, 1, 31))
            if v != [date(2026, 3, 2), date(2026, 4, 1)]:
                falhas.append(f"b) vencimentos 30/60 de 31/01/2026 = {v} (esperado 02/03 e 01/04)")
            total += 1
            p = f11.parcelas(Decimal("100.00"), 3, Decimal("0"))
            if sum(p) != Decimal("100.00") or len(p) != 3:
                falhas.append(f"b) parcelas(100, 3) = {p} — não fecha ao centavo")

            # c) contas fixas — idempotência (o serviço usa o ORM: carrega o metadata das FKs como o app faz)
            import core.models  # noqa: F401
            import modules.clients.models  # noqa: F401
            import modules.financial.models  # noqa: F401
            from modules.financial.services.contas_fixas import gerar_titulos_do_mes

            uid = (await db.execute(text("SELECT id FROM users WHERE email='jjesus@conectamais.pro'"))).scalar()
            cid = (
                await db.execute(
                    text(
                        "INSERT INTO financial_custos_recorrentes (categoria, descricao, valor, dia_vencimento, ativo, created_by) "
                        "VALUES ('fixo', :d, 123.45, 10, true, 'oraculo') RETURNING id"
                    ),
                    {"d": f"{FIX} conta fixa"},
                )
            ).scalar()
            await db.commit()
            r1 = await gerar_titulos_do_mes(db, COMP_FIX, uid)
            r2 = await gerar_titulos_do_mes(db, COMP_FIX, uid)
            n_pay = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM payable_accounts WHERE id IN "
                        "(SELECT payable_id FROM fin_contas_fixas_geradas WHERE custo_id=:c)"
                    ),
                    {"c": cid},
                )
            ).scalar()
            n_link = (
                await db.execute(text("SELECT count(*) FROM fin_contas_fixas_geradas WHERE custo_id=:c"), {"c": cid})
            ).scalar()
            total += 1
            if not (r1["criados"] >= 1 and r2["criados"] == 0 and n_pay == 1 and n_link == 1):
                falhas.append(
                    f"c) gerar 2× em {COMP_FIX}: criados {r1['criados']}/{r2['criados']}, títulos {n_pay}, vínculos {n_link}"
                )
            venc = (
                await db.execute(
                    text(
                        "SELECT due_date FROM payable_accounts WHERE id = (SELECT payable_id FROM fin_contas_fixas_geradas WHERE custo_id=:c)"
                    ),
                    {"c": cid},
                )
            ).scalar()
            total += 1
            if venc != date(2099, 1, 10):
                falhas.append(f"c) vencimento do título gerado = {venc} (esperado 10/01/2099)")

            # d) recibos numerados sem buraco
            n1 = await f11.emitir_recibo(
                db, {"cliente_nome": "Oráculo", "valor": "10,00", "referente_a": f"{FIX} um"}, "oraculo"
            )
            n2 = await f11.emitir_recibo(
                db, {"cliente_nome": "Oráculo", "valor": "20,00", "referente_a": f"{FIX} dois"}, "oraculo"
            )
            total += 1
            if n2 != n1 + 1:
                falhas.append(f"d) recibos consecutivos numerados {n1} e {n2}")
            buraco = (
                await db.execute(text("SELECT count(*) <> max(numero) - min(numero) + 1 FROM fin_recibos"))
            ).scalar()
            total += 1
            if buraco:
                falhas.append("d) numeração de recibos com buraco (count ≠ max − min + 1)")
            ext = f11.por_extenso(Decimal("1234.56"))
            total += 1
            if "mil" not in ext or "cinquenta e seis centavos" not in ext:
                falhas.append(f"d) valor por extenso de 1.234,56 = {ext!r}")

            # e) fechamento de comissões — não fecha duas vezes
            seller = uid
            for i in (1, 2):
                await db.execute(
                    text(
                        "INSERT INTO commissions (id, reference_number, seller_id, sale_value, sale_margin, commission_type, commission_rate, "
                        "base_commission, adjustments, final_commission, status, trigger, trigger_date, due_date, description, is_active, created_at, updated_at) "
                        "VALUES (:id, :ref, :s, 1000, 0, 'percentage', 5, 50, 0, 50, 'pending', 'on_first_payment', '2099-01-15', '2099-01-15', :d, true, now(), now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "ref": f"FIX-F11-{i}-{uuid.uuid4().hex[:6]}",
                        "s": seller,
                        "d": f"{FIX} comissão {i}",
                    },
                )
            await db.commit()
            f1 = await f11.fechar_comissoes(db, COMP_FIX, str(seller), "oraculo")
            try:
                f2 = await f11.fechar_comissoes(db, COMP_FIX, str(seller), "oraculo")
            except ValueError:
                f2 = {"qtd": 0}
            n_pag = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM commission_payments WHERE commission_id IN (SELECT id FROM commissions WHERE description LIKE :f)"
                    ),
                    {"f": f"%{FIX}%"},
                )
            ).scalar()
            n_fech = (
                await db.execute(
                    text("SELECT count(*) FROM fin_comissoes_fechamentos WHERE competencia=:c AND seller_id=:s"),
                    {"c": COMP_FIX, "s": seller},
                )
            ).scalar()
            st = (
                await db.execute(
                    text("SELECT array_agg(DISTINCT status) FROM commissions WHERE description LIKE :f"),
                    {"f": f"%{FIX}%"},
                )
            ).scalar()
            total += 1
            if not (
                f1["qtd"] == 2 and f2["qtd"] == 0 and n_pag == 2 and n_fech == 1 and list(st or []) == ["approved"]
            ):
                falhas.append(
                    f"e) fechar 2×: qtd {f1['qtd']}/{f2['qtd']}, pagamentos {n_pag}, fechamentos {n_fech}, status {st}"
                )

            # f) orçado × realizado — realizado recontado por SQL próprio
            mes_ref = (
                await db.execute(
                    text(
                        "SELECT to_char(max(transaction_date),'YYYY-MM') FROM bank_transactions WHERE amount<0 AND category='Folha'"
                    )
                )
            ).scalar()
            if mes_ref:
                await db.execute(
                    text(
                        "INSERT INTO financial_orcamentos (chave, valor, updated_by, updated_at) VALUES (:k, 999999, :u, now()) "
                        "ON CONFLICT (chave) DO UPDATE SET valor=999999, updated_by=:u"
                    ),
                    {"k": f"cc:Folha:{mes_ref}", "u": FIX},
                )
                await db.commit()
                real_sql = (
                    await db.execute(
                        text(
                            "SELECT round(coalesce(sum(-amount),0)::numeric,2) FROM bank_transactions WHERE amount<0 AND category='Folha' "
                            "AND to_char(transaction_date,'YYYY-MM')=:m"
                        ),
                        {"m": mes_ref},
                    )
                ).scalar()
                linhas = await f11.orcado_realizado(db)
                alvo = [x for x in linhas if x["centro"] == "Folha" and x["mes"] == mes_ref]
                total += 1
                if not alvo:
                    falhas.append(f"f) tela não traz a linha Folha/{mes_ref}")
                else:
                    a = alvo[0]
                    if Decimal(str(a["realizado"])) != Decimal(str(real_sql)):
                        falhas.append(f"f) realizado Folha/{mes_ref}: tela {a['realizado']} ≠ SQL {real_sql}")
                    if Decimal(str(a["orcado"])) != Decimal("999999") or Decimal(str(a["desvio"])) != Decimal(
                        "999999"
                    ) - Decimal(str(real_sql)):
                        falhas.append(f"f) orçado/desvio errados: {a}")
            else:
                print("f) sem saídas classificadas 'Folha' no extrato — bloco pulado")

            # g) pensão sem beneficiário
            emp = (
                await db.execute(text("SELECT id FROM employees WHERE status='ativo' ORDER BY nome LIMIT 1"))
            ).scalar()
            await db.execute(
                text(
                    "INSERT INTO employee_deductions (id, employee_id, tipo, descricao, valor, ativo, data_inicio, created_at, updated_at) "
                    "VALUES (:id, :e, 'pensao_alimenticia', :d, 300, true, '2099-01-01', now(), now())"
                ),
                {"id": str(uuid.uuid4()), "e": emp, "d": f"{FIX} pensão"},
            )
            await db.commit()
            antes = await f11.pensoes_sem_beneficiario(db)
            await db.execute(
                text(
                    "INSERT INTO financial_beneficiarios (nome, chave_pix, tipo_chave, cpf_cnpj, categoria, origem, tipo, employee_id, ativo) "
                    "VALUES (:n, :k, 'aleatoria', '00000000000', 'pessoa', 'manual', 'pensionista', :e, true)"
                ),
                {"n": f"{FIX} pensionista", "k": f"fix-f11-{uuid.uuid4().hex}", "e": emp},
            )
            await db.commit()
            depois = await f11.pensoes_sem_beneficiario(db)
            total += 1
            if not (antes >= 1 and depois == antes - 1):
                falhas.append(f"g) pensões sem beneficiário: antes {antes}, depois {depois} (esperado cair 1)")
        finally:
            await db.rollback()
            await _limpar(db)

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL financeiro_cadastros: {total} checagens · {len(falhas)} falha(s)")
    if falhas:
        return 1
    print(
        "OK financeiro_cadastros: telas com porta, condições contam certo, conta fixa não duplica, recibo sem buraco, "
        "fechamento único, realizado bate com o extrato, pensão sem beneficiário acusada"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
