"""
Signature Controller — API REST do motor de assinatura universal.

Endpoints (montados sob /api/v1/signatures):

- POST   /signatures/requests                       criar solicitação (admin)
- GET    /signatures/document/{document_type}/{document_id}   status por documento
- POST   /signatures/{request_id}/sign              assinar (funcionário OU empresa)
- GET    /signatures/verify/{signature_hash}        verificar assinatura por hash
- GET    /signatures/public/{token}                 dados p/ o cliente (link seguro)
- POST   /signatures/public/{token}                 cliente assina (link seguro)

Auth:
- /requests, /{id}/sign, /verify  → admin (CurrentActiveUser) para EMPRESA,
  ou funcionário (Portal JWT) para EMPLOYEE. O endpoint /sign aceita ambos:
  resolve o assinante conforme o signer_type da própria request.
- /public/{token}  → SEM auth (token de uso único é a credencial).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.signatures.schemas.signature_schemas import (
    CreateSignatureRequestSchema,
    PublicSignSchema,
    SignRequestSchema,
    VerifyResponseSchema,
)
from modules.signatures.services.universal_signature_service import (
    SignatureEvidence,
    SignerInput,
    SignerType,
    UniversalSignatureService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signatures", tags=["Assinatura Universal"])

_bearer = HTTPBearer(auto_error=False)


def _evidence_from(request: Request, body_ev: Any = None) -> SignatureEvidence:
    """Monta as evidências a partir do Request (IP/UA) + corpo (device/location)."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    device = None
    location = None
    extra: dict[str, Any] = {}
    if body_ev is not None:
        device = getattr(body_ev, "device", None)
        location = getattr(body_ev, "location", None)
        extra = getattr(body_ev, "extra", None) or {}
    return SignatureEvidence(
        ip_address=ip, user_agent=ua, device=device, location=location, extra=extra
    )


# --------------------------------------------------------------------------- #
# 1) CRIAR SOLICITAÇÃO (admin)
# --------------------------------------------------------------------------- #
@router.post(
    "/requests",
    status_code=201,
    summary="Criar solicitação de assinatura",
    description="Cria uma solicitação de assinatura para 1..N signatários "
    "(funcionário, empresa e/ou cliente). Para clientes, retorna o token do link.",
)
async def criar_solicitacao(
    payload: CreateSignatureRequestSchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Any:
    """Cria a solicitação. Requer Bearer (admin ou portal); usa o sub como requester."""
    requested_by = _resolve_requester(credentials)
    svc = UniversalSignatureService(db)

    try:
        signers = [
            SignerInput(
                signer_type=SignerType(s.signer_type),
                signer_name=s.signer_name,
                signer_id=s.signer_id,
                signer_email=s.signer_email,
                signer_phone=s.signer_phone,
                signer_document=s.signer_document,
                order=s.order,
            )
            for s in payload.signers
        ]
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"signer_type inválido: {e}. Aceitos: employee, company, customer.",
        )

    try:
        return await svc.criar_solicitacao_assinatura(
            document_type=payload.document_type,
            document_id=payload.document_id,
            signers=signers,
            title=payload.title,
            document_name=payload.document_name,
            document_path=payload.document_path,
            document_hash=payload.document_hash,
            requested_by=requested_by,
            purpose=payload.purpose,
            expires_in_days=payload.expires_in_days,
            reference_code=payload.reference_code,
            metadata=payload.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))


