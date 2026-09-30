#!/usr/bin/env python3
"""Caçador: registro de TESTE visível na listagem que o dono abre.

O QUE ACONTECEU (BUG-07, 30/09/2026)
«AA2-FIXTURE DGX AA2 / Cliente de fixture / R$ 2.501,00» era o PRIMEIRO item de
`listar_propostas`. «QA Bateria E2E 14/09 / CONDOMINIO TESTE QA» estava no funil. O dono
abria a lista para decidir e lia lixo de teste junto com R$ 100 mil de negócio real.

POR QUE `checar_desmonte_comportamento` NÃO PEGAVA — e é o ponto desta trava
Aquele caçador compara a CONTAGEM das tabelas antes × depois de rodar cada oráculo. O
`test_oraculo_aa2_orcamento_catalogo` apagava a fixture no INÍCIO e inseria outra: uma
saída, uma entrada, saldo ZERO. A contagem nunca mexia, e a linha estava sempre lá — só
trocava de identidade a cada corrida.

Um caçador de DELTA é estruturalmente cego para apagar-e-inserir. Este olha o ESTADO: a
pergunta não é «cresceu?», é «tem lixo vivo agora?».

A REGRA AFIRMADA
Zero linha com assinatura de teste NÃO MARCADA como fixture nas tabelas comerciais.
Marcada é declarada: some da listagem e continua na base (decisão do Jordan, «não apague
nada»). O que esta trava proíbe é a fixture ANÔNIMA — a que ninguém declarou e por isso
aparece.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.crm.services import fixtures as fx  # noqa: E402


async def main() -> int:
    achados: list[str] = []
    async with async_session_factory() as db:
        await fx.garantir_colunas(db)
        for tabela in fx.ALVOS:
            linhas = await fx.candidatos(db, tabela)
            for r in linhas:
                campos = " | ".join(str(r[c])[:44] for c in fx.ALVOS[tabela])
                achados.append(f"{tabela}: {campos}")
                print(f"FIXTURE ANÔNIMA  {tabela}: {campos}")

        # A proposta de fixture do oráculo AA2 tem endereço próprio e vale checar direto:
        # é a que já apareceu em primeiro lugar na lista do dono.
        viva = (await db.execute(text("SELECT count(*) FROM proposals WHERE notes = 'FIXTURE DGX AA2'"))).scalar()
        if viva:
            achados.append(
                f"a fixture do oráculo AA2 ficou viva ({viva}) — o desmonte dele voltou a rodar só no início"
            )
            print(f"FIXTURE DO ORÁCULO AA2 VIVA: {viva} — desmonte só no início?")

    print(f"\n{len(achados)} registro(s) de teste visível(is) na base comercial")
    if achados:
        print(
            "São o que o dono lê quando abre a listagem. Marque-os "
            "(`scripts/crm/marcar_fixtures.py --aplicar`) ou faça o oráculo desmontar."
        )
        return 1
    print("VEREDITO: nenhuma fixture anônima nas listagens comerciais.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
