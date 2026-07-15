"""
Helper único de solicitação de assinatura para os geradores de documento.

Todo gerador de PDF que produz um documento assinável chama UMA função daqui —
`garantir_solicitacao_assinatura` (async) ou `garantir_solicitacao_assinatura_sync`
(para endpoints síncronos, ex. folha) — passando o tipo do documento, o id e o
contexto (funcionário, cliente). O helper:

1. Aplica a POLÍTICA DE ASSINANTE por tipo de documento (definida pelo Jordan):
     contract       → EMPLOYEE + COMPANY
     proposal       → COMPANY + CUSTOMER
     recibo_vt_vr   → EMPLOYEE
     payslip        → EMPLOYEE
     aviso_previo   → EMPLOYEE + COMPANY
     rescisao       → EMPLOYEE + COMPANY
     licitacao      → COMPANY
   (ficha_epi NÃO passa por aqui — continua no fluxo portal_digital_signatures.)

2. É IDEMPOTENTE: se já existe solicitação para (document_type, document_id),
   não cria outra — devolve o status atual. Assim, gerar o PDF N vezes não
   duplica signatários.

3. NUNCA quebra a geração do PDF: qualquer erro aqui é logado e engolido
   (retorna None), pois a assinatura é um efeito colateral do gerador — o
   download do documento não pode falhar por causa dela.

O motor (UniversalSignatureService) é consumido exatamente pelo contrato
publicado; este helper apenas monta os SignerInput conforme a política.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.signatures.services.universal_signature_service import (
    SignatureLevel,
    SignerInput,
    SignerType,
    UniversalSignatureService,
)

logger = logging.getLogger(__name__)

# Empresa (assinante COMPANY) — fonte da verdade da razão social/CNPJ (memória).
EMPRESA_RAZAO = "CONECTAMAIS ELETRONICA LTDA"
EMPRESA_CNPJ = "35.710.481/0001-03"
EMPRESA_REPRESENTANTE = "JORDAN JESUS"

# Política: quais tipos de assinante cada tipo de documento exige, na ordem.
#   contract          → contrato de TRABALHO (funcionário + empresa)
#   service_contract  → contrato de SERVIÇO com cliente (cliente + empresa)
POLITICA_ASSINANTES: dict[str, list[SignerType]] = {
    "contract": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "service_contract": [SignerType.CUSTOMER, SignerType.COMPANY],
    "proposal": [SignerType.COMPANY, SignerType.CUSTOMER],
    "recibo_vt_vr": [SignerType.EMPLOYEE],
    "payslip": [SignerType.EMPLOYEE],
    # Espelho de ponto mensal (Portaria 671): o FUNCIONÁRIO homologa (assina) o
    # espelho do mês FECHADO no Meu Espaço. A empresa não co-assina digitalmente
    # (o bloco de assinatura da empresa consta no PDF); nível SIMPLE (SHA-256).
    "espelho_ponto": [SignerType.EMPLOYEE],
    "aviso_previo": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "rescisao": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "licitacao": [SignerType.COMPANY],
    # Documento do KIT GEDEON (contracheque/ponto/VT-VA-VR/contrato/ficha/férias/
    # aviso/rescisão montados no kit por condomínio) → o FUNCIONÁRIO assina.
    # A empresa NÃO co-assina docs do kit; ficha_epi tem fluxo próprio (fora daqui).
    "kit_documento": [SignerType.EMPLOYEE],
}

# Política de NÍVEL legal por (document_type). Decisão do Jordan:
#   Assinatura QUALIFICADA ICP-Brasil (A1) SÓ para CONTRATOS — e somente do lado
#   da EMPRESA (COMPANY), que é a titular do certificado. Funcionário e cliente
#   não têm certificado próprio: assinam sempre em nível SIMPLE (SHA-256).
#   Todos os demais document_types usam SIMPLE para todos os signatários.
DOCUMENTOS_QUALIFICADOS: frozenset[str] = frozenset({"contract", "service_contract"})


def nivel_assinatura(document_type: str, signer_type: SignerType) -> SignatureLevel:
    """Nível legal exigido para (document_type × signer_type).

    Regra única e testável:
      - COMPANY assinando um CONTRATO (contract | service_contract) → QUALIFIED (A1).
      - Qualquer outro caso (outros tipos de doc, ou EMPLOYEE/CUSTOMER) → SIMPLE.

    Args:
        document_type: Tipo do documento.
        signer_type: Tipo do assinante.

    Returns:
        SignatureLevel.QUALIFIED ou SignatureLevel.SIMPLE.
    """
    if signer_type == SignerType.COMPANY and document_type in DOCUMENTOS_QUALIFICADOS:
        return SignatureLevel.QUALIFIED
    return SignatureLevel.SIMPLE


def document_hash_sha256(pdf_bytes: bytes | None) -> str | None:
    """SHA-256 (hex) do conteúdo do PDF, quando os bytes estiverem disponíveis."""
    if not pdf_bytes:
        return None
    return hashlib.sha256(pdf_bytes).hexdigest()


def _build_signers(
    tipos: list[SignerType],
    *,
    employee_id: uuid.UUID | str | None,
    employee_name: str | None,
    employee_document: str | None,
    customer_name: str | None,
    customer_email: str | None,
    customer_document: str | None,
    company_signer_id: uuid.UUID | str | None,
) -> list[SignerInput]:
    """Monta os SignerInput na ordem da política, a partir do contexto do doc."""
    signers: list[SignerInput] = []
    for idx, tipo in enumerate(tipos, start=1):
        if tipo == SignerType.EMPLOYEE:
            signers.append(
                SignerInput(
                    signer_type=SignerType.EMPLOYEE,
                    signer_name=employee_name or "Funcionário",
                    signer_id=_coerce_uuid(employee_id),
                    signer_document=employee_document,
                    order=idx,
                )
            )
        elif tipo == SignerType.COMPANY:
            signers.append(
                SignerInput(
                    signer_type=SignerType.COMPANY,
                    signer_name=f"{EMPRESA_RAZAO} ({EMPRESA_REPRESENTANTE})",
                    signer_id=_coerce_uuid(company_signer_id),
                    signer_document=EMPRESA_CNPJ,
                    order=idx,
                )
            )
        elif tipo == SignerType.CUSTOMER:
            signers.append(
                SignerInput(
                    signer_type=SignerType.CUSTOMER,
                    signer_name=customer_name or "Cliente",
                    signer_email=customer_email,
                    signer_document=customer_document,
                    order=idx,
                )
            )
    return signers


def _coerce_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def garantir_solicitacao_assinatura(
    db: AsyncSession,
    *,
    document_type: str,
    document_id: str,
    title: str,
    document_hash: str | None = None,
    document_path: str | None = None,
    employee_id: uuid.UUID | str | None = None,
    employee_name: str | None = None,
    employee_document: str | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
    customer_document: str | None = None,
    company_signer_id: uuid.UUID | str | None = None,
    requested_by: uuid.UUID | str | None = None,
) -> dict[str, Any] | None:
    """Garante que exista uma solicitação de assinatura para o documento (idempotente).

    Aplica a POLÍTICA por document_type e chama o motor. Se já houver solicitação,
    devolve o status atual sem criar outra. Erros são engolidos (retorna None) para
    nunca quebrar a geração do PDF.

    Returns:
        dict com o resultado do motor (chave "created": bool). Para propostas,
        inclui "public_token" do link do cliente. None em caso de erro.
    """
    tipos = POLITICA_ASSINANTES.get(document_type)
    if not tipos:
        # Documento sem política de assinatura (ex.: NFS-e) — nada a fazer.
        return None

    try:
        svc = UniversalSignatureService(db)

        # Idempotência: já existe solicitação para este documento?
        atual = await svc.status(document_type=document_type, document_id=str(document_id))
        if atual.get("total_signers", 0) > 0:
            atual["created"] = False
            atual["public_token"] = _extract_public_token(atual)
            return atual

        signers = _build_signers(
            tipos,
            employee_id=employee_id,
            employee_name=employee_name,
            employee_document=employee_document,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_document=customer_document,
            company_signer_id=company_signer_id,
        )

        result = await svc.criar_solicitacao_assinatura(
            document_type=document_type,
            document_id=str(document_id),
            signers=signers,
            title=title,
            document_hash=document_hash,
            document_path=document_path,
            requested_by=_coerce_uuid(requested_by),
        )
        result["created"] = True
        # Expõe o token do cliente (proposta) no topo, para o endpoint devolver o link.
        for r in result.get("requests", []):
            if r.get("public_token"):
                result["public_token"] = r["public_token"]
                break
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Falha ao garantir solicitação de assinatura (doc_type=%s doc_id=%s): %s",
            document_type,
            document_id,
            exc,
        )
        return None


def _extract_public_token(status: dict[str, Any]) -> str | None:
    """Token do cliente não é exposto pelo status(); devolvido só na criação."""
    return None


def _engine_sync_nullpool():
    """Engine DEDICADA com NullPool para os helpers `_sync` (asyncio.run cria um loop
    novo a cada chamada; o pool GLOBAL prende conexões asyncpg ao loop de origem → erro
    'got Future attached to a different loop'). NullPool abre/fecha conexão por uso."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from core.config import settings

    eng = create_async_engine(settings.database_url, poolclass=NullPool)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def status_documento_sync(document_type: str, document_id: str) -> dict[str, Any] | None:
    """Versão síncrona de status() para endpoints `def` (ex.: folha/recibo VT-VR)."""
    async def _run() -> dict[str, Any] | None:
        eng, factory = _engine_sync_nullpool()
        try:
            async with factory() as session:
                return await UniversalSignatureService(session).status(
                    document_type=document_type, document_id=str(document_id)
                )
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao consultar status de assinatura (sync): %s", exc)
        return None


def garantir_solicitacao_assinatura_sync(**kwargs: Any) -> dict[str, Any] | None:
    """Versão síncrona para endpoints `def` (ex.: folha/recibo VT-VR).

    Abre uma AsyncSession própria de curta duração e roda o fluxo async.
    Seguro em rotas síncronas do FastAPI (executam num worker thread sem event
    loop). Nunca quebra o chamador: erros retornam None.
    """
    async def _run() -> dict[str, Any] | None:
        eng, factory = _engine_sync_nullpool()
        try:
            async with factory() as session:
                return await garantir_solicitacao_assinatura(session, **kwargs)
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_run())
    except RuntimeError:
        # Já existe event loop rodando neste contexto — cai fora sem quebrar o PDF.
        logger.warning(
            "garantir_solicitacao_assinatura_sync chamado dentro de event loop ativo; ignorado."
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha na solicitação de assinatura (sync): %s", exc)
        return None
