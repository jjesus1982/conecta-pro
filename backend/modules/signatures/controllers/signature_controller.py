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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.signatures.schemas.signature_schemas import (
    AssinarLoteSchema,
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

from core.auth.dependencies import get_current_active_user
from core.models import User

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
# 2b) MEUS DOCUMENTOS A ASSINAR (funcionário logado — self-service)
# --------------------------------------------------------------------------- #
@router.get(
    "/meus-pendentes",
    summary="Meus documentos pendentes de assinatura (funcionário logado)",
    description="Lista as solicitações de assinatura PENDENTES do funcionário "
    "autenticado, resolvidas por users.employee_id. Base da tela self-service "
    "'Meus documentos a assinar'. O funcionário só vê o que é DELE. Separa em "
    "`a_assinar_agora` (corrente/obrigatório) e `historico_opcional` (competência "
    "antiga ou lote retroativo) — o badge conta só os obrigatórios.",
)
async def meus_pendentes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    if not current_user.employee_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Sua conta não está vinculada a um funcionário (employee_id ausente). "
            "Peça a um administrador para aprovar seu acesso com o perfil 'Funcionário'.",
        )
    svc = UniversalSignatureService(db)
    separado = await svc.pendentes_do_funcionario_separado(current_user.employee_id)
    a_assinar = separado["a_assinar_agora"]
    historico = separado["historico_opcional"]
    return {
        "employee_id": str(current_user.employee_id),
        # M2 — corrente × histórico
        "a_assinar_agora": a_assinar,
        "historico_opcional": historico,
        "total_a_assinar": separado["total_a_assinar"],
        "total_historico": separado["total_historico"],
        # retrocompat: `pendentes` = todos (com flag `opcional`), `total` = tudo.
        "pendentes": a_assinar + historico,
        "total": separado["total_a_assinar"] + separado["total_historico"],
    }


# --------------------------------------------------------------------------- #
# 2c) ASSINAR EM LOTE (funcionário logado — limpa o histórico de uma vez)
# --------------------------------------------------------------------------- #
@router.post(
    "/assinar-lote",
    summary="Assinar várias solicitações do próprio funcionário de uma vez",
    description="Assina em lote (até 50 por chamada) as solicitações do funcionário "
    "autenticado — usado para limpar o histórico opcional de uma vez. Cada documento "
    "vira uma assinatura REAL (hash SHA-256 + evidência). Valida a posse de todas "
    "antes: um id que não seja do funcionário resulta em 403 e nada é assinado.",
)
async def assinar_lote(
    payload: AssinarLoteSchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    if not current_user.employee_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Sua conta não está vinculada a um funcionário (employee_id ausente).",
        )
    svc = UniversalSignatureService(db)
    evidence = _evidence_from(request, payload.evidence)
    try:
        return await svc.assinar_lote(
            employee_id=current_user.employee_id,
            request_ids=payload.request_ids,
            evidence=evidence,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=str(exc))


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

    # SEGURANÇA (self-service): funcionário só assina o que é DELE.
    # Para solicitações EMPLOYEE, resolve o employee_id do assinante e exige que
    # bata com req.signer_id. Aceita tanto o token do Portal (claim employee_id)
    # quanto o token principal/Google (sub=user.id → users.employee_id).
    if signer_type == SignerType.EMPLOYEE:
        eff_employee_id = signer_id
        if eff_employee_id is not None:
            u = await db.execute(select(User).where(User.id == eff_employee_id))
            user_row = u.scalar_one_or_none()
            if user_row is not None:
                # sub era um user.id (token principal/Google): usa o vínculo.
                if not user_row.employee_id:
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail="Sua conta não está vinculada a um funcionário.",
                    )
                eff_employee_id = user_row.employee_id
        if eff_employee_id is None or (
            req.signer_id is not None and str(eff_employee_id) != str(req.signer_id)
        ):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Você não pode assinar um documento que não é seu.",
            )
        signer_id = eff_employee_id

    body_ev = payload.evidence if payload else None
    evidence = _evidence_from(request, body_ev)

    # POLÍTICA DE NÍVEL: EMPRESA assinando CONTRATO → QUALIFIED (ICP-Brasil A1);
    # todo o resto → SIMPLE. Aplicada centralmente aqui, a partir do tipo do doc.
    from modules.signatures.helpers.solicitar_assinatura_documento import (
        nivel_assinatura,
    )

    level = nivel_assinatura(req.document_type or "", signer_type)

    try:
        return await svc.assinar(
            request_id=request_id,
            signer_type=signer_type,
            signer_id=signer_id,
            signer_name=payload.signer_name if payload else None,
            signer_document=payload.signer_document if payload else None,
            evidence=evidence,
            level=level,
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
