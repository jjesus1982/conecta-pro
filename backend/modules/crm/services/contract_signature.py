"""Assinatura eletrônica do contrato — Conecta Mais assina, cliente assina por link.

Fecha o ciclo que faltava: até 21/08/2026 o contrato saía em PDF e a assinatura acontecia
fora do sistema. Agora o instrumento é firmado no próprio Conecta PRO, com evidência.

Reusa o MOTOR UNIVERSAL (`modules/signatures`), que já existia e já fazia tudo:
`criar_solicitacao_assinatura` com signatários em ordem, `assinar` para quem tem login e
`assinar_por_token` para quem recebe o link. Não escrevi motor de assinatura nenhum — o
que faltava era ninguém ter ligado o contrato nele.

ORDEM DOS SIGNATÁRIOS (decisão do Jordan, 21/08): a CONTRATADA assina primeiro, pelo
painel; depois o link vai para o cliente. Faz sentido no fluxo comercial — não se manda
para o síndico assinar um documento que a própria empresa ainda não firmou.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BASE_PUBLICA = "https://erp.conectamais.pro"


@dataclass
class Solicitacao:
    request_id_empresa: str | None
    request_id_cliente: str | None
    token_cliente: str | None
    link_cliente: str | None
    documento_hash: str


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def abrir_assinatura(db: AsyncSession, contract_id: str, pdf: bytes, *,
                           contratante_nome: str, representante: str, representante_cpf: str,
                           representante_email: str | None, contratada_nome: str,
                           assinante_empresa: str, assinante_empresa_id: uuid.UUID | None,
                           solicitado_por: uuid.UUID | None = None) -> Solicitacao:
    """Abre a solicitação de assinatura das duas partes para este contrato."""
    from modules.signatures.services.universal_signature_service import (
        SignerInput,
        SignerType,
        UniversalSignatureService,
    )

    doc_hash = _sha256(pdf)
    svc = UniversalSignatureService(db)
    res = await svc.criar_solicitacao_assinatura(
        document_type="contrato",
        document_id=uuid.uuid4(),
        signers=[
            # ordem 1: a empresa. Não se pede ao síndico que assine o que a Conecta Mais
            # ainda não firmou.
            SignerInput(signer_type=SignerType.COMPANY, signer_name=assinante_empresa,
                        signer_id=assinante_empresa_id, order=1),
            # ordem 2: o cliente, por link único
            SignerInput(signer_type=SignerType.CUSTOMER, signer_name=representante,
                        signer_document=representante_cpf, signer_email=representante_email,
                        order=2),
        ],
        document_name=f"Contrato {contract_id} — {contratante_nome}",
        document_hash=doc_hash,
        requested_by=solicitado_por,
        purpose="signature",
        expires_in_days=30,
        reference_code=contract_id,
        metadata={"contrato": contract_id, "contratada": contratada_nome},
    )

    pedidos = res.get("requests") or []
    emp = next((p for p in pedidos if str(p.get("signer_type", "")).endswith("company")), None)
    cli = next((p for p in pedidos if str(p.get("signer_type", "")).endswith("customer")), None)
    token = (cli or {}).get("public_token")
    return Solicitacao(
        request_id_empresa=str(emp.get("id")) if emp else None,
        request_id_cliente=str(cli.get("id")) if cli else None,
        token_cliente=token,
        link_cliente=f"{BASE_PUBLICA}/assinar/{token}" if token else None,
        documento_hash=doc_hash,
    )


# `sig_signature_requests` (1.749 linhas — o motor está em uso de verdade). O hash da
# assinatura fica em sig_signatures; o do documento assinado, na própria solicitação.
_SQL_ASSIN = """
SELECT r.signer_type::text AS papel, r.signer_name AS nome, r.signed_at,
       coalesce(r.signed_document_hash, r.document_hash, '') AS hash,
       r.signing_ip
FROM sig_signature_requests r
WHERE r.reference_code = :k AND r.signed_at IS NOT NULL
ORDER BY r.signature_order, r.signed_at
"""


async def assinaturas_do_contrato(db: AsyncSession, contract_id: str) -> list[dict]:
    """As assinaturas JÁ coletadas — é o que o bloco final do PDF exibe.

    Devolve lista vazia quando ninguém assinou: o contrato então sai com "Aguardando
    assinatura eletrônica", que é honesto. Nunca inventa carimbo.
    """
    try:
        linhas = (await db.execute(text(_SQL_ASSIN), {"k": contract_id})).mappings().all()
    except Exception:  # noqa: BLE001 — tabela/coluna ausente neste ambiente
        await db.rollback()
        return []
    saida = []
    for r in linhas:
        papel = "contratada" if "company" in (r["papel"] or "") else "contratante"
        quando = r["signed_at"]
        saida.append({
            "papel": papel,
            "nome": r["nome"],
            "quando": quando.strftime("%d/%m/%Y às %H:%M") if quando else "",
            "hash": r["hash"] or "",
            "ip": r["signing_ip"] or "",
        })
    return saida
