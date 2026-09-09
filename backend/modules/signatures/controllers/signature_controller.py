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
import os
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from fastapi import status as http_status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.models import User
from modules.signatures.schemas.signature_schemas import (
    AssinarLoteEmpresaSchema,
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
    return SignatureEvidence(ip_address=ip, user_agent=ua, device=device, location=location, extra=extra)


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
    if requested_by is None:  # 08/09/2026: sem token criava solicitação no tenant default
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória.")
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
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Any:
    if _decode_sub(credentials) is None:  # 08/09/2026: status de assinatura era público
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Autenticação obrigatória.")
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


@router.get(
    "/{request_id}/documento",
    summary="PDF de uma solicitação (o assinado, se já houver; senão o original) — para ler antes de assinar",
)
async def documento_da_solicitacao(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """09/09/2026: a central de assinaturas e o portal precisam MOSTRAR o PDF antes do clique. Só o próprio
    signatário (funcionário) ou admin/operador (empresa) enxergam."""
    from fastapi.responses import FileResponse

    svc = UniversalSignatureService(db)
    req = await svc._get_request(request_id)  # noqa: SLF001
    if not req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    eh_admin = (current_user.role or "") in ("admin", "operator")
    eh_dono = current_user.employee_id is not None and str(current_user.employee_id) == str(req.signer_id or "")
    if not (eh_admin or eh_dono):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Sem acesso a este documento.")
    caminho = req.signed_document_path if req.signed_document_path and os.path.exists(req.signed_document_path) else req.document_path
    if not caminho or not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail="PDF da solicitação não está no disco.")
    nome = f"{(req.title or req.document_type or 'documento')[:60]}.pdf".replace("/", "-")
    return FileResponse(caminho, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.post(
    "/empresa/assinar-lote",
    summary="Assina em lote tudo que espera a EMPRESA (central de assinaturas do gestor)",
)
async def assinar_lote_empresa(
    request: Request,
    payload: dict | None = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """09/09/2026: a central de assinaturas (redesign › documentos) assina em lote os pedidos PENDING do lado
    COMPANY — antes só existia o serviço (assinar_lote_empresa) sem rota, e a tela assinava um por vez."""
    if (current_user.role or "") not in ("admin", "operator"):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Só administrador/operador assina pela empresa.")
    try:
        limite = int((payload or {}).get("limite") or 60)
    except (TypeError, ValueError):
        limite = 60
    from modules.operacional.controllers.redesign_write_gate import _otp_generate, _otp_validate_consume

    # 09/09 (Jordan): "pasta com o nome do mês do kit, eu abro e assino todos por lá" → lote por PASTA:
    # pasta = "kit:<kit_id>" (documentos daquele kit/condomínio/mês) ou "tipo:<document_type>" (contratos, comunicados…).
    pasta = ((payload or {}).get("pasta") or "").strip()
    if pasta.startswith("kit:"):
        where_pasta = "AND document_type LIKE 'kit_documento%' AND document_id IN (SELECT id FROM ged_kit_documents WHERE kit_id::text = :pk)"
        pk = pasta[4:]
    elif pasta.startswith("tipo:"):
        where_pasta = "AND document_type = :pk"
        pk = pasta[5:]
    else:
        where_pasta, pk = "", ""
    _ref = f"sig-lote:{current_user.id}:{pasta or 'tudo'}"
    _otp = ((payload or {}).get("otp_code") or "").strip()
    if not _otp:
        n = (await db.execute(sa_text(
            "SELECT count(*) FROM sig_signature_requests WHERE lower(signer_type::text) = 'company' AND status::text = 'PENDING' "
            f"AND (expires_at IS NULL OR expires_at > now()) {where_pasta}"), {"pk": pk})).scalar() or 0
        if not n:
            return {"assinados": [], "falhas": [], "message": "Nada pendente para a empresa nesta pasta."}
    evidence = _evidence_from(request, None)
    # 09/09 (medido): 21 assinaturas ICP-Brasil + Drive levaram 100 s; o nginx corta em 60 s → 504 e a tela dizia
    # "não foi possível salvar" com TUDO assinado por baixo. O lote roda em segundo plano com sessão própria e a
    # resposta volta na hora; a central mostra o andamento (pendentes caindo) ao recarregar.
    import asyncio

    from core.database.session import async_session_factory

    uid, nome = current_user.id, current_user.name

    async def _rodar() -> None:
        async with async_session_factory() as s:
            try:
                r = await UniversalSignatureService(s).assinar_lote_empresa(
                    company_signer_id=uid, signer_name=nome, request_ids=ids, limite=len(ids), evidence=evidence)
                logger.info("Lote da empresa (%s) concluído: %s assinados, %s falhas",
                            pasta or "tudo", len(r.get("assinados") or []), len(r.get("falhas") or []))
            except Exception as exc:  # noqa: BLE001
                logger.error("Lote da empresa (%s) falhou: %s", pasta or "tudo", exc)

    asyncio.create_task(_rodar())
    return {"iniciado": True, "quantidade": len(ids), "pasta": pasta or "todas",
            "message": f"Código confirmado. Assinando {len(ids)} documento(s) com ICP-Brasil em segundo plano "
                       f"(~4 s cada). Recarregue a central para acompanhar; os PDFs assinados vão para o kit e o Drive."}


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
            detail="Solicitação de cliente deve ser assinada pelo link público (POST /signatures/public/{token}).",
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
        if eff_employee_id is None or (req.signer_id is not None and str(eff_employee_id) != str(req.signer_id)):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Você não pode assinar um documento que não é seu.",
            )
        signer_id = eff_employee_id

    # SEGURANÇA (empresa): a assinatura QUALIFIED da razão social usa o certificado
    # ICP-Brasil A1 (fé pública). Só um usuário ADMINISTRADOR autorizado da empresa
    # (Jordan/Pyetra) pode assiná-la — NUNCA um token do Portal do funcionário nem
    # perfis operacionais. Sem isso, qualquer usuário autenticado assinaria contrato
    # em nome da empresa.
    if signer_type == SignerType.COMPANY:
        # 09/09/2026 (Jordan): "gera o código OTP pro meu e-mail e eu assino" — mesmo gate das ações de dinheiro
        # do redesign: 1ª chamada sem otp_code → e-mail com o código + {otp_required, ref}; 2ª com otp_code → assina.
        from modules.operacional.controllers.redesign_write_gate import _otp_generate, _otp_validate_consume

        _ref = f"sig:{request_id}"
        _otp = (payload.otp_code if payload else None) or ""
        if not _otp.strip():
            enviado = await _otp_generate(db, _ref, label="assinatura da empresa", dest=req.title or req.document_type or str(request_id))
            return {"otp_required": True, "ref": _ref,
                    "message": ("Código enviado ao seu e-mail. Digite-o para assinar com o certificado ICP-Brasil da empresa."
                                if enviado else "Código gerado, mas o e-mail falhou — verifique o servidor de e-mail.")}
        if not await _otp_validate_consume(db, _ref, _otp):
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Código OTP inválido ou expirado.")
        req_user_id = _resolve_requester(credentials)
        admin_user = None
        if req_user_id is not None:
            _u = await db.execute(select(User).where(User.id == req_user_id))
            admin_user = _u.scalar_one_or_none()
        if admin_user is None or not admin_user.is_active or (admin_user.role or "") not in ("admin", "operator"):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Assinatura em nome da empresa exige usuário administrador autorizado.",
            )

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


@router.get(
    "/public/{token}/documento",
    summary="Documento a assinar (cliente, via link)",
    description="Entrega o PDF que o cliente vai assinar. Sem autenticação — o token é a "
    "credencial. Sem esta rota o signatário assinaria às cegas.",
)
async def public_document(
    token: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from fastapi.responses import Response  # noqa: PLC0415

    svc = UniversalSignatureService(db)
    req = await svc._get_request_by_token(token)  # noqa: SLF001
    if req is None:
        raise HTTPException(status_code=404, detail="Link de assinatura inválido.")
    # CONTRATO: o documento é RENDERIZADO na hora, não servido do arquivo congelado.
    # O arquivo salvo na abertura mostra "Aguardando assinatura" para as DUAS partes para
    # sempre — inclusive para a CONTRATADA depois de ela assinar, porque o motor sobrepõe
    # um selo mas não redesenha o quadro. O síndico leria um contrato que se contradiz.
    # A prova de integridade continua onde deve: hash congelado na solicitação, hash de
    # cada assinatura em sig_signatures e o manifesto ao final do próprio PDF.
    if (req.document_type or "").lower() in {"contrato", "contract"} and req.reference_code:
        try:
            from modules.crm.services.contract_render import (  # noqa: PLC0415
                renderizar_contrato,
            )

            res = await renderizar_contrato(db, req.reference_code)
            return Response(
                content=res.pdf, media_type="application/pdf",
                headers={"Content-Disposition": 'inline; filename="contrato.pdf"'})
        except Exception:  # noqa: BLE001 — cai para o arquivo salvo, melhor que 500
            logger.warning("public_document: render vivo falhou para %s, servindo o arquivo",
                           req.reference_code, exc_info=True)

    # depois de assinado, o que vale é a via carimbada
    caminho = req.signed_document_path or req.document_path
    if not caminho:
        raise HTTPException(status_code=404, detail="Documento não disponível para este link.")
    try:
        pdf = svc._read_pdf(caminho)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Documento não disponível para este link.")
    if not pdf:
        raise HTTPException(status_code=404, detail="Documento não disponível para este link.")
    # cabeçalho HTTP é latin-1: o travessão de "Contrato CTR-… — CONDOMÍNIO…" derrubava a
    # entrega com UnicodeEncodeError DEPOIS de o PDF já estar lido. Nome do arquivo vira
    # ASCII; o título de verdade continua no PDF.
    import unicodedata  # noqa: PLC0415

    bruto = (req.document_name or "documento").replace('"', "")
    nome = unicodedata.normalize("NFKD", bruto).encode("ascii", "ignore").decode() or "documento"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'})


async def _limite_ok(chave: str, teto: int, janela: int) -> bool:
    """INCR+EXPIRE no Redis. Fail-OPEN: cache com soluço não pode impedir uma assinatura
    legítima — mas o teto existe porque este endpoint DISPARA E-MAIL sem autenticação."""
    try:
        from core.cache.redis import get_redis  # noqa: PLC0415

        r = await get_redis()
        n = await r.incr(chave)
        if n == 1:
            await r.expire(chave, janela)
        return n <= teto
    except Exception:  # noqa: BLE001
        logger.warning("rate limit indisponível para %s — seguindo aberto", chave)
        return True


@router.post(
    "/public/{token}/codigo",
    summary="Envia o código de validação para o e-mail do signatário",
    description="O signatário informa nome, CPF e e-mail; o código de 6 dígitos vai para "
    "esse e-mail. Sem autenticação — o token é a credencial.",
)
async def public_send_code(
    request: Request,
    token: str = Path(...),
    payload: PublicSignSchema | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    from core.mailer import send_email  # noqa: PLC0415

    email = (payload.signer_email if payload else None) or ""
    nome = (payload.signer_name if payload else None) or ""
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail="Informe um e-mail válido para receber o código.")

    svc = UniversalSignatureService(db)
    req = await svc._get_request_by_token(token)  # noqa: SLF001
    if req is None:
        raise HTTPException(status_code=404, detail="Link de assinatura inválido.")
    if req.signed_at:
        raise HTTPException(status_code=409, detail="Este documento já foi assinado por você.")

    ip = request.client.host if request.client else "sem-ip"
    if not await _limite_ok(f"rl:sigcode:ip:{ip}", 10, 3600) or \
       not await _limite_ok(f"rl:sigcode:tok:{token}", 6, 3600):
        raise HTTPException(status_code=429,
                            detail="Muitas tentativas. Aguarde alguns minutos e tente de novo.")

    # o código é o que a solicitação já guarda; guardamos também PARA ONDE ele foi — é essa
    # linha que sustenta a evidência de entrega no manifesto
    req.signer_email = email
    if payload and payload.signer_document:
        req.signer_document = payload.signer_document
    if nome:
        req.signer_name = nome
    await db.commit()

    from modules.crm.services.contract_signature import _html  # noqa: PLC0415

    ok = await send_email(
        email, f"Seu código para assinar — {req.title or 'documento'}",
        _html("Código de validação",
              f"<p>Olá, {nome or req.signer_name}.</p>"
              f"<p>Use o código abaixo para assinar eletronicamente "
              f"<b>{req.title or 'o documento'}</b>:</p>"
              f'<p style="font-size:34px;letter-spacing:10px;font-weight:bold;color:#16277D;'
              f'background:#EEF2FF;border:1px solid #C9D4EA;border-radius:10px;'
              f'padding:16px;text-align:center;margin:18px 0">{req.access_code}</p>'
              "<p>O código é pessoal. Se você não solicitou, ignore esta mensagem — "
              "nada será assinado.</p>"))
    if not ok:
        raise HTTPException(status_code=502,
                            detail="Não conseguimos enviar o e-mail agora. Tente novamente.")
    dominio = email.split("@")[-1]
    return {"enviado": True, "para": f"{email[:2]}***@{dominio}"}


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

    # ORDEM, só para CONTRATO. O motor guarda `signature_order` e nunca o exige — e não dá
    # para exigir globalmente: comunicado (162 de 165 pedidos) e holerite usam ordem
    # escalonada e assinam fora de ordem o tempo todo; travar lá quebraria produção.
    # No contrato a ordem é decisão do Jordan e tem efeito jurídico: o cliente não pode
    # firmar um instrumento que a CONTRATADA ainda não firmou. Link vaza, é encaminhado e
    # vale 30 dias — processo não é trava.
    if not await _limite_ok(f"sig:pin:{token}", 6, 900):  # 08/09/2026: PIN de 6 dígitos sem limite de tentativas
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos e peça um novo código.")
    req_ord = await svc._get_request_by_token(token)  # noqa: SLF001
    if req_ord is not None and (req_ord.document_type or "").lower() in {"contrato", "contract"}:
        pendente_antes = (await db.execute(sa_text(
            "SELECT signer_name FROM sig_signature_requests "
            "WHERE reference_code = :k AND signature_order < :o AND signed_at IS NULL "
            "ORDER BY signature_order LIMIT 1"),
            {"k": req_ord.reference_code, "o": req_ord.signature_order or 1})).scalar()
        if pendente_antes:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="Este contrato ainda não foi assinado pela Conecta Mais. "
                       "Assim que a assinatura da contratada for registrada, você poderá "
                       "assinar por este mesmo link.")

    try:
        res = await svc.assinar_por_token(
            access_token=token,
            access_code=payload.access_code if payload else None,
            signer_name=payload.signer_name if payload else None,
            signer_document=payload.signer_document if payload else None,
            signer_email=payload.signer_email if payload else None,
            evidence=evidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e))

    # CONTRATO: manda a via a quem assinou e, quando todos assinarem, avisa as partes.
    # Dentro de try: e-mail que falha NÃO pode derrubar uma assinatura já registrada.
    if req_ord is not None and (req_ord.document_type or "").lower() in {"contrato", "contract"}:
        try:
            from modules.crm.services.contract_render import (  # noqa: PLC0415
                renderizar_contrato,
            )
            from modules.crm.services.contract_signature import (  # noqa: PLC0415
                notificar_apos_assinatura,
            )

            r = await renderizar_contrato(db, req_ord.reference_code)
            res["envio"] = await notificar_apos_assinatura(db, req_ord.reference_code, r.pdf)
        except Exception:  # noqa: BLE001
            logger.warning("public_sign: envio de e-mail falhou para %s (assinatura mantida)",
                           req_ord.reference_code, exc_info=True)
            res["envio"] = {"erro": "não foi possível enviar a cópia por e-mail"}
    return res


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
