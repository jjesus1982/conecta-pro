"""Quanto do dinheiro NASCEU no sistema — a métrica do padrão de uso.

Meta do Jordan (2026-08-11): *"precisamos de um padrão, tudo que entra e sai das
nossas contas tem que passar pelo sistema"*. Isto é o termômetro dele.

A distinção que a métrica mede: hoje o Conecta PRO é um **escriturário** — anota
depois, e anota certo (razão = extrato = banco, provado ao centavo). O que falta é
ser a **PORTA**: nada sai sem ter nascido aqui como um pagável. São coisas
diferentes, e só a segunda dá "cada centavo".

Ponto de partida medido em 11/08/2026, período aberto: **0 de 175 saídas
vinculadas a um pagável**. E o motivo é DIFERENTE por família — por isso o número
sozinho não serve, tem que vir com o mapa:

  salario        51 saídas R$79.090,55 — 1 pagável de folha ↔ 51 PIX (1:N)
  socio           4 saídas R$20.800,00 — não existe pagável
  pj_prolabore   14 saídas R$14.351,56 — não existe pagável
  fornecedor     24 saídas R$ 9.853,98 — pagável existe, vencimento fora da janela
  diaristas_vtvr 45 saídas R$ 1.440,00 — não existe pagável

Forçar um match 1:1 sobre isso seria fabricar vínculo. O caminho é criar o
pagável na origem, família por família.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.services.periodo_contabil import CORTE_CONTABIL

# Uma saída "nasceu no sistema" quando há um pagável dos dois lados da relação:
#   1:1  o pagável aponta para a saída  (`payable_accounts.transacao_bancaria_id`)
#   N:1  a saída aponta para o pagável  (`bank_transactions.payable_payment_id`)
# A folha OBRIGA o N:1: existe UM pagável de folha e 51 PIX individuais. Ler só a
# direção 1:1 deixaria 59% do valor do mês invisível para sempre.
# `transacao_bancaria_id` é TEXT (drift de schema) — o cast é obrigatório, sem ele
# o Postgres recusa `uuid = text` e a métrica morre em vez de medir.
VINCULADA = ("(EXISTS (SELECT 1 FROM payable_accounts p "
             "         WHERE p.transacao_bancaria_id = bt.id::text) "
             " OR bt.payable_payment_id IS NOT NULL)")

# Medido em 11/08: acima deste valor há exatamente 2 saídas sem pagável no
# período aberto (as duas para o sócio). Abaixo dele mora a folha — 51 PIX de
# salário que só serão cobertos quando o vínculo 1:N existir; alarmar neles hoje
# seria 51 avisos por mês que ninguém pode resolver.
LIMIAR_SAIDA_SEM_ORIGEM = 5000.00


async def medir(db: AsyncSession, desde: date | None = None) -> dict:
    """Cobertura do período ABERTO, com o mapa por categoria."""
    ini = desde or CORTE_CONTABIL
    tot = (await db.execute(text(f"""
        SELECT count(*) AS n, coalesce(sum(abs(amount)), 0) AS valor,
               count(*) FILTER (WHERE {VINCULADA}) AS vinculadas,
               coalesce(sum(abs(amount)) FILTER (WHERE {VINCULADA}), 0) AS valor_vinculado
        FROM bank_transactions bt
        WHERE bt.amount < 0 AND bt.transaction_date >= :ini
    """), {"ini": ini})).mappings().first()

    linhas = (await db.execute(text(f"""
        SELECT coalesce(bt.justificativa_categoria, '(sem classificar)') AS categoria,
               count(*) AS n, coalesce(sum(abs(amount)), 0) AS valor,
               count(*) FILTER (WHERE {VINCULADA}) AS vinculadas
        FROM bank_transactions bt
        WHERE bt.amount < 0 AND bt.transaction_date >= :ini
        GROUP BY 1 ORDER BY 3 DESC
    """), {"ini": ini})).mappings().all()

    n = int(tot["n"] or 0)
    vinc = int(tot["vinculadas"] or 0)
    valor = float(tot["valor"] or 0)
    valor_vinc = float(tot["valor_vinculado"] or 0)
    return {
        "desde": str(ini),
        "saidas": n,
        "vinculadas": vinc,
        "pct_por_linha": round(100 * vinc / n, 1) if n else 0.0,
        "valor": round(valor, 2),
        "valor_vinculado": round(valor_vinc, 2),
        "pct_por_valor": round(100 * valor_vinc / valor, 1) if valor else 0.0,
        "por_categoria": [
            {"categoria": r["categoria"], "saidas": int(r["n"]),
             "valor": round(float(r["valor"]), 2), "vinculadas": int(r["vinculadas"])}
            for r in linhas
        ],
    }
