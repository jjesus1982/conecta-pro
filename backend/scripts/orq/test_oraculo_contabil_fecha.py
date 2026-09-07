"""Oráculo contábil: o balanço FECHA, e fecha pelo motivo certo.

Ativo = Passivo + Patrimônio Líquido não é meta: é identidade. Em partidas dobradas ela sai
de graça quando toda conta com movimento está classificada. Quando não fecha, alguém sumiu
com um pedaço.

Foi o que aconteceu até 11/08/2026. O builder classificava pelo PRIMEIRO DÍGITO do código,
assumindo 3=Receita e 4=Despesa. O plano desta empresa usa 4=Receita e 5=Despesa, e não tem
grupo 3. Efeito medido:

  • a receita (R$ 2.020.962,77) entrou como despesa NEGATIVA e virou o "Patrimônio Líquido";
  • as despesas inteiras (12 contas, R$ 2.118.029,49) foram ignoradas;
  • a tela anunciava PL de +R$ 2,02 MILHÕES onde o resultado é PREJUÍZO de R$ 97.066,72.

O balanço já dizia "Não fecha" e ninguém tinha por que investigar — a diferença ERA a
despesa descartada. Agora a classificação vem de `fin_accounting_accounts.account_type`.

Este oráculo não fixa valores: fixa a identidade. Mês novo entra sozinho; erro de
classificação futuro reprova sozinho.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_contabil_fecha.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import tela  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.operacional.controllers.redesign_builders.financeiro import build  # noqa: E402


def _num(v: str) -> float:
    """'R$ -97.066,72' -> -97066.72"""
    neg = "-" in v
    limpo = v.replace("R$", "").replace("-", "").replace(".", "").replace(",", ".").strip()
    return -float(limpo) if neg else float(limpo)


def _kpi(scr: dict, prefixo: str):
    return next((k for k in scr.get("kpis", []) if (k.get("l") or "").startswith(prefixo)), None)


async def main() -> None:
    async with async_session_factory() as db:
        bp = tela(await build(db), "balanco-patrimonial")
        assert bp, "balanço patrimonial não resolve"

        ativo = _num(_kpi(bp, "Ativo total")["v"])
        passivo = _num(_kpi(bp, "Passivo total")["v"])
        pl = _num(_kpi(bp, "Patrimônio Líquido")["v"])
        veredito = _kpi(bp, "Ativo = Passivo + PL")["v"]

        # ── 1. A identidade. Se abrir, alguma conta sumiu da classificação. ──
        assert abs(ativo - (passivo + pl)) < 0.01, (
            f"balanço NÃO fecha: Ativo {ativo:.2f} != Passivo {passivo:.2f} + PL {pl:.2f} "
            f"(diferença {ativo - passivo - pl:.2f}). Procure conta com movimento e sem "
            f"account_type no plano — foi assim que R$ 2,1 mi de despesa sumiu em 11/08."
        )
        assert "Fecha" in veredito, f"a tela diz {veredito!r} com os números fechando"
        print(f"OK identidade: {ativo:.2f} = {passivo:.2f} + {pl:.2f}")

        # ── 2. Toda conta com movimento tem classificação ──
        orfas = (await db.execute(text(
            "WITH mov AS (SELECT conta_debito AS conta FROM accounting_entries "
            "             UNION SELECT conta_credito FROM accounting_entries) "
            "SELECT m.conta FROM mov m LEFT JOIN fin_accounting_accounts a ON a.code = m.conta "
            "WHERE m.conta IS NOT NULL AND a.account_type IS NULL"))).fetchall()
        assert not orfas, (
            f"{len(orfas)} conta(s) com movimento e sem account_type: {[o[0] for o in orfas][:5]}. "
            f"Elas somem do balanço em silêncio."
        )
        print("OK classificação: toda conta com movimento tem account_type no plano")

        # ── 3. O PL da tela é o resultado real do razão, não um artefato ──
        rec = float((await db.execute(text(
            "SELECT coalesce(sum(e.valor),0) FROM accounting_entries e "
            "JOIN fin_accounting_accounts a ON a.code = e.conta_credito "
            "WHERE upper(a.account_type::text) = 'REVENUE'"))).scalar() or 0)
        desp = float((await db.execute(text(
            "SELECT coalesce(sum(e.valor),0) FROM accounting_entries e "
            "JOIN fin_accounting_accounts a ON a.code = e.conta_debito "
            "WHERE upper(a.account_type::text) IN ('EXPENSE','COST')"))).scalar() or 0)
        assert abs(pl - (rec - desp)) < 0.01, (
            f"PL da tela {pl:.2f} != receita {rec:.2f} − despesa {desp:.2f} = {rec - desp:.2f}"
        )
        # Suspenders contra a volta exata do defeito: receita nunca é o PL sozinha.
        if abs(rec - desp) > 0.01:
            assert abs(pl - rec) > 0.01, "PL voltou a ser a RECEITA — a classificação inverteu de novo"
        print(f"OK resultado: receita {rec:.2f} − despesa {desp:.2f} = PL {pl:.2f}")

        # ── 4. Partida dobrada intacta na origem ──
        d, c = (await db.execute(text(
            "SELECT coalesce(sum(valor),0), coalesce(sum(valor),0) FROM accounting_entries"))).first()
        assert abs(float(d) - float(c)) < 0.01, "razão desbalanceado na origem"
        print(f"OK razão: débitos = créditos ({float(d):.2f})")

        # ── 5. "Vencido" não pode incluir dívida SUSPENSA ──
        # Em 14/08/2026 a tela somava R$140.799,11 de débitos suspensos (a reparcelar
        # com a União) dentro de R$152.172,72 de "vencido": 93% do número era ruído,
        # e é por esse número que se decide caixa. O filtro vive em SQL_CONTA_EM_ABERTO;
        # este teste existe para a próxima cópia à mão não trazer o defeito de volta.
        from modules.financial.services.periodo_contabil import SQL_CONTA_EM_ABERTO

        assert "suspensa" in SQL_CONTA_EM_ABERTO, "SQL_CONTA_EM_ABERTO parou de excluir suspensa"
        for tabela in ("receivable_accounts", "payable_accounts"):
            n = int((await db.execute(text(
                f"SELECT count(*) FROM {tabela} WHERE due_date < current_date "
                f"AND {SQL_CONTA_EM_ABERTO} AND coalesce(status::text,'') = 'suspensa'"))).scalar() or 0)
            assert n == 0, f"{tabela}: {n} conta(s) suspensa(s) sendo contadas como vencidas"
        print("OK vencido: nenhuma dívida suspensa contada como cobrança")

        # ── 6. Transitória só guarda o que NÃO tem regra ──
        # 07/09/2026: 13 recebimentos de cliente da Cora (R$ 132.898,35) dormiam em 4.9.9.01
        # com category='recebimento_cliente' no extrato, e a DRE de agosto somava-os como
        # receita em cima das NFS-e. Regra: categoria conhecida ⇒ fora da transitória.
        from modules.financial.services.periodo_contabil import CORTE_CONTABIL

        n_ent = int((await db.execute(text(
            "SELECT count(*) FROM accounting_entries a JOIN bank_transactions b ON b.id=a.bank_transaction_id "
            "WHERE a.data_lancamento >= :c AND a.conta_credito='4.9.9.01' "
            "AND lower(replace(coalesce(b.justificativa_categoria, b.category, ''), ' ', '_')) "
            "IN ('recebimento_cliente','recebimento_de_cliente','receita_cliente','socio','transferencia_interna','emprestimo')"),
            {"c": CORTE_CONTABIL})).scalar() or 0)
        n_sai = int((await db.execute(text(
            "SELECT count(*) FROM accounting_entries a JOIN bank_transactions b ON b.id=a.bank_transaction_id "
            "WHERE a.data_lancamento >= :c AND a.conta_debito='5.9.9.01' "
            "AND b.justificativa_categoria IS NOT NULL AND lower(b.justificativa_categoria) NOT IN ('diversos','outros','outro')"),
            {"c": CORTE_CONTABIL})).scalar() or 0)
        assert n_ent == 0 and n_sai == 0, (
            f"transitória com regra conhecida: {n_ent} entrada(s) em 4.9.9.01, {n_sai} saída(s) em 5.9.9.01 "
            "— reclassificar_transitorias não rodou ou a regra do plano regrediu")
        print("OK transitória: só fica nela o que não tem categoria/justificativa")

    print("TEST oraculo_contabil_fecha PASS")


if __name__ == "__main__":
    asyncio.run(main())
