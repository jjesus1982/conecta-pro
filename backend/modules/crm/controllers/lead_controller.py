"""
Controller (endpoints) para Lead.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.lead import LeadStatus
from modules.crm.repositories.lead_repository import LeadRepository
from modules.crm.schemas.lead import (
    LeadCreate,
    LeadFilter,
    LeadListResponse,
    LeadResponse,
    LeadStatusUpdate,
    LeadUpdate,
)
from modules.crm.services.pipeline_sync import ensure_opportunity_for_lead
from modules.crm.services.timeline import log_activity


def _serializar(modelo, registros, *, rotulo):
    """Um lead fora do contrato não pode derrubar a listagem inteira — ver `listagem_tolerante`."""
    from modules.crm.services.listagem_tolerante import serializar_lista

    itens, _ = serializar_lista(modelo, registros, rotulo=rotulo)
    return itens


router = APIRouter(prefix="/leads", tags=["CRM - Leads"])


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_lead(
    data: LeadCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> LeadResponse:
    """
    Cria um novo lead.

    Requer autenticação. O score é calculado automaticamente.
    """
    repo = LeadRepository(db)

    # Verificar se email já existe (apenas quando informado — leads de WhatsApp não têm email)
    if data.email:
        existing = await repo.get_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um lead com este email",
            )

    # Duplicado por TELEFONE (mesmo telefone = mesmo lead). Aqui o guard é 400, e não
    # reaproveitamento silencioso como no rd_action_lead: este endpoint devolve
    # LeadResponse, então reaproveitar faria quem pediu para criar "João" receber de
    # volta "Maria" com 201 Created. Avisar de quem é o telefone é mais útil.
    duplicado = await repo.find_duplicate(phone=data.phone)
    if duplicado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Já existe um lead com este telefone: {duplicado.name}",
        )

    lead = await repo.create(data)
    await log_activity(db, "lead_created", "Lead criado", lead_id=str(lead.id), user_id=str(current_user.id))
    logger.info(f"Lead criado por {current_user.email}: {lead.id}")

    # Growth: dispara workflows do evento lead_created + recalcula scoring configurável.
    # SESSÃO ISOLADA (async_session_factory): nunca toca a sessão/objeto do request -> sem MissingGreenlet
    # no LeadResponse.model_validate(lead). Best-effort.
    try:
        from sqlalchemy import text as _text

        from core.database import async_session_factory
        from modules.crm.services import growth_services as _G  # noqa: N812

        _lid = str(lead.id)
        async with async_session_factory() as _s:
            _ld = (await _s.execute(_text("SELECT * FROM leads WHERE id=:id"), {"id": _lid})).mappings().first()
            await _G.run_workflows_for_event(_s, "lead_created", dict(_ld) if _ld else {"id": _lid}, "lead")
            await _G.recompute_lead_score(_s, _lid)
    except Exception as _exc:  # noqa: BLE001
        logger.debug(f"growth hook lead_created ignorado: {_exc}")

    return LeadResponse.model_validate(lead)


@router.get("", response_model=LeadListResponse)
@router.get("/", response_model=LeadListResponse, include_in_schema=False)
async def list_leads(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    status_filter: LeadStatus | None = Query(None, alias="status"),
    source: str | None = None,  # str p/ alcançar origens fora do enum (ver LeadFilter)
    assigned_to_id: str | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    max_score: int | None = Query(None, ge=0, le=100),
    is_hot: bool | None = None,
    company: str | None = None,
    search: str | None = None,
    #: Apelido PT de `search` (30/09/2026). Sem ele a rota ACEITAVA `busca` e a IGNORAVA:
    #: FastAPI descarta query param desconhecido em silêncio, então `?busca=Toscana`
    #: devolvia a base inteira com HTTP 200. Resposta errada é pior que erro.
    busca: str | None = None,
    incluir_fixtures: bool = Query(False, description="Traz de volta os registros de TESTE, que ficam fora por padrão"),
) -> LeadListResponse:
    """
    Lista leads com filtros e paginação.

    Suporta busca por nome, email ou empresa.

    Registro de TESTE fica FORA por padrão desde 30/09/2026 (BUG-07). Nada foi apagado —
    `incluir_fixtures=true` traz de volta.
    """
    from modules.crm.services import fixtures as _fx  # noqa: PLC0415

    await _fx.garantir_colunas(db)
    repo = LeadRepository(db)

    filters = LeadFilter(
        incluir_fixtures=incluir_fixtures,
        status=status_filter,
        source=source,
        assigned_to_id=assigned_to_id,
        min_score=min_score,
        max_score=max_score,
        is_hot=is_hot,
        company=company,
        search=(search or busca),
    )

    leads, total = await repo.list(filters=filters, page=page, page_size=page_size)

    total_pages = (total + page_size - 1) // page_size

    return LeadListResponse(
        items=_serializar(LeadResponse, leads, rotulo="lead"),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    data: LeadUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> LeadResponse:
    """
    Atualiza um lead.

    Apenas campos fornecidos são atualizados.
    O score é recalculado se necessário.
    """
    repo = LeadRepository(db)
    lead = await repo.update(lead_id, data)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead não encontrado",
        )

    # Pipeline: se a edição qualificou o lead, garante o deal no Kanban.
    await ensure_opportunity_for_lead(db, lead)
    logger.info(f"Lead atualizado por {current_user.email}: {lead.id}")
    return LeadResponse.model_validate(lead)


@router.patch("/{lead_id}/status", response_model=LeadResponse)
async def update_lead_status(
    lead_id: str,
    data: LeadStatusUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> LeadResponse:
    """
    Atualiza o status de um lead.

    Registra a mudança nas notas e recalcula o score.
    """
    repo = LeadRepository(db)
    lead = await repo.update_status(lead_id, data.status, data.notes)

    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead não encontrado",
        )

    logger.info(f"Lead {lead.id} status alterado para {data.status.value} por {current_user.email}")

    # Pipeline: lead qualificado (qualified/proposal/negotiation/won) vira deal no Kanban.
    await ensure_opportunity_for_lead(db, lead)
    await log_activity(
        db, "lead_status", f"Status do lead → {data.status.value}", lead_id=str(lead.id), user_id=str(current_user.id)
    )

    if data.status == LeadStatus.WON:
        import asyncio

        from modules.crm.publishers import publish_lead_convertido

        asyncio.create_task(
            publish_lead_convertido(
                lead_id=str(lead.id),
                nome=getattr(lead, "name", "") or getattr(lead, "nome", ""),
                empresa=getattr(lead, "company", "") or getattr(lead, "empresa", ""),
                score=getattr(lead, "score", None),
                cliente_id=str(getattr(lead, "client_id", "") or ""),
            )
        )

    return LeadResponse.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um lead (soft delete).
    """
    repo = LeadRepository(db)
    deleted = await repo.delete(lead_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead não encontrado",
        )

    logger.info(f"Lead deletado por {current_user.email}: {lead_id}")
