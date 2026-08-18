"""A completude ANUNCIADA do kit tem de ser a contagem no banco — não um número velho.

🔴 O DEFEITO, medido em 14/08/2026 em produção. O painel do GEDEON dizia:

    competência   kits   completude gravada   completude real (contagem)
    2026-05        11          12,2%                  76,7%
    2026-07        11           7,7%                  53,4%
    2026-08         1           0,0%                 100,0%

**Maio anunciava 12,2% com três quartos do kit montado. Agosto dizia 0% com o kit inteiro
pronto.** 49 dos 52 kits divergiam da própria fórmula do código.

ATUALIZADO em 18/08/2026: este oráculo PASSOU com o Prime Arena anunciando **357%** e o
Mirante anunciando **0%** com 18 slots cheios. Passou porque dividia pelo mesmo
`total_documents` que o código auditado usava — os dois concordavam no número errado. É
exatamente a armadilha de comparar com a query que se audita. Agora a verdade é contada
de `ged_kit_documents`, e o `total_documents` virou objeto de asserção, não instrumento.

A conta nunca esteve errada — `slot com arquivo ÷ total_documents` é a definição do próprio
sistema. O número é que estava VELHO: só o `Hermes.processar_mes` recalculava, e ele roda
pelo beat do dia 1 às 09:00. Os arquivos entram o mês inteiro pelo `kit_pdf_controller`, que
preenchia o slot e ia embora.

A cadeia que isso trava: completude falsa → o kit nunca chega a 100% → ninguém aprova →
nada é enviado → o cliente continua cobrando na mão. 55 kits montados, ZERO aprovados, UM
enviado em oito meses.

ESTE ORÁCULO AFIRMA A REGRA, NÃO A FOTOGRAFIA: não fixa "76,7%" nem competência nenhuma.
Recalcula a verdade do banco a cada rodada e exige que o gravado bata. Continua valendo em
setembro, com outros kits e outros clientes.

⚠️ A consulta daqui é escrita de forma INDEPENDENTE do serviço. Se fosse `from
completude_slots import ...` e comparar com ele mesmo, provaria só que sei chamar a função.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Tolerância de arredondamento: o gravado é `round(x, 2)`, então 0,01 de folga.
TOLERANCIA = 0.02

SQL_DIVERGENTES = text(
    "SELECT k.id::text AS id, to_char(k.reference_month,'YYYY-MM') AS comp, "
    "       coalesce(gc.name,'—') AS cliente, "
    "       (SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id = k.id) AS slots, "
    "       k.total_documents AS declarado, "
    "       coalesce(k.completion_percentage, 0) AS gravado, "
    "       round(100.0 * (SELECT count(*) FROM ged_kit_documents d "
    "                      WHERE d.kit_id = k.id "
    "                        AND d.file_path IS NOT NULL AND d.file_path <> '') "
    "             / nullif((SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id = k.id), 0), 2) AS real_ "
    "FROM ged_document_kits k "
    "LEFT JOIN ged_clients gc ON gc.id = k.client_id "
    "WHERE EXISTS (SELECT 1 FROM ged_kit_documents d WHERE d.kit_id = k.id) "
    "ORDER BY k.reference_month DESC"
)


async def main() -> None:
    async with async_session_factory() as db:
        linhas = (await db.execute(SQL_DIVERGENTES)).mappings().all()
        assert linhas, "nenhum kit com slots — o oráculo não teria o que provar"

        divergentes = [r for r in linhas if abs(float(r["gravado"]) - float(r["real_"] or 0)) > TOLERANCIA]
        if divergentes:
            amostra = "; ".join(
                f"{r['comp']} {r['cliente'][:20]}: anuncia {r['gravado']}% e tem {r['real_']}% ({r['slots']} slots)"
                for r in divergentes[:4]
            )
            raise AssertionError(
                f"{len(divergentes)} de {len(linhas)} kits com completude divergente da contagem no banco — {amostra}"
            )
        print(f"OK completude bate com o banco em {len(linhas)} kits")

        # suspenders: o defeito exato era percentual VELHO — zerado enquanto os slots já
        # estavam cheios. Se voltar a existir kit com todos os slots preenchidos anunciando
        # menos de 100, o recálculo sumiu de novo em algum ponto de escrita.
        cheio_mentindo = [r for r in linhas if float(r["real_"] or 0) >= 100.0 and float(r["gravado"]) < 100.0]
        assert not cheio_mentindo, (
            f"{len(cheio_mentindo)} kit(s) com TODOS os slots preenchidos anunciando "
            f"menos de 100% — o recálculo deixou de rodar em algum ponto de escrita"
        )
        # Percentual é percentual: 0..100. O Prime Arena anunciou 357% em 18/08/2026 e
        # este oráculo não viu, porque dividia pelo mesmo número podre que o código usava.
        fora_da_faixa = [r for r in linhas if not (0.0 <= float(r["gravado"]) <= 100.0)]
        assert not fora_da_faixa, f"{len(fora_da_faixa)} kit(s) com completude fora de 0..100 — " + " ; ".join(
            f"{r['cliente'][:24]} {r['gravado']}%" for r in fora_da_faixa[:4]
        )

        # `total_documents` é espelho da contagem de slots, e espelho envelhece: o montador
        # insere slot sem mexer nele. Enquanto for usado como denominador em qualquer lugar,
        # divergir dele é dividir pelo número errado.
        espelho_velho = [r for r in linhas if int(r["declarado"] or 0) != int(r["slots"])]
        assert not espelho_velho, (
            f"{len(espelho_velho)} kit(s) com total_documents diferente da contagem real — "
            + " ; ".join(f"{r['cliente'][:24]} declara {r['declarado']} e tem {r['slots']}" for r in espelho_velho[:4])
        )

        pct100 = sum(1 for r in linhas if float(r["real_"] or 0) >= 100.0)
        print(f"OK nenhum kit cheio anunciando menos que 100 — {pct100} kit(s) em 100%")
        print(f"OK completude dentro de 0..100 e total_documents batendo em {len(linhas)} kit(s)")

    print("TEST oraculo_completude_kit PASS")


if __name__ == "__main__":
    asyncio.run(main())
