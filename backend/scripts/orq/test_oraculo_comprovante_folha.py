"""Pagamento de folha no extrato tem de ter comprovante no kit da competência.

🔴 O BURACO, medido em 14/08/2026 no banco de produção:

    Cora SCD · 40 lançamentos de salário entre 04 e 10/08 · R$ 63.883,01
    com comprovante anexado: ZERO

O salário de agosto **foi pago** e o bloco "pagamentos" do kit nasce vazio. O cliente recebe
um kit trabalhista sem a prova de que a folha foi quitada — que é justamente um dos
documentos que ele cobra.

POR QUE O GEDEON NÃO ENXERGAVA: o módulo foi construído quando o dinheiro era do Inter.
`kit_orchestrator.py` tem 19 menções a "inter" e ZERO a "cora" (a única ocorrência da palavra
no arquivo está dentro de "an**cora**do"). O Cora existe no sistema e é usado por outros
módulos — `integrations/banking/adapters/cora.py` — mas o montador do kit nunca soube.

ESTE ORÁCULO MEDE O BURACO, NÃO O TAPA. Buscar o comprovante encosta na API do banco, e
`cora_*` é território a combinar com o T1. Aqui só se afirma a REGRA: existe saída de folha
no extrato de uma competência? Então tem de existir comprovante no kit daquela competência.

💰 SÓ LEITURA. Este arquivo não chama banco nenhum: lê `bank_transactions`, que o sync já
trouxe. Nunca acionar pagamento — o dinheiro já saiu, aqui se procura a prova dele.

⚠️ Vermelho aqui é ACHADO DE OPERAÇÃO, não bug de código: quer dizer que a prova do
pagamento ainda não entrou no kit. Verde quer dizer que o bloco "pagamentos" está honesto.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: O que conta como saída de folha no extrato. Palavra, não código de rubrica: o extrato
#: bancário é texto livre e não tem plano de contas.
PADRAO_FOLHA = "salario|salário|folha|remunera"

#: Os tipos de slot que provam pagamento no kit. Vieram da coluna tipada `document_type`,
#: que tem 52 valores canônicos — não de adivinhação por nome de arquivo.
TIPOS_COMPROVANTE = (
    "comp_salario_individual", "comprovante_va", "comprovante_vt", "comprovante_vr",
    "comp_vt_individual", "comp_va_solides", "comp_vt_va_combinado", "vale_vt_vr",
)

SQL_SAIDAS = text(
    "SELECT date_trunc('month', t.transaction_date)::date AS comp, "
    "       coalesce(ba.bank_name, ba.name, '—') AS banco, "
    "       count(*) AS lancamentos, round(sum(abs(t.amount)), 2) AS total "
    "FROM bank_transactions t "
    "LEFT JOIN bank_accounts ba ON ba.id = t.bank_account_id "
    f"WHERE lower(coalesce(t.description,'')) ~ '{PADRAO_FOLHA}' "
    "  AND t.transaction_date >= :desde "
    "GROUP BY 1, 2 ORDER BY 1 DESC"
)

SQL_COMPROVANTES = text(
    "SELECT date_trunc('month', k.reference_month)::date AS comp, "
    "       count(*) FILTER (WHERE d.file_path IS NOT NULL AND d.file_path <> '') AS com_arquivo, "
    "       count(*) AS slots "
    "FROM ged_kit_documents d JOIN ged_document_kits k ON k.id = d.kit_id "
    "WHERE d.document_type = ANY(:tipos) AND k.reference_month >= :desde "
    "GROUP BY 1"
)


async def main() -> None:
    desde = date(2026, 8, 1)  # a competência em que o Cora entrou no jogo

    async with async_session_factory() as db:
        saidas = (await db.execute(SQL_SAIDAS, {"desde": desde})).mappings().all()
        comps = {
            r["comp"]: r
            for r in (await db.execute(
                SQL_COMPROVANTES, {"tipos": list(TIPOS_COMPROVANTE), "desde": desde}
            )).mappings().all()
        }

        if not saidas:
            print(f"OK nenhuma saída de folha no extrato desde {desde} — nada a provar")
            print("TEST oraculo_comprovante_folha PASS")
            return

        sem_prova = []
        for s in saidas:
            c = comps.get(s["comp"])
            if not c or int(c["com_arquivo"] or 0) == 0:
                sem_prova.append(s)

        if sem_prova:
            det = "; ".join(
                f'{s["comp"]:%m/%Y} {s["banco"]}: {s["lancamentos"]} lançamento(s), '
                f'R$ {s["total"]}, e nenhum comprovante no kit'
                for s in sem_prova[:4]
            )
            raise AssertionError(
                f"{len(sem_prova)} competência(s) com folha PAGA e sem prova no kit — {det}"
            )

        for s in saidas:
            c = comps[s["comp"]]
            print(f'OK {s["comp"]:%m/%Y} {s["banco"]}: R$ {s["total"]} pagos · '
                  f'{c["com_arquivo"]}/{c["slots"]} comprovantes no kit')

    print("TEST oraculo_comprovante_folha PASS")


if __name__ == "__main__":
    asyncio.run(main())
