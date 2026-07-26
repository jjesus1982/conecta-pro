"""
Controller (endpoints) para Proposal.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.proposal import ProposalStatus, ProposalType
from modules.crm.repositories.proposal_repository import ProposalRepository
from modules.crm.schemas.proposal import (
    ProposalApprovalRequest,
    ProposalCreate,
    ProposalCreateFromOpportunity,
    ProposalDetailResponse,
    ProposalFilter,
    ProposalItemCreate,
    ProposalItemResponse,
    ProposalListResponse,
    ProposalResponse,
    ProposalStats,
    ProposalTemplateCreate,
    ProposalTemplateResponse,
    ProposalTemplateUpdate,
    ProposalUpdate,
)
from modules.crm.services.pipeline_sync import ensure_contract_for_proposal, sync_opportunity_for_proposal
from modules.crm.services.timeline import log_activity

router = APIRouter(prefix="/proposals", tags=["CRM - Proposals"])

# --- Endurecimento do link público de assinatura (task 5.4c-2, 2026-07-26) --------------------
# Rota é CLIENTE-FACING/cria contrato: UUID vazado (WhatsApp) permitiria assinar como qualquer um.
# Defesa em 2 camadas SEM quebrar links já enviados antes desta mudança (transição não-quebra):
#   1) rate-limit por IP e por proposta (HARD, sem exceção — fecha brute-force).
#   2) token assinado (?t=) nos links NOVOS: presente+válido=ok; presente+inválido/expirado=403;
#      AUSENTE (link legado)=permitido + audit, NUNCA hard-bloqueado.
# Endurecimento forte (hard-require token, OU OTP ao telefone, OU binding) é decisão de UX do
# Jordan — não implementado aqui, ver follow-up no relatório da task.
_SIGN_TOKEN_SALT = b"crm-proposal-sign-v1"
_SIGN_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 dias, mesma janela usada pra gerar o token no envio


async def _rate_limit_ok(key: str, limit: int, window_seconds: int) -> bool:
    """INCR+EXPIRE simples no Redis (o projeto já usa Redis — core.cache.redis). True = dentro
    do limite (já contou esta tentativa). Fail-OPEN se o Redis estiver indisponível: um endpoint
    que cria contrato/cliente não pode ficar refém de um hiccup do cache — loga warning pro
    Jordan investigar, mas não derruba a assinatura legítima.

    NÃO usamos o decorator @limiter.limit() (slowapi) aqui: stackar duas instâncias dele (uma
    por IP, outra por proposta) quebra com 'response must be an instance of Response' porque os
    endpoints devolvem dict, não Response — confirmado na bancada de teste desta task."""
    try:
        from core.cache.redis import get_redis  # noqa: PLC0415

        client = await get_redis()
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
        return current <= limit
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"rate-limit indisponível (Redis) — permitindo por fail-open: {exc}")
        return True


def _client_ip(request: Request) -> str | None:
    """IP real do cliente atrás do proxy (nginx->frontend->backend) — 1º hop do XFF."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def _verify_sign_token(proposal_id: str, token: str | None) -> bool:
    """True = token assinado válido p/ esta proposta. False = ausente/inválido/expirado (nunca
    levanta exceção — quem chama decide o que fazer com "ausente" vs "inválido").

    HMAC-SHA256 puro (stdlib) — sem depender de itsdangerous, que NÃO está no requirements.txt
    do projeto (evita adicionar dependência nova pra um gate de segurança pequeno). Mesmo
    esquema (secret+salt) do gerador em modules/integrations/connectors/whatsapp/agent_service.py
    (_gen_sign_token) — têm que interoperar."""
    if not token:
        return False
    try:
        import base64
        import hashlib
        import hmac
        import time

        from core.config import settings  # noqa: PLC0415

        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        pid_part, ts_part, sig_part = raw.split("|", 2)
        if pid_part != str(proposal_id):
            return False
        if (int(time.time()) - int(ts_part)) > _SIGN_TOKEN_MAX_AGE_SECONDS:
            return False
        expected = hmac.new(
            settings.jwt_secret_key.encode("utf-8") + _SIGN_TOKEN_SALT,
            f"{pid_part}|{ts_part}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig_part)
    except Exception:  # noqa: BLE001 — token malformado: trata como inválido, nunca derruba o /sign
        return False


@router.get("/{proposal_id}/pdf")
async def gerar_pdf_proposta(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera o PDF do orçamento (download) a partir da proposta e seus itens.
    salvar=true: registra no Conecta PRO e devolve link público de download."""
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")

    from modules.crm.services.proposal_pdf import build_proposal_pdf

    # Assinaturas já coletadas (motor universal) → carimbo branded de autenticidade no PDF.
    _signatarios = None
    try:
        from modules.signatures.services.universal_signature_service import (
            UniversalSignatureService,
        )

        _st = await UniversalSignatureService(db).status(
            document_type="proposal", document_id=str(proposal_id)
        )
        _signatarios = _st.get("signatarios")
    except Exception:  # noqa: BLE001
        _signatarios = None

    try:
        pdf_bytes = build_proposal_pdf(proposal, _signatarios)
    except Exception as e:  # noqa: BLE001
        logger.exception("Erro ao gerar PDF da proposta %s", proposal_id)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {e}") from e

    # Camada de assinatura universal: proposta comercial → COMPANY + CUSTOMER.
    # Devolve o public_token do link do cliente. Idempotente e à prova de falha.
    public_token = None
    try:
        from modules.signatures.helpers import (
            document_hash_sha256,
            garantir_solicitacao_assinatura,
        )

        sig = await garantir_solicitacao_assinatura(
            db,
            document_type="proposal",
            document_id=proposal_id,
            title=f"Proposta {getattr(proposal, 'number', '')} - {getattr(proposal, 'client_name', '')}",
            document_hash=document_hash_sha256(pdf_bytes),
            customer_name=getattr(proposal, "client_name", None),
            customer_email=getattr(proposal, "client_email", None),
            customer_document=getattr(proposal, "client_document", None),
        )
        if sig:
            public_token = sig.get("public_token")
    except Exception as _sig_exc:  # noqa: BLE001
        logger.warning("Assinatura da proposta %s não criada: %s", proposal_id, _sig_exc)

    if salvar:
        from modules.crm.services.docs_registry import salvar_pdf

        result = await salvar_pdf(
            db,
            "proposta",
            f"Proposta {getattr(proposal, 'number', '')} - {getattr(proposal, 'client_name', '')}",
            pdf_bytes,
            ref_tipo="proposal",
            ref_id=proposal_id,
            teste=teste,
        )
        if isinstance(result, dict) and public_token:
            result["signature_public_token"] = public_token
        return result

    number = (getattr(proposal, "number", None) or proposal_id).replace("/", "-")
    filename = f"orcamento_{number}.pdf"
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    if public_token:
        headers["X-Signature-Public-Token"] = public_token
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )


# ============== Proposal Endpoints ==============


@router.post("", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_proposal(
    data: ProposalCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria uma nova proposta comercial.

    Requer autenticacao. Totais sao calculados automaticamente.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create(data, created_by_id=str(current_user.id))
    # Pipeline: toda proposta nasce com um deal ligado (estágio "Proposta").
    await sync_opportunity_for_proposal(db, proposal)
    await log_activity(
        db,
        "proposal_created",
        f"Proposta {proposal.number} criada",
        proposal_id=str(proposal.id),
        opportunity_id=getattr(proposal, "opportunity_id", None),
        user_id=str(current_user.id),
    )
    logger.info(f"Proposal criada por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.post(
    "/from-opportunity",
    response_model=ProposalDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_proposal_from_opportunity(
    data: ProposalCreateFromOpportunity,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria proposta a partir de uma opportunity.

    Dados do cliente sao copiados da opportunity.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create_from_opportunity(data, created_by_id=str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada ou inativa",
        )

    logger.info(f"Proposal criada de opportunity {data.opportunity_id} por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.get("", response_model=ProposalListResponse)
@router.get("/", response_model=ProposalListResponse, include_in_schema=False)
async def list_proposals(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    status_filter: ProposalStatus | None = Query(None, alias="status"),
    proposal_type: ProposalType | None = None,
    opportunity_id: str | None = None,
    is_expired: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    client_name: str | None = None,
    search: str | None = None,
) -> ProposalListResponse:
    """
    Lista propostas com filtros e paginacao.

    Suporta busca por numero, titulo, cliente.
    """
    repo = ProposalRepository(db)

    filters = ProposalFilter(
        status=status_filter,
        proposal_type=proposal_type,
        opportunity_id=opportunity_id,
        is_expired=is_expired,
        min_value=min_value,
        max_value=max_value,
        client_name=client_name,
        search=search,
    )

    proposals, total = await repo.list(filters=filters, page=page, page_size=page_size)

    total_pages = (total + page_size - 1) // page_size

    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in proposals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=ProposalStats)
async def get_proposal_stats(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    created_by_id: str | None = None,
) -> ProposalStats:
    """
    Obtem estatisticas de propostas.

    Inclui: taxa de aceitacao, valor medio, tempo de resposta.
    """
    repo = ProposalRepository(db)
    return await repo.get_stats(created_by_id=created_by_id)


# ============== Template Endpoints (antes de /{proposal_id} — evita captura de rota) ==============


@router.post(
    "/templates",
    response_model=ProposalTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: ProposalTemplateCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Cria template de proposta.
    """
    repo = ProposalRepository(db)
    template = await repo.create_template(data)
    logger.info(f"Template criado por {current_user.email}: {template.name}")
    return ProposalTemplateResponse.model_validate(template)


@router.get("/templates", response_model=list[ProposalTemplateResponse])
async def list_templates(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> list[ProposalTemplateResponse]:
    """
    Lista todos os templates ativos.
    """
    repo = ProposalRepository(db)
    templates = await repo.list_templates()
    return [ProposalTemplateResponse.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Obtem template por ID.
    """
    repo = ProposalRepository(db)
    template = await repo.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    return ProposalTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def update_template(
    template_id: str,
    data: ProposalTemplateUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Atualiza template.
    """
    repo = ProposalRepository(db)
    template = await repo.update_template(template_id, data)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    logger.info(f"Template atualizado por {current_user.email}: {template.name}")
    return ProposalTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove template (soft delete).
    """
    repo = ProposalRepository(db)
    deleted = await repo.delete_template(template_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    logger.info(f"Template deletado por {current_user.email}: {template_id}")


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Obtem uma proposta pelo ID com todos os itens.
    """
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    return ProposalDetailResponse.model_validate(proposal)


@router.put("/{proposal_id}", response_model=ProposalDetailResponse)
async def update_proposal(
    proposal_id: str,
    data: ProposalUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Atualiza uma proposta.

    Apenas propostas em rascunho ou revisao podem ser editadas.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update(proposal_id, data)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada ou nao pode ser editada",
        )

    logger.info(f"Proposal atualizada por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.post("/{proposal_id}/submit", response_model=ProposalResponse, status_code=201)
async def submit_proposal_for_approval(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Submete proposta para aprovacao.

    Muda status de DRAFT para PENDING_APPROVAL.
    """
    repo = ProposalRepository(db)
    proposal = await repo.submit_for_approval(proposal_id, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao esta em rascunho",
        )

    logger.info(f"Proposal submetida por {current_user.email}: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/approve", response_model=ProposalResponse, status_code=201)
async def process_proposal_approval(
    proposal_id: str,
    data: ProposalApprovalRequest,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Processa aprovacao/rejeicao de proposta.

    Acoes: approve, reject, request_changes.
    """
    repo = ProposalRepository(db)
    proposal = await repo.process_approval(proposal_id, data, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao esta pendente",
        )

    logger.info(f"Proposal {proposal.number} {data.action.value} por {current_user.email}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/send", response_model=ProposalResponse, status_code=201)
async def send_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Marca proposta como enviada ao cliente.

    Muda status para SENT e registra data de envio.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.SENT, user_id=str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    # Pipeline: proposta enviada -> deal avança para "Negociação".
    await sync_opportunity_for_proposal(db, proposal)
    # E-mail: envia a proposta ao cliente com link de assinatura + pixel de rastreio (best-effort).
    from modules.crm.services.proposal_delivery import send_proposal_email

    await send_proposal_email(proposal)
    logger.info(f"Proposal enviada por {current_user.email}: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/marcar-enviada", status_code=201)
async def marcar_proposta_enviada(
    proposal_id: str,
    current_user: CurrentActiveUser,
    data_envio: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Marca uma proposta como ENVIADA sem reenviar ao cliente (quando o envio foi feito por fora
    do ciclo — WhatsApp/e-mail manual). Entra no painel + acompanhamento do José Luís. NÃO dispara
    nada ao cliente."""
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta nao encontrada")
    # status -> sent, sent_at = data informada OU a já existente OU a data de criação (reflete o real).
    await db.execute(
        text("""
        UPDATE proposals SET status='sent',
               sent_at = COALESCE(CAST(:dt AS timestamptz), sent_at, created_at), updated_at=now()
        WHERE id=:id"""),
        {"dt": data_envio, "id": proposal_id},
    )
    await db.commit()
    sent = await repo.get_by_id(proposal_id)
    # pipeline + acompanhamento (entra no radar do José Luís)
    try:
        await sync_opportunity_for_proposal(db, sent)
    except Exception as e:  # noqa: BLE001
        logger.warning("marcar-enviada: sync opportunity falhou: %s", e)
    from modules.crm.services import orchestration as O
    from modules.crm.services.phone import canonical_br

    await O.upsert_negociacao(
        db,
        proposal_id=str(sent.id),
        deal_id=str(sent.opportunity_id) if getattr(sent, "opportunity_id", None) else None,
        phone_canonical=canonical_br(sent.client_phone),
        cliente_nome=sent.client_name,
        proposta_enviada_em=sent.sent_at,
        responsavel="jose_luis",
    )
    logger.info("Proposta %s marcada como enviada (sem reenvio) por %s", sent.number, current_user.email)
    return {
        "ok": True,
        "proposta": sent.number,
        "cliente": sent.client_name,
        "status": "sent",
        "enviada_em": str(sent.sent_at)[:10],
        "obs": "marcada como enviada sem reenviar ao cliente",
    }


@router.post("/{proposal_id}/send-whatsapp", status_code=201)
async def send_proposal_whatsapp(
    proposal_id: str,
    current_user: CurrentActiveUser,
    confirmar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Envia a proposta pelo WhatsApp do José Luís: PDF + link de assinatura, com rastreio em
    crm_followups. confirmar=false mostra o preview; confirmar=true envia de verdade."""
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta nao encontrada")

    from modules.crm.services import followups as F
    from modules.crm.services.phone import to_e164_br
    from modules.crm.services.proposal_delivery import sign_url

    e164 = to_e164_br(proposal.client_phone)
    cliente_id = None
    if not e164 and getattr(proposal, "client_document", None):
        tgt = await F.resolve_target(db, cliente=str(proposal.client_document))
        e164 = tgt.get("phone_e164")
        cliente_id = tgt.get("cliente_id")
    link = sign_url(str(proposal.id))
    nome = (proposal.client_name or "").split()[0] if proposal.client_name else "tudo bem"
    msg = (
        f"Olá, {nome}! 😊 Aqui é o José Luís, da Conecta Mais. "
        f"Segue a nossa proposta {proposal.number}. "
        f"Para visualizar e assinar online, é só acessar: {link}\n\n"
        f"Fico à disposição para qualquer dúvida. — José Luís · Conecta Mais"
    )

    if not confirmar:
        return {
            "preview": True,
            "proposta": proposal.number,
            "cliente": proposal.client_name,
            "telefone": e164,
            "link_assinatura": link,
            "mensagem": msg,
            "sem_telefone": not e164,
            "aviso": "Reenvie com confirmar=true para o José Luís enviar o PDF + link pelo WhatsApp.",
        }

    if not e164:
        raise HTTPException(422, "Cliente sem WhatsApp. Use cadastrar_whatsapp_cliente antes.")

    # Compliance: opt-out / horário comercial
    canon = F.canonical_br(e164)
    if await F.is_opted_out(db, canon):
        return {"enviada": False, "motivo": "opt_out", "detalhe": "Cliente pediu para não receber."}

    # PDF da proposta
    pdf_bytes = b""
    try:
        from modules.crm.services.proposal_pdf import build_proposal_pdf

        pdf_bytes = build_proposal_pdf(proposal)
    except Exception as e:  # noqa: BLE001 — sem PDF ainda manda o texto+link
        logger.error("send-whatsapp: falha ao gerar PDF da proposta %s: %s", proposal.number, e)

    from modules.integrations.connectors.whatsapp.service import whatsapp_service

    res = (
        await whatsapp_service.send_with_attachment(e164, msg, pdf_bytes, f"proposta_{proposal.number}.pdf")
        if pdf_bytes
        else await whatsapp_service.send_custom(e164, msg)
    )
    ok = res.get("status") == "sent"

    if ok:
        # marca proposta como enviada + move o deal (mesma semântica do envio por e-mail)
        sent = await repo.update_status(proposal_id, ProposalStatus.SENT, user_id=str(current_user.id))
        if sent:
            await sync_opportunity_for_proposal(db, sent)

    await F.register_followup(
        db,
        canal="whatsapp",
        mensagem=msg,
        status=("enviado" if ok else "erro"),
        phone_e164=e164,
        phone_canonical=canon,
        proposal_id=str(proposal.id),
        deal_id=str(proposal.opportunity_id) if getattr(proposal, "opportunity_id", None) else None,
        cliente_id=cliente_id,
        template="proposta_whatsapp",
        enviado_em=(F.now_manaus() if ok else None),
        conversation_id=res.get("conversation_id"),
        message_id=res.get("message_id"),
        criado_por=getattr(current_user, "email", None),
        detalhe=(None if ok else str(res.get("status") or res)[:300]),
    )

    if ok:
        await F.notify_jordan(
            f"📤 Proposta {proposal.number} enviada por WhatsApp para {proposal.client_name} ({e164})."
        )
    return {
        "enviada": ok,
        "proposta": proposal.number,
        "para": e164,
        "pdf_anexado": bool(res.get("attachment_sent")),
        "status_envio": res.get("status"),
        "link_assinatura": link,
    }


@router.post("/{proposal_id}/send-completo", status_code=201)
async def send_proposal_completo(
    proposal_id: str,
    current_user: CurrentActiveUser,
    confirmar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Envia a proposta por E-MAIL **e** por WhatsApp (José Luís), o WhatsApp citando o e-mail.
    Cria o estado da negociação, inscreve na cadência de follow-up e avisa o Jordan que vai acompanhar.
    confirmar=false = preview; confirmar=true = envia de verdade (e-mail + WhatsApp)."""
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta nao encontrada")

    from modules.crm.services import followups as F
    from modules.crm.services import orchestration as O
    from modules.crm.services.phone import to_e164_br
    from modules.crm.services.proposal_delivery import sign_url

    email = (proposal.client_email or "").strip() or None
    e164 = to_e164_br(proposal.client_phone)
    cliente_id = None
    if not e164 and getattr(proposal, "client_document", None):
        tgt = await F.resolve_target(db, cliente=str(proposal.client_document))
        e164 = tgt.get("phone_e164")
        cliente_id = tgt.get("cliente_id")
    link = sign_url(str(proposal.id))
    nome = (proposal.client_name or "").split()[0] if proposal.client_name else "tudo bem"
    canais = [c for c, ok in (("e-mail", bool(email)), ("WhatsApp", bool(e164))) if ok]
    msg = (
        f"Olá, {nome}! 😊 Aqui é o José Luís, da Conecta Mais. "
        f"Acabei de enviar a nossa proposta {proposal.number} "
        + (f"para o seu e-mail cadastrado ({email}). " if email else "")
        + f"Segue também por aqui o link pra visualizar e assinar online: {link}\n\n"
        f"Qualquer dúvida, estou à disposição. — José Luís · Conecta Mais"
    )

    if not confirmar:
        return {
            "preview": True,
            "proposta": proposal.number,
            "cliente": proposal.client_name,
            "email": email,
            "whatsapp": e164,
            "canais": canais,
            "mensagem_whatsapp": msg,
            "sem_canais": not canais,
            "aviso": "Reenvie com confirmar=true para enviar por e-mail + WhatsApp e iniciar o acompanhamento.",
        }

    if not canais:
        raise HTTPException(422, "Cliente sem e-mail e sem WhatsApp. Cadastre ao menos um canal.")

    resultado: dict = {"proposta": proposal.number, "cliente": proposal.client_name}

    # marca a proposta como enviada + move o deal (uma vez)
    sent = await repo.update_status(proposal_id, ProposalStatus.SENT, user_id=str(current_user.id))
    if sent:
        await sync_opportunity_for_proposal(db, sent)

    # E-MAIL
    if email:
        try:
            from modules.crm.services.proposal_delivery import send_proposal_email

            resultado["email_enviado"] = await send_proposal_email(sent or proposal)
        except Exception as e:  # noqa: BLE001
            logger.error("send-completo e-mail falhou: %s", e)
            resultado["email_enviado"] = False

    # WHATSAPP (PDF + link, citando o e-mail)
    wa_ok = False
    if e164:
        canon = F.canonical_br(e164)
        if await F.is_opted_out(db, canon):
            resultado["whatsapp_enviado"] = False
            resultado["whatsapp_motivo"] = "opt_out"
        else:
            pdf_bytes = b""
            try:
                from modules.crm.services.proposal_pdf import build_proposal_pdf

                pdf_bytes = build_proposal_pdf(sent or proposal)
            except Exception as e:  # noqa: BLE001
                logger.error("send-completo PDF falhou: %s", e)
            from modules.integrations.connectors.whatsapp.service import whatsapp_service

            res = (
                await whatsapp_service.send_with_attachment(e164, msg, pdf_bytes, f"proposta_{proposal.number}.pdf")
                if pdf_bytes
                else await whatsapp_service.send_custom(e164, msg)
            )
            wa_ok = res.get("status") == "sent"
            resultado["whatsapp_enviado"] = wa_ok
            await F.register_followup(
                db,
                canal="whatsapp",
                mensagem=msg,
                status=("enviado" if wa_ok else "erro"),
                phone_e164=e164,
                phone_canonical=canon,
                proposal_id=str(proposal.id),
                deal_id=str(proposal.opportunity_id) if getattr(proposal, "opportunity_id", None) else None,
                cliente_id=cliente_id,
                template="proposta_completa",
                enviado_em=(F.now_manaus() if wa_ok else None),
                conversation_id=res.get("conversation_id"),
                message_id=res.get("message_id"),
                criado_por=getattr(current_user, "email", None),
            )

    # estado da negociação (José Luís passa a acompanhar)
    await O.upsert_negociacao(
        db,
        proposal_id=str(proposal.id),
        deal_id=str(proposal.opportunity_id) if getattr(proposal, "opportunity_id", None) else None,
        cliente_id=cliente_id,
        phone_canonical=(F.canonical_br(e164) if e164 else None),
        cliente_nome=proposal.client_name,
        proposta_enviada_em=F.now_manaus(),
        responsavel="jose_luis",
    )

    # avisa o Jordan que assumiu o acompanhamento
    await O.notify_owner(
        f"📤 Proposta *{proposal.number}* enviada para *{proposal.client_name}* "
        f"({' + '.join(canais)}).\nVou acompanhar o follow-up (D+2/D+5/D+10) e te aviso quando "
        f"ele responder. Se quiser assumir, é só falar."
    )

    resultado["link_assinatura"] = link
    resultado["canais"] = canais
    return resultado


async def _try_generate_commission(db: AsyncSession, proposal, created_by_id: str | None) -> None:
    """
    Gera comissão automaticamente quando uma proposta é aceita.

    Defensivo por design: qualquer falha (sem regra, sem vendedor, sem valor)
    apenas registra warning e NUNCA quebra o fluxo de aceite da proposta.
    """
    try:
        from modules.crm.repositories.commission_repository import CommissionRepository
        from modules.crm.schemas.commission import CommissionCreate

        seller_id = getattr(proposal, "created_by_id", None) or created_by_id
        sale_value = float(getattr(proposal, "total", 0) or 0)
        if not seller_id or sale_value <= 0:
            logger.info(
                f"Comissão não gerada p/ proposta {proposal.number}: "
                f"sem vendedor ou valor (seller={seller_id}, total={sale_value})"
            )
            return

        crepo = CommissionRepository(db)
        rules = await crepo.get_valid_rules(seller_id=str(seller_id))
        if not rules:
            logger.info(
                f"Comissão não gerada p/ proposta {proposal.number}: nenhuma regra de comissão válida cadastrada"
            )
            return

        rule = crepo.service.find_applicable_rule(rules, sale_value) if getattr(crepo, "service", None) else rules[0]
        commission = await crepo.create(
            CommissionCreate(
                seller_id=str(seller_id),
                proposal_id=str(proposal.id),
                sale_value=sale_value,
                rule_id=str(rule.id) if rule else None,
                description=f"Comissão auto — proposta {proposal.number}",
            ),
            created_by_id=created_by_id,
        )
        logger.info(f"Comissão gerada automaticamente: {commission.reference_number} (proposta {proposal.number})")
    except Exception as exc:  # noqa: BLE001 — comissão nunca pode quebrar o aceite
        logger.warning(f"Falha ao gerar comissão p/ proposta {getattr(proposal, 'number', '?')}: {exc}")


@router.post("/{proposal_id}/accept", response_model=ProposalResponse, status_code=201)
async def accept_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Marca proposta como aceita pelo cliente e gera comissão automaticamente
    (se houver vendedor, valor e regra de comissão válida).
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.ACCEPTED)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    await _try_generate_commission(db, proposal, str(current_user.id))
    # Pipeline: proposta aceita -> deal "Ganho" (closed_won) + contrato automático (DRAFT).
    await sync_opportunity_for_proposal(db, proposal)
    await ensure_contract_for_proposal(db, proposal)
    await log_activity(
        db,
        "proposal_accepted",
        f"Proposta {proposal.number} ACEITA pelo cliente",
        proposal_id=str(proposal.id),
        opportunity_id=getattr(proposal, "opportunity_id", None),
        user_id=str(current_user.id),
    )

    logger.info(f"Proposal aceita: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse, status_code=201)
async def reject_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,
) -> ProposalResponse:
    """
    Marca proposta como rejeitada pelo cliente.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.REJECTED, notes=reason)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    # Pipeline: proposta rejeitada -> deal "Perdido" (closed_lost).
    await sync_opportunity_for_proposal(db, proposal)
    logger.info(f"Proposal rejeitada: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/new-version", response_model=ProposalDetailResponse, status_code=201)
async def create_new_version(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria nova versao da proposta.

    Mantém mesmo numero, incrementa versao.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create_new_version(proposal_id, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Nova versao criada por {current_user.email}: {proposal.number} v{proposal.version}")
    return ProposalDetailResponse.model_validate(proposal)


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma proposta (soft delete).
    """
    repo = ProposalRepository(db)
    deleted = await repo.delete(proposal_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Proposal deletada por {current_user.email}: {proposal_id}")


# ============== Item Endpoints ==============


@router.put("/{proposal_id}/items", response_model=ProposalDetailResponse)
async def replace_proposal_items(
    proposal_id: str,
    items: list[ProposalItemCreate],
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Substitui TODOS os itens da proposta de uma vez (a tela manda a lista completa).
    Recalcula o total e sincroniza o valor do deal no pipeline.
    """
    repo = ProposalRepository(db)
    proposal = await repo.replace_items(proposal_id, items)
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou ja fechada (nao editavel)",
        )
    await sync_opportunity_for_proposal(db, proposal)
    logger.info(f"Itens da proposta {proposal_id} substituidos por {current_user.email}")
    return ProposalDetailResponse.model_validate(proposal)


@router.post("/{proposal_id}/items", response_model=ProposalItemResponse, status_code=201)
async def add_proposal_item(
    proposal_id: str,
    data: ProposalItemCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalItemResponse:
    """
    Adiciona item a proposta.
    """
    repo = ProposalRepository(db)
    item = await repo.add_item(proposal_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao pode ser editada",
        )

    logger.info(f"Item adicionado a proposta {proposal_id} por {current_user.email}")
    return ProposalItemResponse.model_validate(item)


@router.delete(
    "/{proposal_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_proposal_item(
    proposal_id: str,
    item_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove item da proposta.
    """
    repo = ProposalRepository(db)
    removed = await repo.remove_item(proposal_id, item_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou proposta nao encontrados",
        )

    logger.info(f"Item {item_id} removido de proposta {proposal_id}")


# ============================================================================
# ENDPOINTS PÚBLICOS (sem auth) — rastreio de e-mail + assinatura interna
# ============================================================================


@router.get("/{proposal_id}/track.gif")
async def track_proposal_open(proposal_id: str, db: AsyncSession = Depends(get_db)):
    """Pixel de rastreio: marca a proposta como visualizada quando o cliente abre o e-mail. PÚBLICO."""
    from modules.crm.services.proposal_delivery import PIXEL_GIF, mark_proposal_viewed

    await mark_proposal_viewed(db, proposal_id)
    return Response(
        content=PIXEL_GIF, media_type="image/gif", headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )


@router.get("/{proposal_id}/public")
async def get_proposal_public(proposal_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Dados da proposta para a página pública de assinatura. PÚBLICO (sem auth).
    Rate-limited por IP e por proposta (30/h) — leitura repetida de tela normal, mas fecha scraping."""
    ip = _client_ip(request)
    if not await _rate_limit_ok(f"rl:proposal_public:ip:{ip}", 30, 3600) or not await _rate_limit_ok(
        f"rl:proposal_public:pid:{proposal_id}", 30, 3600
    ):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")
    row = (
        await db.execute(
            text("""
        SELECT id, number, title, client_name, client_document, total, status,
               signature_status, signed_at, payment_terms, notes
        FROM proposals WHERE id = :id AND is_active = true
        """),
            {"id": proposal_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    items = (
        await db.execute(
            text(
                "SELECT name, description, quantity, unit, unit_price, total FROM proposal_items WHERE proposal_id=:id ORDER BY sort_order"
            ),
            {"id": proposal_id},
        )
    ).fetchall()
    return {
        "id": str(row[0]),
        "number": row[1],
        "title": row[2],
        "client_name": row[3],
        "client_document": row[4],
        "total": float(row[5] or 0),
        "status": row[6],
        "signature_status": row[7],
        "signed_at": row[8].isoformat() if row[8] else None,
        "payment_terms": row[9],
        "notes": row[10],
        "items": [
            {
                "name": i[0],
                "description": i[1],
                "quantity": float(i[2] or 0),
                "unit": i[3],
                "unit_price": float(i[4] or 0),
                "total": float(i[5] or 0),
            }
            for i in items
        ],
    }


class SignRequest(BaseModel):
    signer_name: str
    signer_cpf: str | None = None
    token: str | None = None  # alternativa ao query param ?t= (aceita nos dois lugares)


@router.post("/{proposal_id}/sign")
async def sign_proposal_public(
    proposal_id: str,
    data: SignRequest,
    request: Request,
    t: str | None = Query(default=None, description="Token assinado do link (ausente = link legado)"),
    db: AsyncSession = Depends(get_db),
):
    """Assinatura INTERNA pelo cliente (PÚBLICO). Registra a assinatura, aceita a proposta e dispara
    o fluxo de Ganho (deal -> contrato -> cliente automático).

    Rate-limited (5/h por IP e por proposta — checado ANTES de buscar a proposta, então também
    fecha enumeração de UUID contra ids inexistentes). Token (?t= ou body.token):
    presente+válido=ok; presente+inválido/expirado=403; AUSENTE=permitido (link legado enviado
    antes do endurecimento) mas fica registrado em audit — transição não-quebra, task 5.4c-2."""
    ip = _client_ip(request)
    if not await _rate_limit_ok(f"rl:proposal_sign:ip:{ip}", 5, 3600) or not await _rate_limit_ok(
        f"rl:proposal_sign:pid:{proposal_id}", 5, 3600
    ):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente mais tarde.")

    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)
    if not proposal or not getattr(proposal, "is_active", True):
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    if (getattr(proposal, "status", "") or "") == "accepted":
        return {"ok": True, "already_signed": True, "number": proposal.number}

    from modules.crm.services.proposal_delivery import register_signature

    ua = request.headers.get("user-agent")

    token = t or data.token
    if token:
        if not _verify_sign_token(proposal_id, token):
            logger.warning(f"sign_proposal_public: token INVÁLIDO/expirado proposta={proposal_id} ip={ip}")
            raise HTTPException(
                status_code=403, detail="Link de assinatura inválido ou expirado. Peça um novo link."
            )
        token_status = "valido"
    else:
        token_status = "ausente_legado"
        logger.warning(
            f"sign_proposal_public: assinatura SEM TOKEN (link legado, permitido em transição) "
            f"proposta={proposal_id} ip={ip}"
        )

    sig = await register_signature(db, proposal, data.signer_name.strip(), data.signer_cpf, ip, ua)
    if not sig:
        raise HTTPException(status_code=500, detail="Falha ao registrar a assinatura")

    # Fluxo de Ganho: deal -> Ganho, contrato (com cliente automático).
    await db.refresh(proposal)
    await sync_opportunity_for_proposal(db, proposal)
    await ensure_contract_for_proposal(db, proposal)
    await log_activity(
        db,
        "proposal_signed",
        f"Proposta {proposal.number} ASSINADA por {data.signer_name}",
        proposal_id=str(proposal.id),
        opportunity_id=getattr(proposal, "opportunity_id", None),
    )
    if token_status == "ausente_legado":
        # Audit best-effort (log_activity nunca derruba o /sign): rastreia quem assinou sem token
        # p/ o Jordan decidir se quer investigar (não é bloqueio — só o registro pedido na task).
        await log_activity(
            db,
            "proposal_signed_no_token",
            f"Assinatura de {proposal.number} SEM TOKEN (link legado) — ip={ip}",
            proposal_id=str(proposal.id),
        )
    # 🎉 fecha o ciclo: avisa o Jordan na hora que o negócio entrou (best-effort, nunca derruba o /sign).
    try:
        from modules.crm.services import orchestration as _O  # noqa: PLC0415

        await _O.notify_owner(
            f"🎉🎉 *PROPOSTA ASSINADA!* — {getattr(proposal, 'client_name', '') or data.signer_name}\n"
            f"Proposta {proposal.number} foi assinada por {data.signer_name} agora.\n"
            f"✅ Deal em GANHO, contrato e cliente já criados automaticamente. Parabéns! 🚀"
        )
    except Exception as _e:  # noqa: BLE001
        logger.error("notify_owner pós-assinatura falhou (ignorada): %s", _e)
    return {"ok": True, "signed": True, "hash": sig, "number": proposal.number}
