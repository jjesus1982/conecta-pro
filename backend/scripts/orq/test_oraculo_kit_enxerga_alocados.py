"""O montador do kit enxerga os funcionários alocados, venha o id de qual tabela vier.

São DUAS tabelas de cliente sem FK entre si: `ged_document_kits.client_id` aponta para
`ged_clients`, `posts.client_id` aponta para `clients`. `_get_employees_for_client`
recebia o primeiro e comparava com o segundo — nunca casava. A função devolvia lista
vazia para TODO cliente e o montador respondia "Sem funcionarios alocados" nos 7
condomínios, mesmo com 52 pessoas alocadas. Medido em 18/08/2026.

Afirma a REGRA e não a fotografia: para cada cliente que tem posto com gente alocada, o
que o montador enxerga tem de ser o mesmo que a alocação diz — por qualquer um dos dois
ids. Cliente novo, posto novo ou remanejamento entram sozinhos; nenhum UUID chumbado.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.ged.controllers.kit_real_controller import _get_employees_for_client  # noqa: E402

# Verdade independente: quantas pessoas a ALOCAÇÃO diz que estão em cada cliente.
# Escrita aqui do zero — não é cópia da query que o oráculo audita.
SQL_VERDADE = text(
    """
    SELECT c.id::text AS client_id, c.name, count(DISTINCT e.id) AS n
      FROM clients c
      JOIN posts p ON p.client_id = c.id
      JOIN allocations a ON a.post_id = p.id AND a.status = 'active'
      JOIN employees e ON e.id = a.employee_id AND e.is_active = true
     GROUP BY c.id, c.name
    HAVING count(DISTINCT e.id) > 0
     ORDER BY c.name
    """
)

# O id equivalente no OUTRO mundo — é ele que o kit carrega.
SQL_GED = text(
    """
    SELECT g.id::text
      FROM ged_clients g, clients c
     WHERE c.id::text = :cid
       AND ((coalesce(g.cnpj,'') <> '' AND coalesce(c.document_number,'') <> ''
             AND regexp_replace(g.cnpj,'\\D','','g') = regexp_replace(c.document_number,'\\D','','g'))
            OR upper(btrim(g.name)) = upper(btrim(c.name)))
     LIMIT 1
    """
)


async def main() -> None:
    async with async_session_factory() as db:
        verdade = (await db.execute(SQL_VERDADE)).mappings().all()
        assert verdade, "nenhum cliente com gente alocada — pré-condição do oráculo não existe"

        divergentes: list[str] = []
        sem_ponte = 0
        conferidos = 0
        for r in verdade:
            vistos_direto = len(await _get_employees_for_client(db, r["client_id"]))
            if vistos_direto != r["n"]:
                divergentes.append(
                    f"{r['name'][:28]}: alocação diz {r['n']}, montador vê {vistos_direto} (id de clients)"
                )

            ged = (await db.execute(SQL_GED, {"cid": r["client_id"]})).scalar()
            if not ged:
                sem_ponte += 1
                continue
            vistos_ged = len(await _get_employees_for_client(db, ged))
            conferidos += 1
            if vistos_ged != r["n"]:
                divergentes.append(
                    f"{r['name'][:28]}: alocação diz {r['n']}, montador vê {vistos_ged} (id de ged_clients)"
                )

        assert not divergentes, f"{len(divergentes)} divergência(s) — " + " ; ".join(divergentes[:4])

        # Suspenders: o defeito era ZERO para todo mundo. Que não volte silenciosamente.
        total = sum(r["n"] for r in verdade)
        assert total > 0, "soma de alocados deu zero — o oráculo estaria passando à toa"

        print(f"OK {len(verdade)} cliente(s) com gente alocada, {total} pessoas no total")
        print(f"OK {conferidos} conferido(s) também pelo id de ged_clients; {sem_ponte} sem par no GED")
        print("TEST oraculo_kit_enxerga_alocados PASS")


if __name__ == "__main__":
    asyncio.run(main())
