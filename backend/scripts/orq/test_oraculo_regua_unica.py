"""Banco e Drive medem a completude do kit com A MESMA régua.

Até 19/08/2026 respondiam perguntas diferentes com a mesma etiqueta: o banco fazia
"todo slot criado tem arquivo?" — e como o slot só nasce quando o documento é ENCONTRADO,
tendia a 100% por construção; o Drive fazia "o kit está completo perante o contrato?" e
dava 50%. Duas telas, dois números, e ninguém sabendo em qual acreditar.

Agora os dois usam os blocos de `kit_completude_service.CHECKLIST`, recortados pelo
contrato. Este oráculo trava a ESTRUTURA, que é o que apodrece em silêncio: se alguém
acrescentar um bloco de um lado e esquecer o outro, ou traduzir um `document_type` para um
bloco que não existe, as duas telas voltam a divergir sem que nada quebre.

Afirma a REGRA, não a fotografia: não fixa percentual, kit nem competência.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.gedeon.services.completude_slots import _BLOCO_DE_TIPO, _CND_ESPERADO  # noqa: E402
from modules.gedeon.services.kit_completude_service import CHECKLIST  # noqa: E402


async def main() -> None:
    blocos_drive = {c["key"] for c in CHECKLIST}
    blocos_banco = set(_BLOCO_DE_TIPO.values())

    orfaos = blocos_banco - blocos_drive
    assert not orfaos, (
        f"o banco traduz document_type para bloco(s) que o Drive não conhece: {sorted(orfaos)} — "
        "as duas telas voltariam a divergir sem nada quebrar"
    )

    # O bloco de CND vale por 5 certidões nos dois lados. Divergir aqui faz o mesmo kit
    # valer percentuais diferentes conforme a tela.
    esp_drive = next(c["esperado"] for c in CHECKLIST if c["key"] == "cnd")
    assert esp_drive == _CND_ESPERADO, f"bloco CND espera {esp_drive} no Drive e {_CND_ESPERADO} no banco"

    with get_sync_db() as db:
        # Tipo em uso que ninguém traduz = documento que nunca conta para completude
        # nenhuma. Não é erro fatal (há tipos legítimos fora do kit mensal), mas o número
        # tem de ser conhecido — silêncio aqui vira "0% com a pasta cheia".
        sem_bloco = (
            db.execute(
                text(
                    "SELECT d.document_type, count(*) AS n FROM ged_kit_documents d "
                    " WHERE coalesce(d.file_path,'') <> '' AND d.document_type <> ALL(:tipos) "
                    " GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
                ),
                {"tipos": list(_BLOCO_DE_TIPO.keys())},
            )
            .mappings()
            .all()
        )

        fora = db.execute(text("SELECT count(*) FROM ged_document_kits WHERE completion_percentage > 100")).scalar()

    assert not fora, f"{fora} kit(s) com completude acima de 100% — a régua está dividindo errado"

    print(f"OK vocabulário comum: {len(blocos_banco)} bloco(s) no banco, todos dentro dos {len(blocos_drive)} do Drive")
    print(f"OK bloco CND vale {esp_drive} certidões nos dois lados")
    if sem_bloco:
        top = ", ".join(f"{r['document_type']}({r['n']})" for r in sem_bloco[:5])
        print(f"OK {len(sem_bloco)} tipo(s) sem bloco — não contam para completude: {top}")
    print("TEST oraculo_regua_unica PASS")


if __name__ == "__main__":
    asyncio.run(main())
