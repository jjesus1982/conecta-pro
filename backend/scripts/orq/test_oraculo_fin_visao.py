#!/usr/bin/env python3
"""Visão financeira do redesign (tela `projecao`, grupo Visão Geral): os KPIs batem com o banco.

Nasceu na 2ª passada do Financeiro (07/09/2026): 29 telas do módulo sem nenhum vigia, e a
Visão Geral é a primeira que o dono abre. A regra, não a fotografia:

  · "Base recorrente (MRR)"  == soma de contracts.monthly_value dos contratos ATIVOS
                               (verdade independente: o contrato, não o forecast)
  · "Saldo atual"            == bank_accounts.current_balance da CONTA PRINCIPAL (077 Inter;
                               a primeira versão somava Cora junto e acusava 1.579 × 13.625)
  · médias de 90 dias        == médias dos 3 meses COMPLETOS anteriores em bank_transactions,
                               sem transferências (recalculadas aqui; tolerância de 5%)

Sem escrita. Roda: docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fin_visao.py
"""
import asyncio
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")
import main_production  # noqa: E402,F401 — primeiro, sempre

from _fixtures import tela  # noqa: E402


def _num(txt: str) -> Decimal:
    t = re.sub(r"[^\d,.-]", "", str(txt or "")).replace(".", "").replace(",", ".")
    return Decimal(t or "0")


async def main() -> None:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.operacional.controllers.redesign_builders.financeiro import build

    falhas = []
    async with async_session_factory() as db:
        scr = tela(await build(db), "projecao")
        assert isinstance(scr, dict) and scr.get("kpis"), "tela 'projecao' sem KPIs"
        kpi = {k["l"]: _num(k["v"]) for k in scr["kpis"]}
        mrr_banco = Decimal(str((await db.execute(text(
            "SELECT coalesce(sum(monthly_value),0) FROM contracts WHERE status='active'"))).scalar() or 0))
        saldo_banco = Decimal(str((await db.execute(text(
            "SELECT coalesce(current_balance,0) FROM bank_accounts WHERE bank_code = '077'"))).scalar() or 0))
        ent, sai = (await db.execute(text(
            "SELECT coalesce(sum(amount) FILTER (WHERE amount>0),0), coalesce(-sum(amount) FILTER (WHERE amount<0),0) "
            # a mesma janela do builder: "últimos 90 dias (MESES COMPLETOS)" — os 3 meses
            # fechados antes do atual, não 90 dias corridos (a diferença dava 5,8% em 07/09)
            "FROM bank_transactions WHERE transaction_date >= date_trunc('month', current_date) - interval '3 months' "
            "  AND transaction_date < date_trunc('month', current_date) AND NOT coalesce(is_transfer,false)"))).one()
        med_ent, med_sai = Decimal(str(ent)) / 3, Decimal(str(sai)) / 3

    def cmp(rotulo, tela_v, banco_v, tol=Decimal("0.01")):
        if banco_v == 0 and tela_v == 0:
            print(f"OK {rotulo}: 0 nos dois lados"); return
        dif = abs(tela_v - banco_v) / (abs(banco_v) or Decimal("1"))
        (print if dif <= tol else falhas.append)(f"{'OK' if dif <= tol else 'FALHOU'} {rotulo}: tela {tela_v:,.2f} × banco {banco_v:,.2f}")
    cmp("MRR (contratos ativos)", kpi.get("Base recorrente (MRR)", Decimal(0)), mrr_banco)
    cmp("saldo atual (conta principal 077)", kpi.get("Saldo atual (conta principal)", Decimal(0)), saldo_banco)
    cmp("média entradas 90d", kpi.get("Média entradas/mês (90d)", Decimal(0)), med_ent, Decimal("0.05"))
    cmp("média saídas 90d", kpi.get("Média saídas/mês (90d)", Decimal(0)), med_sai, Decimal("0.05"))
    for f in falhas:
        print(f)
    assert not falhas, f"{len(falhas)} KPI(s) da visão financeira divergem do banco"
    print("TEST oraculo_fin_visao PASS")


if __name__ == "__main__":
    asyncio.run(main())
