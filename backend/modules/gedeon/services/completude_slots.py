"""A completude do kit — UMA fórmula, um dono.

🔴 O DEFEITO, medido em 14/08/2026 no banco de produção. O painel do GEDEON anunciava:

    competência   kits   completude gravada   completude pela PRÓPRIA fórmula
    2026-07        11           7,7%                    53,4%
    2026-06        10          20,9%                    43,5%
    2026-05        11          12,2%                    93,7%   ← 93,7, anunciando 12,2

**Maio estava 93,7% montado e o sistema dizia 12,2%.** 49 dos 52 kits divergiam. E a conta
que revela isso é a MESMA que o código já usava — `slot com arquivo ÷ total_documents`. Não
havia erro de fórmula: o número estava VELHO.

Por quê: o percentual só era recalculado dentro do `Hermes.processar_mes`, que roda pelo beat
do **dia 1 às 09:00**. Os arquivos entram durante o mês inteiro — pelo `kit_pdf_controller`,
que preenche o slot e vai embora sem recalcular nada. O percentual congela no que era quando
o kit nasceu; vários ficaram em `0.00` com todos os slots cheios.

A cadeia que isso alimenta é a que trava o módulo: completude falsa → o kit nunca chega a
100% → ninguém aprova → nada é enviado → **o cliente continua cobrando na mão.** 55 kits
montados, ZERO aprovados, UM enviado em oito meses.

POR QUE UM MÓDULO SÓ, e não uma linha em cada lugar: a fórmula vivia em `hermes.py:544` e os
outros dois pontos de escrita simplesmente não a tinham. Duas cópias divergem na primeira
mudança; três, mais rápido ainda. Aqui ela tem um dono, e quem preenche slot chama.

⚠️ NÃO CONFUNDA com `kit_completude_service`, que é outra coisa: aquele lê as pastas do
Google Drive e classifica por NOME de arquivo — é a visão de conferência, não o número
gravado. Arquivo de Drive não tem coluna de tipo; casar por nome ali é a única informação
que existe. Consertar aquele não move este número em um ponto sequer.
"""

from __future__ import annotations

from sqlalchemy import text

#: A conta, escrita uma vez.
#:
#: ⚠️ `total_documents` NÃO é meta nem template: é um espelho da contagem de slots — e
#: espelho envelhece. Em 18/08/2026, depois que o montador voltou a criar slots (o defeito
#: das duas tabelas de cliente), 14 kits ficaram com o declarado diferente do real:
#: Prime Arena declarava 7 com 25 slots e anunciou **357%**; o Mirante declarava 0 com 18
#: slots cheios e ficou em **0%**, fora do UPDATE por causa do antigo `total_documents > 0`.
#:
#: Por isso o número é REFRESCADO aqui, na mesma conta que o usa. Dividir por um valor
#: guardado por outra pessoa em outro momento é confiar em convenção; contar é ler a fonte.
_CONTA = (
    "  total_documents = (SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id = k.id), "
    "  completion_percentage = coalesce(round("
    "    100.0 * (SELECT count(*) FROM ged_kit_documents d "
    "             WHERE d.kit_id = k.id AND d.file_path IS NOT NULL AND d.file_path <> '')"
    "    / nullif((SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id = k.id), 0), 2), 0), "
    "  updated_at = now() "
)

_SQL_UM_KIT = text("UPDATE ged_document_kits k SET " + _CONTA + "WHERE k.id = CAST(:kit_id AS uuid)")

# Sem o antigo `AND total_documents > 0`: era ele que deixava o kit zerado FORA do
# recálculo — justo o kit que mais precisava. Kit sem slot nenhum cai em 0% pelo coalesce.
_SQL_COMPETENCIA = text(
    "UPDATE ged_document_kits k SET " + _CONTA + "WHERE k.reference_month = CAST(:ref_date AS date)"
)


def recalcular_kit(db, kit_id) -> int:
    """Recalcula a completude de UM kit. Chame logo depois de preencher um slot.

    Recebe a sessão de quem chamou e NÃO faz commit: o recálculo tem de entrar na mesma
    transação que gravou o `file_path`. Se entrasse em transação própria, um rollback do
    chamador deixaria o percentual falando de um arquivo que não existe.
    """
    return db.execute(_SQL_UM_KIT, {"kit_id": str(kit_id)}).rowcount


def recalcular_competencia(db, ref_date: str) -> int:
    """Recalcula todos os kits de uma competência (`AAAA-MM-01`). Sem commit, igual."""
    return db.execute(_SQL_COMPETENCIA, {"ref_date": ref_date}).rowcount


async def recalcular_kit_async(db, kit_id) -> int:
    """Mesma conta, para quem tem `AsyncSession`. O SQL é o mesmo objeto — não há segunda
    fórmula aqui, só o `await`."""
    return (await db.execute(_SQL_UM_KIT, {"kit_id": str(kit_id)})).rowcount


async def recalcular_competencia_async(db, ref_date: str) -> int:
    return (await db.execute(_SQL_COMPETENCIA, {"ref_date": ref_date})).rowcount
