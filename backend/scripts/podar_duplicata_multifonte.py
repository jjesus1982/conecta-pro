#!/usr/bin/env python3
"""Remove a CÓPIA excedente de transações importadas duas vezes — adjudicada contra o banco.

## Por que existe

Em 11/08/2026 houve uma limpeza de duplicatas do Inter (as tabelas `backup_inter_*_20260811`
guardam 321 transações e 293 lançamentos removidos). Ela deduplicava exigindo **descrição
idêntica**, e a mesma transação vinda do CSV e da API tem texto diferente:

    Pagamento efetuado: "FULL TELECOM LTDA     ← CSV
    PAGAMENTO DE TITULO - FULL TELECOM LTDA    ← API

Sobreviveram 73 grupos. Ficaram invisíveis porque a checagem de duplicata do oráculo exige
favorecido preenchido, e essas cópias vinham sem nome — até 26/09/2026, quando a
conciliação passou a nomear 545 transações.

## A adjudicação, que é o que autoriza apagar

A regra da casa é conferir contra o BANCO antes de apagar. Já se apagou um pagamento
achando que era duplicata, e o saldo denunciou com a diferença exata de R$ 32,00.

A conferência NÃO depende da API (que devolveu 503 em 26/09): `inter_transactions` é a
tabela crua da ponte e guarda o payload que o banco mandou. Cobre de 06/03/2026 em diante,
e todos os grupos afetados são de 23/03 a 28/07.

Duas travas, e a poda só age onde as duas passam:

 1. **contagem por valor no dia**, que é o método que o oráculo prescreve: para o dia e o
    valor do grupo, quantas linhas o banco tem contra quantas temos;
 2. **teto por dia**: nunca apagar mais do que `nosso − banco` naquele dia.

Mantém-se a linha COM `external_id` (a que o índice único reconhece); no empate, a mais
antiga. Tudo o que sai vai para `backup_dup_multifonte_<AAAAMMDD>`, transação e lançamento,
antes do DELETE — mesmo padrão de 11/08.

## O que ele fez em 26/09/2026

    73 grupos · teto por dia autorizou 67 · R$ 5.069,00
    67 transações e 67 lançamentos removidos, backup em
      backup_dup_multifonte_20260926 / backup_dup_multifonte_lanc_20260926
    sobraram 6 grupos — o banco confirma ter aquelas linhas, e o teto os protegeu

Depois disso as competências 04 a 07, que já estavam apuradas, ficaram com resíduo aberto
(a soma exata do que saiu: 405,00 + 2.198,00 + 2.114,00 + 352,00 = R$ 5.069,00). Reapuradas,
o balanço voltou a fechar e o resultado de 2026 foi de −R$ 208.231,49 para −R$ 203.875,99.

**Apagar sem reapurar deixa o balanço mentindo.** As duas coisas são o mesmo trabalho.

    python3 podar_duplicata_multifonte.py            # ensaio
    python3 podar_duplicata_multifonte.py --aplicar
"""

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")
APLICAR = "--aplicar" in sys.argv
SUFIXO = date.today().strftime("%Y%m%d")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    async with async_session_factory() as db:
        conta = (await db.execute(text(
            "SELECT id::text FROM bank_accounts WHERE bank_name ILIKE '%inter%' LIMIT 1"
        ))).scalar()
        if not conta:
            print("RECUSO: conta do Inter não encontrada")
            return 2

        cob = (await db.execute(text(
            "SELECT min(data_lancamento), max(data_lancamento) FROM inter_transactions"
        ))).first()
        print(f"cobertura da tabela crua do banco (`inter_transactions`): {cob[0]} a {cob[1]}")

        grupos = (await db.execute(text("""
            SELECT transaction_date d, amount a, unaccent(upper(counterparty_name)) n,
                   count(*) nossas
              FROM bank_transactions
             WHERE coalesce(counterparty_name, '') <> '' AND bank_account_id = CAST(:c AS uuid)
             GROUP BY 1, 2, 3
            HAVING count(DISTINCT coalesce(imported_from, origin, '?')) > 1
             ORDER BY 1"""), {"c": conta})).all()
        print(f"grupos multi-fonte: {len(grupos)}")

        fora_da_cobertura = [g for g in grupos if not (cob[0] <= g[0] <= cob[1])]
        if fora_da_cobertura:
            print(f"  {len(fora_da_cobertura)} FORA da cobertura do banco — não serão tocados")

        # ── trava 1: contagem por valor no dia ────────────────────────────────────────
        # ── trava 2: teto por dia ─────────────────────────────────────────────────────
        alvos, recusados = [], []
        teto_usado: dict[date, int] = {}
        for d, a, n, nossas in grupos:
            if not (cob[0] <= d <= cob[1]):
                recusados.append((d, a, n, nossas, "fora da cobertura do banco"))
                continue
            no_banco = (await db.execute(text(
                "SELECT count(*) FROM inter_transactions"
                " WHERE data_lancamento = :d AND abs(valor) = abs(:a)"
            ), {"d": d, "a": float(a)})).scalar() or 0
            nosso_dia = (await db.execute(text(
                "SELECT count(*) FROM bank_transactions WHERE transaction_date = :d"
                "   AND abs(amount) = abs(:a) AND bank_account_id = CAST(:c AS uuid)"
            ), {"d": d, "a": float(a), "c": conta})).scalar() or 0
            excesso_do_dia = nosso_dia - no_banco
            if excesso_do_dia <= 0:
                recusados.append((d, a, n, nossas, f"banco tem {no_banco}, nós {nosso_dia} — não é cópia"))
                continue
            podem = min(nossas - 1, excesso_do_dia - teto_usado.get((d, float(a)), 0))
            if podem <= 0:
                recusados.append((d, a, n, nossas, "teto do dia já consumido"))
                continue
            teto_usado[(d, float(a))] = teto_usado.get((d, float(a)), 0) + podem
            alvos.append((d, a, n, nossas, podem, no_banco, nosso_dia))

        ids = []
        for d, a, n, _nossas, podem, _nb, _nd in alvos:
            linhas = (await db.execute(text("""
                SELECT id::text, coalesce(external_id, '') ext, created_at, imported_from
                  FROM bank_transactions
                 WHERE transaction_date = :d AND amount = :a AND bank_account_id = CAST(:c AS uuid)
                   AND unaccent(upper(counterparty_name)) = :n
                 ORDER BY (coalesce(external_id, '') = '') ASC, created_at ASC"""),
                {"d": d, "a": float(a), "c": conta, "n": n})).all()
            # mantém a primeira (com external_id, mais antiga); os próximos `podem` saem
            ids.extend([r[0] for r in linhas[1 : 1 + podem]])

        lanc = (await db.execute(text(
            "SELECT count(*), coalesce(round(sum(valor), 2), 0) FROM accounting_entries"
            " WHERE bank_transaction_id::text = ANY(:i)"
        ), {"i": ids})).first() if ids else (0, 0)

        print(f"\nA PODAR: {len(ids)} transação(ões) · {lanc[0]} lançamento(s) · R$ {float(lanc[1]):,.2f}")
        print(f"RECUSADOS pelas travas: {len(recusados)}")
        for r in recusados[:6]:
            print(f"   {r[0]}  R$ {abs(float(r[1])):>9,.2f}  {r[2][:24]:<24} {r[4]}")
        for g in alvos[:6]:
            print(f"   podar {g[4]}x  {g[0]}  R$ {abs(float(g[1])):>9,.2f}  {g[2][:26]:<26}"
                  f" (banco {g[5]} × nosso {g[6]} naquele dia/valor)")

        if not APLICAR:
            print("\nENSAIO — nada apagado. Rode com --aplicar.")
            return 0
        if not ids:
            print("\nnada a podar.")
            return 0

        await db.execute(text(
            f"CREATE TABLE IF NOT EXISTS backup_dup_multifonte_{SUFIXO} AS"
            " SELECT * FROM bank_transactions WHERE FALSE"))
        await db.execute(text(
            f"CREATE TABLE IF NOT EXISTS backup_dup_multifonte_lanc_{SUFIXO} AS"
            " SELECT * FROM accounting_entries WHERE FALSE"))
        await db.execute(text(
            f"INSERT INTO backup_dup_multifonte_lanc_{SUFIXO}"
            " SELECT * FROM accounting_entries WHERE bank_transaction_id::text = ANY(:i)"), {"i": ids})
        await db.execute(text(
            f"INSERT INTO backup_dup_multifonte_{SUFIXO}"
            " SELECT * FROM bank_transactions WHERE id::text = ANY(:i)"), {"i": ids})
        n_l = (await db.execute(text(
            "DELETE FROM accounting_entries WHERE bank_transaction_id::text = ANY(:i)"), {"i": ids})).rowcount
        n_t = (await db.execute(text(
            "DELETE FROM bank_transactions WHERE id::text = ANY(:i)"), {"i": ids})).rowcount
        await db.commit()
        print(f"\nAPLICADO: {n_t} transação(ões) e {n_l} lançamento(s) removidos.")
        print(f"Backup em backup_dup_multifonte_{SUFIXO} e backup_dup_multifonte_lanc_{SUFIXO}.")
        return 0


raise SystemExit(asyncio.run(main()))
