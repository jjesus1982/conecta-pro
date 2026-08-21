"""Assinatura registrada tem PDF assinado em disco. Sempre.

🔴 O DEFEITO, medido em 21/08/2026. De 51 documentos marcados como SIGNED/COMPLETED:

     9  tinham o PDF selado em disco
    29  NUNCA tiveram arquivo nenhum (nem original, nem assinado)
     7  apontavam para arquivo que não existe mais
     6  tinham só o original, sem selo

A causa estava em `UniversalSignatureService.assinar`: o selo eletrônico era best-effort —
`if _src:` gerava o PDF quando havia origem, e um `except` engolia a falha. Sem PDF, a
request virava SIGNED do mesmo jeito. E não veio de digitação humana: os registros têm IP
do gateway e device "meu-espaco-web", ou seja, saíram do PORTAL — o Jordan confirmou que
ninguém assinou holerite por lá em julho.

Assinatura sem documento assinado é a mesma família de fabricação que o projeto proíbe no
dado, e aqui ela mente sobre um ATO JURÍDICO: o kit vai ao condomínio com um recibo que
diz assinado e não prova nada.

Afirma a REGRA, não a fotografia: varre todos os assinados a cada rodada, não fixa
quantidade nem tipo. Cresce junto com o produto.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

SQL_ASSINADOS = text(
    "SELECT id::text AS id, document_type, coalesce(signer_name,'?') AS quem, "
    "       coalesce(signed_document_path,'') AS sp "
    "  FROM sig_signature_requests "
    " WHERE status IN ('SIGNED','COMPLETED')"
)


async def main() -> None:
    with get_sync_db() as db:
        linhas = db.execute(SQL_ASSINADOS).mappings().all()

    if not linhas:
        print("SKIP nenhum documento assinado — nada a provar")
        print("TEST oraculo_assinatura_tem_pdf PASS")
        return

    sem_path = [r for r in linhas if not r["sp"]]
    sumido = [r for r in linhas if r["sp"] and not os.path.exists(r["sp"])]

    assert not sem_path, f"{len(sem_path)} de {len(linhas)} assinatura(s) SEM caminho de PDF assinado — " + " ; ".join(
        f"{r['document_type']}/{r['quem'][:18]}" for r in sem_path[:4]
    )
    assert not sumido, (
        f"{len(sumido)} de {len(linhas)} assinatura(s) apontando para arquivo INEXISTENTE — "
        + " ; ".join(f"{r['document_type']}: {r['sp'][-34:]}" for r in sumido[:4])
    )

    print(f"OK {len(linhas)} documento(s) assinado(s), todos com PDF selado em disco")
    print("TEST oraculo_assinatura_tem_pdf PASS")


if __name__ == "__main__":
    asyncio.run(main())
