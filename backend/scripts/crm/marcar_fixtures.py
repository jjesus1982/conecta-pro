#!/usr/bin/env python3
"""Marca registros de TESTE para saírem das listagens — sem apagar nada.

Dry-run é o padrão. `--aplicar` grava. Ver `modules/crm/services/fixtures.py` para a
decisão e o porquê de a marca ser coluna e não filtro de leitura.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from core.database import async_session_factory  # noqa: E402
from modules.crm.services import fixtures as fx  # noqa: E402


async def main(aplicar: bool) -> int:
    async with async_session_factory() as db:
        await fx.garantir_colunas(db)
        total = 0
        for tabela in fx.ALVOS:
            linhas = await fx.candidatos(db, tabela)
            print(f"\n{tabela}: {len(linhas)} candidato(s) ainda sem marca")
            for r in linhas:
                campos = " | ".join(str(r[c])[:46] for c in fx.ALVOS[tabela])
                print(f"   MARCAR  {campos}")
            if aplicar:
                total += await fx.marcar(db, tabela, [r["id"] for r in linhas])
        if not aplicar:
            print("\nDRY-RUN. Nada foi gravado. Rode com --aplicar.")
            return 0
        print(f"\nAPLICADO. {total} registro(s) marcado(s) como fixture. Nada foi apagado.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--aplicar" in sys.argv)))
