#!/usr/bin/env python3
"""Importa o export CSV do Gerenciador de Anúncios da Meta para o Conecta PRO.

Via sem token: a Marketing API está travada numa verificação por SMS que a Meta
não entrega. Isto traz o mesmo dado — gasto por campanha — pelas mesmas colunas,
então o CAC funciona igual e a sincronia por API, quando destravar, apenas
atualiza as mesmas linhas (casa por `external_id`).

Como gerar o arquivo no Gerenciador de Anúncios:
  Campanhas → Relatórios → Exportar → CSV, com as colunas
  "Identificação da campanha", "Nome da campanha", "Valor gasto",
  "Início dos relatórios", "Término dos relatórios".
  A "Identificação da campanha" é a que importa: sem ela o casamento passa a ser
  pelo NOME, e nome de campanha o marketing renomeia.

  docker cp export.csv conecta-pro-backend:/tmp/
  docker exec conecta-pro-backend python3 scripts/importar_ads_csv.py /tmp/export.csv
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from core.database import async_session_factory  # noqa: E402
from modules.integrations.connectors.meta.ads import (  # noqa: E402
    cac_por_campanha,
    importar_csv,
)


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    async with async_session_factory() as db:
        r = await importar_csv(db, sys.argv[1])
        print(f"  {r}")
        if not r.get("ok"):
            return 1
        if not r.get("por_id"):
            print("  AVISO: CSV sem 'Identificação da campanha' — casando pelo NOME. "
                  "Renomear a campanha na Meta criará linha nova.")
        print("\n  CAC por campanha (gasto ÷ leads atribuídos):")
        for c in await cac_por_campanha(db, dias=30):
            cac = f"R$ {c['cac']:.2f}" if c["cac"] is not None else "— (nenhum lead atribuído)"
            print(f"    {c['campanha'][:40]:<42} gasto R$ {c['gasto']:>10.2f}  "
                  f"leads {c['leads']:>4}  CAC {cac}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
