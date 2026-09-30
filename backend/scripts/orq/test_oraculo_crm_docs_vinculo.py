#!/usr/bin/env python3
"""Oráculo: documento vinculado a uma entidade TEM de aparecer quando se pergunta por ela.

O QUE ACONTECEU (30/09/2026)
Os 4 escritores de `crm_documents.ref_tipo` gravam em INGLÊS — `proposal`, `contract`,
`client`. `listar_da_entidade` fazia `lower()` na palavra PORTUGUESA que a tool publica
(`proposta`, `contrato`, `cliente`) e comparava direto com a coluna. Medido:

    proposal   120        contrato    2
    contract    64        proposta    1
    client      22        (nulo)     64

206 dos 209 documentos vinculados nunca apareceram. A rota respondia HTTP 200 com
`total: 0` — e «nenhum documento» é indistinguível de «nenhum documento que eu saiba
procurar» para quem lê a resposta.

A REGRA AFIRMADA, e não a fotografia
Para CADA valor de `ref_tipo` que existe na tabela, perguntar pela entidade correspondente
devolve pelo menos os documentos que o SQL cru encontra. Se amanhã alguém gravar um quinto
idioma, este oráculo acusa — ele não conhece a lista, ele lê a tabela.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.crm.services.docs_registry import listar_da_entidade  # noqa: E402

#: Como o usuário pergunta, por valor gravado. Um valor gravado sem tradutor aqui é
#: exatamente o defeito: documento que existe e não tem pergunta que o alcance.
COMO_SE_PERGUNTA = {
    "client": "cliente",
    "proposal": "proposta",
    "contract": "contrato",
    "deal": "oportunidade",
    "cliente": "cliente",
    "proposta": "proposta",
    "contrato": "contrato",
}


async def main() -> int:
    falhas = []
    async with async_session_factory() as db:
        tipos = (
            (
                await db.execute(
                    text(
                        "SELECT ref_tipo, count(*) n FROM crm_documents "
                        " WHERE ref_tipo IS NOT NULL AND coalesce(arquivado,false)=false "
                        " GROUP BY 1 ORDER BY 2 DESC"
                    )
                )
            )
            .mappings()
            .all()
        )
        if not tipos:
            print("FALHA: nenhum documento vinculado na base — o oráculo não tem o que provar")
            return 1

        for t in tipos:
            gravado, n = t["ref_tipo"], t["n"]
            pergunta = COMO_SE_PERGUNTA.get(gravado)
            if not pergunta:
                falhas.append(f"ref_tipo {gravado!r} ({n} doc) não tem pergunta que o alcance")
                print(f"FALHA sem tradutor para {gravado!r} — {n} documento(s) inalcançáveis")
                continue

            alvo = (
                (
                    await db.execute(
                        text(
                            "SELECT ref_id, count(*) n FROM crm_documents "
                            " WHERE ref_tipo=:t AND coalesce(arquivado,false)=false "
                            " GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
                        ),
                        {"t": gravado},
                    )
                )
                .mappings()
                .first()
            )

            r = await listar_da_entidade(db, entidade=pergunta, entidade_id=alvo["ref_id"])
            if r["total"] < alvo["n"]:
                falhas.append(f"{gravado}: SQL cru vê {alvo['n']}, a rota devolve {r['total']}")
                print(f"FALHA {gravado!r} perguntado como {pergunta!r}: SQL cru {alvo['n']} × rota {r['total']}")
            else:
                print(
                    f"ok    {gravado:<10} perguntado como {pergunta:<12} {r['total']} documento(s), SQL cru {alvo['n']}"
                )

            # O nome gravado também tem de funcionar como pergunta: metade do sistema fala
            # inglês e é ele que escreve. Obrigar quem lê a traduzir é o defeito de origem.
            r2 = await listar_da_entidade(db, entidade=gravado, entidade_id=alvo["ref_id"])
            if r2["total"] != r["total"]:
                falhas.append(
                    f"{gravado}: perguntar pelo nome GRAVADO devolve {r2['total']}, "
                    f"pelo nome publicado devolve {r['total']}"
                )
                print(f"FALHA {gravado!r} como pergunta devolve {r2['total']} ≠ {r['total']}")

    print()
    if falhas:
        print(f"VEREDITO: {len(falhas)} falha(s)")
        for f in falhas:
            print("  -", f)
        return 1
    print("VEREDITO: todo ref_tipo gravado tem pergunta que o alcança, nos dois idiomas")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