# --------------------------------------------------------------------------- #
# 2) STATUS POR DOCUMENTO
# --------------------------------------------------------------------------- #
@router.get(
    "/document/{document_type}/{document_id}",
    summary="Status de assinatura de um documento",
    description="Retorna o status de todos os signatários de um documento.",
)
async def status_documento(
    document_type: str = Path(...),
    document_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = UniversalSignatureService(db)
    return await svc.status(document_type=document_type, document_id=document_id)


# --------------------------------------------------------------------------- #
# 3) ASSINAR (funcionário OU empresa, autenticado)
# --------------------------------------------------------------------------- #
@router.post(
    "/{request_id}/sign",
    summary="Assinar documento (funcionário ou empresa)",
    description="Coleta a assinatura de uma solicitação. O tipo de assinante é o "
    "definido na própria solicitação (employee/company). Requer Bearer.",
)
async def assinar(
    request: Request,
    request_id: uuid.UUID = Path(...),
    payload: SignRequestSchema | None = None,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Any:
    if not credentials:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso não fornecido.",
        )

    svc = UniversalSignatureService(db)
    # descobre o signer_type exigido pela request
    req = await svc._get_request(request_id)  # noqa: SLF001 (uso interno controlado)
    if req is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    try:
        signer_type = SignerType(str(req.signer_type))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"signer_type inválido na solicitação: {req.signer_type}")

    if signer_type == SignerType.CUSTOMER:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Solicitação de cliente deve ser assinada pelo link público "
            "(POST /signatures/public/{token}).",
        )

    signer_id = _resolve_signer_id(credentials)
    body_ev = payload.evidence if payload else None
    evidence = _evidence_from(request, body_ev)

    try:
        return await svc.assinar(
            request_id=request_id,
            signer_type=signer_type,
            signer_id=signer_id,
            signer_name=payload.signer_name if payload else None,
            signer_document=payload.signer_document if payload else None,
            evidence=evidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))


# --------------------------------------------------------------------------- #
# 4) VERIFICAR
# --------------------------------------------------------------------------- #
@router.get(
    "/verify/{signature_hash}",
    response_model=VerifyResponseSchema,
    summary="Verificar assinatura por hash",
    description="Verifica a autenticidade/validade de uma assinatura pelo hash SHA-256.",
)
async def verificar(
    signature_hash: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = UniversalSignatureService(db)
    result = await svc.verificar(signature_hash)
    return VerifyResponseSchema(**{k: result.get(k) for k in VerifyResponseSchema.model_fields})


# --------------------------------------------------------------------------- #
# 5) LINK PÚBLICO DO CLIENTE (sem auth)
# --------------------------------------------------------------------------- #
@router.get(
    "/public/{token}",
    summary="Dados da solicitação (cliente, via link)",
    description="Retorna os dados públicos da solicitação para o cliente antes de "
    "assinar. Sem autenticação — o token é a credencial.",
)
async def public_info(
    token: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = UniversalSignatureService(db)
    req = await svc._get_request_by_token(token)  # noqa: SLF001
    if req is None:
        raise HTTPException(status_code=404, detail="Link de assinatura inválido.")
    from modules.ai.signature.models.signature_request import RequestStatus

    return {
        "request_id": str(req.id),
        "title": req.title,
        "document_type": req.document_type,
        "document_name": req.document_name,
        "signer_name": req.signer_name,
        "requires_pin": bool(req.access_code),
        "status": str(req.status),
        "already_signed": req.status in (RequestStatus.SIGNED, RequestStatus.COMPLETED),
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "is_expired": req.is_expired,
    }


@router.post(
    "/public/{token}",
    summary="Cliente assina via link seguro",
    description="Coleta a assinatura de um cliente pelo link de uso único. "
    "Sem autenticação — exige o token e (se configurado) o PIN.",
)
async def public_sign(
    request: Request,
    token: str = Path(...),
    payload: PublicSignSchema | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = UniversalSignatureService(db)
    body_ev = payload.evidence if payload else None
    evidence = _evidence_from(request, body_ev)
    try:
        return await svc.assinar_por_token(
            access_token=token,
            access_code=payload.access_code if payload else None,
            signer_name=payload.signer_name if payload else None,
            signer_document=payload.signer_document if payload else None,
            evidence=evidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))


# --------------------------------------------------------------------------- #
# Helpers de auth (extração de sub do JWT admin OU portal, sem forçar audience)
# --------------------------------------------------------------------------- #
def _decode_sub(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """Extrai o 'sub' do JWT (admin ou portal), sem validar audience.

    Aceita tanto o token admin quanto o do portal do funcionário. A validação
    de assinatura é feita; a audience é ignorada para permitir os dois emissores.
    """
    if not credentials:
        return None
    from jose import jwt
    from jose.exceptions import JWTError

    from core.config import settings

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        return None
    return payload.get("employee_id") or payload.get("sub")


def _resolve_requester(credentials: HTTPAuthorizationCredentials | None) -> uuid.UUID | None:
    sub = _decode_sub(credentials)
    try:
        return uuid.UUID(sub) if sub else None
    except (ValueError, TypeError):
        return None


def _resolve_signer_id(credentials: HTTPAuthorizationCredentials | None) -> uuid.UUID | None:
    return _resolve_requester(credentials)
