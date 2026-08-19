"""Da competência 08/2026 em diante, o kit só recebe certidão de quem EMITE o contrato.

Regra do Jordan em 19/08/2026: condomínio com mão de obra alocada leva documentação da
CONECTA PATRIMONIAL; contrato de segurança eletrônica leva da CONECTA ELETRÔNICA. O kit de
julho fica como está — por isso a regra tem corte de competência, e este oráculo respeita
o corte: não reprova o passado.

Não é "uma empresa por kit": o VILLA DOS PÁSSAROS tem mão de obra pela Patrimonial E CFTV
pela Eletrônica, e responde pelas duas. Por isso a verdade é `contracts.empresa_id`, não um
mapa de condomínio.

O que motivou: em 19/08/2026 cada um dos 7 kits de mão de obra carregava 5 certidões da
ELETRÔNICA — e com nome anônimo ("CND Estadual (SEFAZ-AM).pdf"), sem CNPJ nem empresa.
Quem abrisse o kit não tinha como saber de quem eram.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.gedeon.services.cnd_kit_service import (  # noqa: E402
    REGRA_EMPREGADORA_DESDE,
    _competencia_ge,
    _nome_arquivo,
    cnpjs_do_kit,
)

# Verdade independente: quais empresas emitem contrato ativo de cada cliente.
SQL_VERDADE = text(
    """
    SELECT c.name, array_agg(DISTINCT regexp_replace(coalesce(em.cnpj,''),'[^0-9]','','g')) AS cnpjs
      FROM clients c
      JOIN contracts ct ON ct.client_id = c.id AND ct.status::text = 'active'
      JOIN empresas em ON em.id = ct.empresa_id
     GROUP BY c.name
    """
)


async def main() -> None:
    # O corte existe e é respeitado nos dois sentidos.
    assert not _competencia_ge("07.2026", REGRA_EMPREGADORA_DESDE), "a regra não pode valer para julho"
    assert _competencia_ge(REGRA_EMPREGADORA_DESDE, REGRA_EMPREGADORA_DESDE), (
        "a regra tem de valer na própria competência"
    )

    with get_sync_db() as db:
        verdade = {r["name"]: {c for c in r["cnpjs"] if c} for r in db.execute(SQL_VERDADE).mappings()}
        assert verdade, "nenhum contrato ativo com empresa — pré-condição não existe"

        errados: list[str] = []
        for nome, esperados in verdade.items():
            visto = cnpjs_do_kit(db, nome)
            if visto != esperados:
                errados.append(f"{nome[:30]}: contrato diz {sorted(esperados)}, kit aceitaria {sorted(visto)}")

    assert not errados, f"{len(errados)} cliente(s) com empresa divergente — " + " ; ".join(errados[:4])

    # Suspenders: sob a regra, NENHUMA certidão pode ter nome anônimo. Era assim que 5
    # certidões da Eletrônica passavam despercebidas em cada kit.
    anonimo = _nome_arquivo(
        "certidao_negativa_estadual", "35710481000103", "Conecta Mais Eletrônica", sempre_com_empresa=True
    )
    assert anonimo and "—" in anonimo, f"certidão sem empresa no nome sob a regra: {anonimo!r}"

    print(f"OK regra vale de {REGRA_EMPREGADORA_DESDE} em diante; julho preservado")
    print(f"OK {len(verdade)} cliente(s) com a empresa do kit igual à do contrato")
    print(f"OK certidão nomeada com a empresa: {anonimo}")
    print("TEST oraculo_kit_por_empresa PASS")


if __name__ == "__main__":
    asyncio.run(main())
