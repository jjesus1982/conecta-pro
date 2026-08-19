"""A régua da completude é o CONTRATO de cada cliente, não uma lista fixa para todos.

O checklist do kit tinha 10 blocos iguais para todo mundo. Isso cobrava folha, ponto e
comprovante de VT do GELAIN — portaria remota, emitida pela Eletrônica, ZERO alocados. O
percentual dele não tinha como subir, e a média do painel afundava por uma exigência que
o contrato não faz.

Afirma a REGRA: quem não tem gente alocada não responde por documento trabalhista; quem
tem, responde. Contrato novo, posto novo ou fim de contrato entram sozinhos — nenhum nome
de cliente chumbado aqui.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.gedeon.services.kit_completude_service import (  # noqa: E402
    _BLOCOS_TRABALHISTAS,
    blocos_por_condominio,
)

# Verdade independente: quem tem gente alocada hoje. Escrita do zero, não copiada do
# serviço auditado — se as duas consultas fossem a mesma, o oráculo só provaria cópia.
SQL_ALOCADOS = text(
    """
    SELECT c.name, count(DISTINCT a.employee_id) AS n
      FROM clients c
      JOIN contracts ct ON ct.client_id = c.id AND ct.status::text = 'active'
      LEFT JOIN posts p ON p.client_id = c.id
      LEFT JOIN allocations a ON a.post_id = p.id AND a.status = 'active'
     GROUP BY c.name
    """
)


def _norm(x: str) -> str:
    import unicodedata

    x = unicodedata.normalize("NFKD", x or "")
    return "".join(c for c in x if not unicodedata.combining(c)).lower().strip()


async def main() -> None:
    with get_sync_db() as db:
        verdade = {_norm(r["name"]): int(r["n"] or 0) for r in db.execute(SQL_ALOCADOS).mappings()}
        blocos = blocos_por_condominio(db)

    assert blocos, "nenhum contrato ativo — pré-condição do oráculo não existe"

    cobrando_de_quem_nao_tem: list[str] = []
    poupando_quem_tem: list[str] = []
    for cliente, esperados in blocos.items():
        n = verdade.get(cliente)
        if n is None:
            continue
        tem_trabalhista = bool(esperados & _BLOCOS_TRABALHISTAS)
        if n == 0 and tem_trabalhista:
            cobrando_de_quem_nao_tem.append(f"{cliente[:34]} (0 alocados, {len(esperados)} blocos)")
        if n > 0 and not tem_trabalhista:
            poupando_quem_tem.append(f"{cliente[:34]} ({n} alocados, {len(esperados)} blocos)")

    assert not cobrando_de_quem_nao_tem, (
        f"{len(cobrando_de_quem_nao_tem)} cliente(s) SEM gente alocada cobrados por documento "
        "trabalhista — " + " ; ".join(cobrando_de_quem_nao_tem[:4])
    )
    assert not poupando_quem_tem, (
        f"{len(poupando_quem_tem)} cliente(s) COM gente alocada sem checklist trabalhista — "
        + " ; ".join(poupando_quem_tem[:4])
    )

    com = sum(1 for c, e in blocos.items() if e & _BLOCOS_TRABALHISTAS)
    print(f"OK {len(blocos)} contratos ativos: {com} com checklist trabalhista, {len(blocos) - com} sem")
    print("OK nenhum cliente cobrado por documento que o contrato dele não pede")
    print("TEST oraculo_checklist_do_contrato PASS")


if __name__ == "__main__":
    asyncio.run(main())
