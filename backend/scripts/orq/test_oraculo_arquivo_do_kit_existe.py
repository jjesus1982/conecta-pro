"""Oráculo — todo documento de kit com caminho tem ARQUIVO de verdade onde a sincronização procura (09/09/2026).

Por que existe: no primeiro kit REAL (Michelangelo, 08/2026) dezesseis documentos legítimos — DCTFWeb, NFS-e,
CNDs, folha de pagamento, boleto — nunca chegaram ao Drive do cliente. O coletor gravou caminho RELATIVO
("ged/kits/x.pdf"); a sincronização testava `os.path.exists` a partir do diretório de trabalho e não achava.
O arquivo estava em /app/uploads/ged/kits/x.pdf o tempo todo. Nenhum erro, nenhum log: o kit só ficava menor.

É o gêmeo do fantasma de container: ali o arquivo existe no disco e não no container; aqui existe no disco e
não no caminho que o código consulta. Nos dois casos o número que se anuncia ("88 documentos") descreve o
BANCO, não o que o cliente recebe.

Afirma, sobre os kits dos últimos 90 dias:
  1. caminho gravado que não é link resolve para um arquivo real (absoluto, ou relativo a /app/uploads);
  2. documento marcado `is_signed` tem arquivo — assinatura sem PDF é evidência que não existe.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import os
import sys

BASES = ("/app/uploads", "/app")


def resolve(fp: str) -> str | None:
    """Mesma regra do `_caminho_real` da sincronização — se mudar lá, este oráculo tem de mudar junto."""
    if os.path.isabs(fp):
        return fp if os.path.exists(fp) else None
    for b in BASES:
        c = os.path.join(b, fp)
        if os.path.exists(c):
            return c
    return None


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    rows = (
        await db.execute(
            text("""
        SELECT c.name, k.reference_month, d.document_type, d.document_name, d.file_path, d.is_signed
        FROM ged_kit_documents d
        JOIN ged_document_kits k ON k.id = d.kit_id
        JOIN ged_clients c ON c.id = k.client_id
        WHERE k.reference_month >= (CURRENT_DATE - INTERVAL '90 days')
    """)
        )
    ).fetchall()

    perdidos: list[str] = []
    assinado_sem_arquivo: list[str] = []
    for nome_cli, ref, tipo, nome, fp, assinado in rows:
        onde = f"{nome_cli} {ref:%m/%Y} · {tipo} · {nome}"
        if fp and not str(fp).startswith("http"):
            if resolve(str(fp)) is None:
                perdidos.append(f"{onde} → {fp}")
        elif assinado and not fp:
            assinado_sem_arquivo.append(onde)

    for x in perdidos[:20]:
        print("FALHOU (some do Drive em silêncio):", x)
    for x in assinado_sem_arquivo[:10]:
        print("FALHOU (assinado sem PDF):", x)
    print(
        f"documentos de kit nos últimos 90 dias: {len(rows)} · "
        f"caminho que não resolve: {len(perdidos)} · assinado sem arquivo: {len(assinado_sem_arquivo)}"
    )
    if perdidos or assinado_sem_arquivo:
        raise AssertionError(f"{len(perdidos) + len(assinado_sem_arquivo)} documento(s) de kit sem arquivo alcançável")
    print("OK: todo documento de kit com caminho tem arquivo onde a sincronização procura")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
