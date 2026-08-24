"""Dedup do extrato Inter por CONTAGEM: aceita gêmeo, recusa duplicata.

O problema real, medido em 13/08/2026: `uq_inter_transactions_dedup` é UNIQUE em
(data, tipo, valor, descrição). Dois PIX de R$32,00 para a MESMA pessoa no MESMO
dia são indistinguíveis nessa chave, e o `ON CONFLICT` descartava o segundo **em
silêncio** — 3 pagamentos sumiram de 11/08 e o oráculo do extrato pegou R$96,00
de diferença contra o saldo do próprio banco.

E não dá para usar o id do banco: `raw_payload->>'transaction_id'` está preenchido
em 2.771 linhas com UM único valor distinto (vazio).

A primeira tentativa de trocar por contagem DUPLICOU 49 linhas em produção e foi
revertida. Este teste existe porque aquela tentativa não tinha teste: ele roda o
laço do sync DUAS vezes sobre o mesmo extrato e exige que a segunda não mude nada.

Tudo em transação com ROLLBACK — não deixa rastro.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_dedup_inter_contagem.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

DIA = date(2099, 12, 31)  # data impossível: não colide com dado real
# ZZ FIXO na descrição: é por ela que a limpeza de ENTRADA acha o resíduo de uma execução que
# tenha commitado no meio (o caminho normal é rollback, mas rollback não roda em morte por
# sinal). ZZ ordena no fim de qualquer listagem de extrato.
DESC = "ZZTESTE DEDUP - PIX ENVIADO - Cp :00000000-Fulano de Tal"
#: Descrição anterior, varrida junto — trocar de marca sem varrer a antiga cria órfão novo.
DESCS_ANTIGAS = ("TESTE DEDUP - PIX ENVIADO - Cp :00000000-Fulano de Tal",)


async def _limpar_orfaos_de_entrada(db) -> int:
    """Apaga lançamento sintético que sobrou de execução sem saída. Por MARCA, nunca por id."""
    n = 0
    for d in (DESC, *DESCS_ANTIGAS):
        r = await db.execute(text(
            "DELETE FROM inter_transactions WHERE data_lancamento = CAST(:dia AS date) "
            "AND descricao = CAST(:d AS varchar)"), {"dia": DIA, "d": d})
        n += r.rowcount or 0
    if n:
        await db.commit()
    return n


async def _quantas(db) -> int:
    return int((await db.execute(text(
        "SELECT count(*) FROM inter_transactions "
        "WHERE data_lancamento = :d AND descricao = :s"), {"d": DIA, "s": DESC})).scalar() or 0)


async def _rodada(db, copias: int) -> None:
    """Simula o laço do sync sobre um extrato com `copias` linhas idênticas."""
    vistas = 0
    for _ in range(copias):
        vistas += 1
        await db.execute(text("""
            INSERT INTO inter_transactions
              (data_lancamento, tipo_operacao, tipo_transacao, valor, descricao, raw_payload)
            SELECT CAST(:d AS date), 'D', 'PIX', CAST(:v AS numeric), CAST(:s AS varchar),
                   CAST('{}' AS jsonb)
            WHERE (SELECT count(*) FROM inter_transactions
                    WHERE data_lancamento = CAST(:d AS date)
                      AND descricao = CAST(:s AS varchar)) < CAST(:vistas AS integer)
        """), {"d": DIA, "v": 32.0, "s": DESC, "vistas": vistas})


async def main() -> None:
    # ENTRADA, UMA VEZ, no começo — não dentro do helper de insert, que roda em laço:
    # lá ela apagava as linhas acumuladas entre as iterações e quebrava a própria dedup.
    async with async_session_factory() as _db:
        _orf = await _limpar_orfaos_de_entrada(_db)
    if _orf:
        print(f"entrada: {_orf} lançamento(s) órfão(s) removido(s)")
    falhas: list[str] = []
    async with async_session_factory() as db:
        try:
            # DDL no Postgres é transacional: derrubar a constraint aqui dentro e
            # dar rollback no fim testa o comportamento PÓS-migration sem aplicar
            # migration nenhuma. Sem isto o teste falha em (1) — que é o defeito
            # em si: a constraint impede o gêmeo legítimo.
            await db.execute(text("ALTER TABLE inter_transactions "
                                  "DROP CONSTRAINT IF EXISTS uq_inter_transactions_dedup"))

            # ── (1) gêmeo legítimo: a API mandou 3, o banco tem que ficar com 3 ──
            await _rodada(db, 3)
            n = await _quantas(db)
            if n != 3:
                falhas.append(f"gêmeo legítimo perdido: a API mandou 3 e o banco ficou com {n}")
            else:
                print("OK gêmeo legítimo aceito: 3 cópias idênticas viraram 3 linhas")

            # ── (2) REPROCESSAR o mesmo extrato não pode duplicar ────────────
            # É aqui que a primeira tentativa quebrou em produção: 49 linhas
            # duplicadas por rodar o sync mais de uma vez na mesma janela.
            await _rodada(db, 3)
            n2 = await _quantas(db)
            if n2 != 3:
                falhas.append(f"reprocessar duplicou: era 3 e virou {n2}")
            else:
                print("OK reprocessar é idempotente: segunda rodada não mudou nada")

            # ── (3) a API mandar MAIS depois: entra só a diferença ───────────
            await _rodada(db, 5)
            n3 = await _quantas(db)
            if n3 != 5:
                falhas.append(f"crescimento errado: a API passou a mandar 5 e o banco tem {n3}")
            else:
                print("OK crescimento incremental: 3 → 5 insere só as 2 que faltavam")

            # ── (4) a API mandar MENOS não apaga nada ───────────────────────
            # Janela menor devolve menos linhas; sumir com o que já foi visto
            # seria perder movimentação real.
            await _rodada(db, 2)
            n4 = await _quantas(db)
            if n4 != 5:
                falhas.append(f"janela menor apagou dado: tinha 5 e ficou {n4}")
            else:
                print("OK janela menor não apaga: segue com 5")
        finally:
            await db.rollback()

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        raise AssertionError(f"{len(falhas)} invariante(s) da dedup quebrada(s)")
    print("TEST dedup_inter_contagem PASS")


if __name__ == "__main__":
    asyncio.run(main())
