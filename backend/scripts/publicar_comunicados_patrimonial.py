# -*- coding: utf-8 -*-
"""Publica os COMUNICADOS INTERNOS da Patrimonial no fluxo de assinatura do app.

Para cada comunicado:
  1) cria a solicitação (document_type='comunicado') com a EMPRESA (COMPANY) +
     CADA funcionário CLT ativo (EMPLOYEE, ciência), gravando empresa_slug;
  2) a EMPRESA assina em nível QUALIFIED (ICP-Brasil, cert A1 da Patrimonial);
  3) os funcionários passam a ver o comunicado em "Meus documentos a assinar"
     (Meu Espaço) e dão ciência (eletrônica simples).

Idempotente: document_id é determinístico (uuid5); reexecutar não duplica.
Roster: funcionários DISTINTOS da Patrimonial em status ativo/afastado/suspenso
(exclui PJ e demitidos). Rodar:
  docker exec -e PYTHONPATH=/app conecta-pro-backend python /app/scripts/publicar_comunicados_patrimonial.py
"""
import asyncio
import hashlib
import uuid

from sqlalchemy import text

from core.database.session import async_session_factory
from modules.signatures.services.universal_signature_service import (
    SignatureLevel,
    SignerInput,
    SignerType,
    UniversalSignatureService,
)

PDF_DIR = "/app/uploads/comunicados_out"
EMPRESA_SLUG = "conecta_patrimonial"
EMPRESA_RAZAO = "CONECTAMAIS PATRIMONIAL LTDA"
EMPRESA_CNPJ = "66.014.833/0001-10"
ADMIN_USER_ID = uuid.UUID("ad9abb59-55fb-444e-a04f-0e1f22541de3")  # jjesus@conectamais.pro (admin)
NS = uuid.uuid5(uuid.NAMESPACE_URL, "comunicado-patrimonial")

COMUNICADOS = [
    ("Comunicado_01_Consignado", "Comunicado 01/2026 — Suspensão temporária do desconto do consignado"),
    ("Comunicado_02_Reorganizacao", "Comunicado 02/2026 — Reorganização: você agora é Conecta Mais Patrimonial"),
    ("Comunicado_03_Pagamento", "Comunicado 03/2026 — Nova forma de pagamento do salário"),
]

ROSTER_SQL = text(
    """
    SELECT DISTINCT e.id, e.nome, e.cpf
    FROM employees e JOIN empresas em ON em.id = e.empresa_id
    WHERE em.slug = :slug
      AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
    ORDER BY e.nome
    """
)


async def _roster(db) -> list:
    rows = (await db.execute(ROSTER_SQL, {"slug": EMPRESA_SLUG})).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


async def _publicar(db, nome: str, titulo: str, roster: list) -> str:
    svc = UniversalSignatureService(db)
    document_id = str(uuid.uuid5(NS, nome))
    atual = await svc.status(document_type="comunicado", document_id=document_id)
    if atual.get("total_signers", 0) > 0:
        return f"JÁ PUBLICADO ({atual['total_signers']} signatários) — pulado"

    pdf_path = f"{PDF_DIR}/{nome}.pdf"
    with open(pdf_path, "rb") as fh:
        doc_hash = hashlib.sha256(fh.read()).hexdigest()

    signers = [
        SignerInput(
            signer_type=SignerType.COMPANY,
            signer_name=f"{EMPRESA_RAZAO} (JORDAN JESUS)",
            signer_id=ADMIN_USER_ID,
            signer_document=EMPRESA_CNPJ,
            order=1,
        )
    ]
    for i, (eid, enome, ecpf) in enumerate(roster, start=2):
        signers.append(
            SignerInput(
                signer_type=SignerType.EMPLOYEE,
                signer_name=enome or "Funcionário",
                signer_id=eid,
                signer_document=ecpf,
                order=i,
            )
        )

    res = await svc.criar_solicitacao_assinatura(
        document_type="comunicado",
        document_id=document_id,
        signers=signers,
        title=titulo,
        document_path=pdf_path,
        document_hash=doc_hash,
        requested_by=ADMIN_USER_ID,
        metadata={"empresa_slug": EMPRESA_SLUG},
    )

    # EMPRESA assina qualificada (ICP-Brasil, cert da Patrimonial)
    company_req = next(r["id"] for r in res["requests"] if r["signer_type"] == str(SignerType.COMPANY))
    r = await svc.assinar(
        request_id=uuid.UUID(company_req),
        signer_type=SignerType.COMPANY,
        signer_id=ADMIN_USER_ID,
        signer_name="JORDAN JESUS",
        level=SignatureLevel.QUALIFIED,
        certificate_ref={"pdf_path": pdf_path},
    )
    cert = (r.get("certificate") or {}).get("subject") or ""
    ok = "66014833000110" in cert
    return f"criado: 1 empresa + {len(roster)} ciência · empresa assinou={'PATRIMONIAL ✓' if ok else cert}"


async def main() -> None:
    async with async_session_factory() as db:
        roster = await _roster(db)
        print(f"Roster CLT Patrimonial (ciência): {len(roster)} funcionários distintos")
        for nome, titulo in COMUNICADOS:
            msg = await _publicar(db, nome, titulo, roster)
            print(f"  {nome}: {msg}")
        await db.commit()
        print("PUBLICAÇÃO CONCLUÍDA")


if __name__ == "__main__":
    asyncio.run(main())
