"""Período contábil FECHADO não se altera sem deixar rastro.

Decisão do Jordan, implementada pelo T1 em 7e6eed09: de 01/08/2026 em diante a empresa opera
dentro do Conecta PRO; jan–jul foram vividos fora dele e reconciliar aquilo é arqueologia.
`extrato_para_razao` e `ledger_auto_service` RECUSAM escrever antes do corte.

Em 12/08/2026 eu passei por cima com `UPDATE` cru e reclassifiquei 184 lançamentos fechados.
O guard existia no caminho de escrita da aplicação; não existia no banco, e script nenhum
perguntou. Foi preciso o Jordan mandar consultar o T1 para a violação aparecer.

**Linha de base, não regra absoluta.** Quando este oráculo nasceu havia 4.109 lançamentos
fechados com `updated_at` posterior ao corte — a escrituração de jan–jul foi feita DEPOIS,
legitimamente, antes do corte existir. Um oráculo absoluto nasceria vermelho e seria
desligado na primeira semana. Então ele congela o passado e vigia o futuro: qualquer toque
NOVO em período fechado precisa ser explicado.

Se um toque legítimo acontecer, mova a linha de base de propósito — é ato auditável:
    UPDATE system_configs SET valor = '<ISO>' WHERE chave = 'contabil.corte_baseline';

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_periodo_fechado.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

CHAVE = "contabil.corte_baseline"

_SQL_BASELINE = """
    INSERT INTO system_configs (id, chave, valor, descricao, grupo)
    VALUES (gen_random_uuid(), :c, :v,
            'Instante a partir do qual alterar lançamento de período FECHADO é violação',
            'contabil')
    ON CONFLICT (chave) DO NOTHING
"""


async def main() -> None:
    async with async_session_factory() as db:
        corte = (await db.execute(text(
            "SELECT valor FROM system_configs WHERE chave = 'contabil.corte'"))).scalar()
        # asyncpg infere o tipo do bind pelo CAST e recusa string onde espera date.
        corte = date.fromisoformat(corte or os.getenv("CONECTA_CORTE_CONTABIL", "2026-08-01"))

        base = (await db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"),
                                 {"c": CHAVE})).scalar()
        if not base:
            # Primeira execução: congela o passado. O que já estava tocado fica perdoado, e a
            # vigilância começa agora.
            base = datetime.now(UTC).isoformat(timespec="seconds")
            await db.execute(text(_SQL_BASELINE), {"c": CHAVE, "v": base})
            await db.commit()
            perdoados = (await db.execute(text(
                "SELECT count(*) FROM accounting_entries WHERE data_lancamento < CAST(:corte AS date) "
                "AND updated_at > CAST(:corte AS timestamp)"), {"corte": corte})).scalar()
            print(f"OK linha de base criada em {base} — {perdoados} toque(s) anteriores perdoados")

        violacoes = (await db.execute(text(
            "SELECT count(*), min(data_lancamento)::text, max(updated_at)::text "
            "FROM accounting_entries "
            "WHERE data_lancamento < CAST(:corte AS date) AND updated_at > CAST(:base AS timestamptz)"),
            {"corte": corte, "base": datetime.fromisoformat(base)})).first()

        n = violacoes[0] or 0
        assert n == 0, (
            f"{n} lançamento(s) de período FECHADO (< {corte}) alterado(s) depois da linha de "
            f"base {base}. Mais antigo: {violacoes[1]}, último toque: {violacoes[2]}. "
            f"Jan–jul não se reconcilia — decisão do Jordan. Se o toque foi legítimo, mova a "
            f"linha de base explicitamente em system_configs, para o ato ficar auditável."
        )
        print(f"OK período fechado intacto desde {base} (corte {corte})")

        # Suspenders: a própria trava do código precisa continuar existindo. Sem ela, só este
        # oráculo separa o razão histórico de quem quiser reescrevê-lo — e ele roda 1x por dia.
        from modules.financial.services.periodo_contabil import periodo_fechado
        assert periodo_fechado(date(2026, 7, 31)), "guard do código parou de barrar julho"
        assert not periodo_fechado(date(2026, 8, 2)), "guard do código passou a barrar agosto"
        print("OK guard `periodo_fechado` continua no caminho de escrita")

    print("TEST oraculo_periodo_fechado PASS")


if __name__ == "__main__":
    asyncio.run(main())
