"""A lista de pessoas de um kit é a do MÊS do kit, não a de hoje.

🔴 28/09/2026 — Pyetra: *"Salvei o Kit do Mirante e veio informações do kit do Fiori."*

Os DOIS montadores de kit escolhiam quem entra por `allocations.status = 'active'`, que é o
estado de HOJE, para montar um kit de um mês PASSADO. Medido chamando
`KitBuilderService.get_employees_for_client` para 03, 08 e 09/2026: **devolveu a mesma lista nas
três**. No Mirante de 03/2026 entrava FRANCE CHARLES ALMEIDA DE SALES, cuja alocação no Mirante
começa em **25/09/2026**; e faltavam MAURICIO ALVES CHAGAS e FERNANDA VINHOTE MACIEL, que
estavam lá em março. Efeito prático: quem troca de condomínio arrasta os documentos dos meses
anteriores para o condomínio NOVO — CINTIA BEZERRA OLIVEIRA e EIDY CULIER DE CASTRO (Villa Dei
Fiori desde 01/03, nunca no Mirante) ficaram com 5 documentos cada nos kits do MIRANTE de 03,
04, 05 e 06/2026.

Afirma a REGRA, não a fotografia: para QUALQUER cliente e QUALQUER competência, quem o montador
enxerga tem de ser exatamente quem a janela da alocação (`start_date`/`end_date`) diz que estava
naquele posto naquele mês. Nenhum UUID, nome ou contagem chumbada — condomínio novo, posto novo
e remanejamento entram sozinhos. Roda contra o banco real.

    docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_kit_pessoas_da_competencia.py
"""

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.ged.controllers.kit_real_controller import _get_employees_for_client  # noqa: E402
from modules.people_management.ged.services.kit_builder_service import KitBuilderService  # noqa: E402

# Verdade independente, escrita do zero (não é cópia da query auditada): quem a ALOCAÇÃO diz que
# estava no posto do cliente GED durante o mês. `posts.ged_client_id` é o vínculo explícito.
SQL_VERDADE = text(
    """
    SELECT DISTINCT a.employee_id::text
      FROM allocations a
      JOIN posts p ON p.id = a.post_id
     WHERE p.ged_client_id = CAST(:cid AS uuid)
       AND a.start_date < (CAST(:ref AS date) + INTERVAL '1 month')
       AND (a.end_date IS NULL OR a.end_date >= CAST(:ref AS date))
    """
)

# Competências a auditar: as que realmente têm kit no banco (regra, não lista fixa).
SQL_COMPETENCIAS = text(
    """
    SELECT DISTINCT k.client_id::text, k.reference_month
      FROM ged_document_kits k
      JOIN ged_clients c ON c.id = k.client_id
     WHERE EXISTS (SELECT 1 FROM posts p WHERE p.ged_client_id = k.client_id)
       AND k.reference_month >= date '2026-01-01'
     ORDER BY 2, 1
    """
)


async def main() -> int:
    falhas: list[str] = []
    checados = 0
    async with async_session_factory() as db:
        casos = (await db.execute(SQL_COMPETENCIAS)).all()
        svc = KitBuilderService(db)
        for cid, ref in casos:
            ref = ref if isinstance(ref, date) else date.fromisoformat(str(ref))
            esperado = {r for (r,) in (await db.execute(SQL_VERDADE, {"cid": cid, "ref": ref})).all()}

            visto_builder = set(await svc.get_employees_for_client(cid, reference_month=ref))
            visto_real = {e["id"] for e in await _get_employees_for_client(db, cid, ref)}
            checados += 1

            # O montador pode ver MENOS que a alocação (ele ainda corta admissão/demissão e
            # `is_active`), mas nunca pode ver QUEM NÃO ESTAVA ALI NAQUELE MÊS. Ver a mais é a
            # contaminação que a Pyetra pegou.
            for rotulo, visto in (("kit_builder_service", visto_builder), ("kit_real_controller", visto_real)):
                intrusos = visto - esperado
                if intrusos:
                    nomes = (
                        await db.execute(
                            text("SELECT nome FROM employees WHERE id::text = ANY(:i) ORDER BY nome"),
                            {"i": sorted(intrusos)},
                        )
                    ).scalars().all()
                    cli = (
                        await db.execute(text("SELECT name FROM ged_clients WHERE id::text = :c"), {"c": cid})
                    ).scalar()
                    falhas.append(f"{rotulo}: {cli} {ref:%m/%Y} viu {len(intrusos)} de fora → {', '.join(nomes)}")

    print(f"{checados} (cliente, competência) auditados nos dois montadores")
    if falhas:
        print(f"\n🔴 {len(falhas)} violações — pessoa no kit sem alocação naquele mês:")
        for f in falhas:
            print("  -", f)
        return 1
    print("✅ nenhum montador colocou no kit gente que não estava no posto naquela competência")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
