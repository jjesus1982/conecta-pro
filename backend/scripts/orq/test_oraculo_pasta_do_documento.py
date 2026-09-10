"""Oráculo — todo tipo de documento de kit tem PASTA declarada (10/09/2026).

Por que existe: no primeiro kit REAL o Jordan abriu a pasta Financeiro e achou lá seis GUIAS
(DARF IRRF, DCTFWeb, EFD-Reinf, FGTS, INSS Patronal, ISS Manaus), o 13º de 2025 e NFS-e de janeiro —
com a pasta Guias vazia. A regra de roteamento nomeava SEIS tipos e mandava todo o resto para
Financeiro no `else`. São 78 tipos gravados no banco: setenta e dois caíam no `else`.

Ninguém percebeu porque o `else` não é um erro — é uma resposta. O arquivo chegava ao Drive, o
contador de "enviados" subia, e só o olho de quem abre a pasta via que estava no lugar errado.

Afirma: todo `document_type` de documento de EMPRESA (employee_id IS NULL) gravado no banco tem
entrada em `PASTA_DO_TIPO`. Tipo novo nasce mapeado ou o oráculo fica vermelho no dia seguinte.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.people_management.ged.services.google_drive_service import PASTA_DO_TIPO

    #: as cinco subpastas que `create_kit_folder` cria — destino inválido é tão ruim quanto ausente
    VALIDAS = {"funcionarios", "certidoes", "guias", "beneficios", "financeiro"}

    gen = get_db()
    db = await gen.__anext__()
    linhas = (
        await db.execute(
            text(
                "SELECT document_type, count(*) FROM ged_kit_documents "
                "WHERE employee_id IS NULL GROUP BY 1 ORDER BY 2 DESC"
            )
        )
    ).fetchall()

    sem_mapa = [(t, n) for t, n in linhas if t not in PASTA_DO_TIPO]
    destino_invalido = sorted({p for p in PASTA_DO_TIPO.values() if p not in VALIDAS})

    for t, n in sem_mapa:
        print(f"FALHOU: '{t}' ({n} documentos) não está em PASTA_DO_TIPO — cairia em Financeiro por omissão")
    for p in destino_invalido:
        print(f"FALHOU: PASTA_DO_TIPO aponta para '{p}', que não é uma das subpastas do kit ({sorted(VALIDAS)})")

    print(
        f"tipos de empresa no banco: {len(linhas)} · mapeados: {len(linhas) - len(sem_mapa)} · "
        f"no mapa ao todo: {len(PASTA_DO_TIPO)}"
    )
    if sem_mapa or destino_invalido:
        raise AssertionError(f"{len(sem_mapa) + len(destino_invalido)} tipo(s) sem pasta declarada")
    print("OK: todo tipo de documento de empresa tem pasta declarada")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
