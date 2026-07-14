"""
Controller de Rondas de Inspecao - Endpoints FastAPI.

Author: Conecta PRO Team
Date: 2026-01-23
"""

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, get_current_active_user
from core.database import get_db
from modules.operacional.publishers import publish_ronda_concluida

from ..schemas import (
    ApplyDisciplinaryRequest,
    CheckpointCreate,
    CheckpointResponse,
    CheckpointUpdate,
    CompleteRoundRequest,
    InspectionDashboardStats,
    InspectionRoundCreate,
    InspectionRoundFilter,
    InspectionRoundListResponse,
    InspectionRoundResponse,
    InspectionRoundSummary,
    InspectionRoundUpdate,
    RegisterOccurrenceRequest,
    StartRoundRequest,
)
from ..services import (
    InspectionRoundNotFoundError,
    InspectionRoundService,
    InspectionRoundValidationError,
)

logger = logging.getLogger(__name__)

_TZ_MANAUS_RESUMO = ZoneInfo("America/Manaus")

router = APIRouter(dependencies=[Depends(get_current_active_user)])


def get_inspection_service(db: AsyncSession = Depends(get_db)) -> InspectionRoundService:
    """Dependency para obter InspectionRoundService."""
    return InspectionRoundService(db)


# =============================================================================
# CRUD ENDPOINTS
# =============================================================================


@router.post(
    "/",
    response_model=InspectionRoundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar ronda de inspecao",
    description="Cria uma nova ronda de inspecao.",
)
async def create_round(
    data: InspectionRoundCreate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Cria uma nova ronda."""
    try:
        inspection_round = await service.create(data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao criar ronda: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar ronda",
        )


@router.get(
    "/",
    response_model=InspectionRoundListResponse,
    summary="Listar rondas",
    description="Lista rondas com filtros e paginacao.",
)
async def list_rounds(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(10, ge=1, le=100, description="Itens por página"),
    skip: int = Query(0, ge=0, description="Registros a pular"),
    limit: int = Query(100, ge=1, le=500, description="Limite de registros"),
    inspector_id: UUID | None = Query(None, description="Filtrar por inspetor"),
    inspector_role: str | None = Query(None, description="Filtrar por cargo"),
    status_filter: str | None = Query(None, alias="status", description="Filtrar por status"),
    start_date: datetime | None = Query(None, description="Data inicial"),
    end_date: datetime | None = Query(None, description="Data final"),
    has_occurrences: bool | None = Query(None, description="Com ocorrencias"),
    has_disciplinary_actions: bool | None = Query(None, description="Com medidas disciplinares"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundListResponse:
    """Lista rondas com filtros."""
    filters = InspectionRoundFilter(
        inspector_id=inspector_id,
        inspector_role=inspector_role,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        has_occurrences=has_occurrences,
        has_disciplinary_actions=has_disciplinary_actions,
    )

    # Calcular skip a partir de page/page_size se fornecidos
    actual_skip = (page - 1) * page_size if page > 0 else skip
    actual_limit = page_size if page_size > 0 else limit

    tenant_str = str(tenant_id) if tenant_id else None
    rounds, total = await service.list(tenant_str, actual_skip, actual_limit, filters)

    total_pages = (total + actual_limit - 1) // actual_limit if actual_limit > 0 else 0

    return InspectionRoundListResponse(
        items=[InspectionRoundSummary.model_validate(r) for r in rounds],
        total=total,
        page=page,
        page_size=actual_limit,
        pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=InspectionDashboardStats,
    summary="Estatísticas de rondas",
    description="Retorna estatísticas de rondas de inspeção.",
)
async def get_stats(
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionDashboardStats:
    """Retorna estatísticas de rondas."""
    tenant_str = str(tenant_id) if tenant_id else None
    return await service.get_dashboard_stats(tenant_str)


@router.get(
    "/dashboard",
    response_model=InspectionDashboardStats,
    summary="Dashboard de rondas",
    description="Retorna estatisticas do dashboard de rondas.",
)
async def get_dashboard(
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    _start_date: datetime | None = Query(None, description="Data inicial"),
    _end_date: datetime | None = Query(None, description="Data final"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionDashboardStats:
    """Retorna estatisticas do dashboard."""
    tenant_str = str(tenant_id) if tenant_id else None
    return await service.get_dashboard_stats(tenant_str)


@router.get(
    "/minhas-rondas",
    response_model=list[InspectionRoundSummary],
    summary="Minhas rondas",
    description="Lista rondas do inspetor logado.",
)
async def get_my_rounds(
    current_user: CurrentActiveUser,
    inspector_id: UUID = Query(..., description="ID do inspetor"),
    tenant_id: UUID = Query(..., description="ID do tenant"),
    limit: int = Query(50, ge=1, le=200),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> list[InspectionRoundSummary]:
    """Lista rondas do inspetor."""
    rounds = await service.get_rounds_by_inspector(str(inspector_id), str(tenant_id), limit)
    return [InspectionRoundSummary.model_validate(r) for r in rounds]


@router.get(
    "/gestao/resumo-inspetores",
    summary="Resumo de atividade por inspetor",
    description="Prestação de contas da gestão de campo: rondas, condomínios visitados, fotos e dias SEM registro por inspetor (janela em dias).",
)
async def resumo_inspetores(
    current_user: CurrentActiveUser,
    dias: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O silêncio também é sinal: dias sem NENHUM registro aparecem por inspetor."""
    rows = (
        await db.execute(
            text(
                """
                SELECT r.inspector_id::text, max(r.inspector_name) AS nome,
                       max(r.inspector_role) AS papel,
                       count(DISTINCT r.id) AS rondas,
                       count(DISTINCT r.id) FILTER (WHERE r.status='concluida') AS concluidas,
                       count(DISTINCT r.id) FILTER (WHERE r.status='agendada') AS agendadas_pendentes,
                       count(DISTINCT r.id) FILTER (WHERE r.status='cancelada') AS canceladas,
                       avg(r.duration_minutes) FILTER (WHERE r.duration_minutes > 0) AS duracao_media_min,
                       count(c.id) AS checkpoints,
                       count(DISTINCT c.post_id) AS condominios_distintos,
                       COALESCE(sum(jsonb_array_length(COALESCE(c.photos,'[]'::jsonb))),0) AS fotos,
                       count(DISTINCT (c.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date) AS dias_com_registro,
                       min(c.created_at) AS primeira_atividade,
                       max(c.created_at) AS ultima_atividade,
                       count(c.id) FILTER (WHERE c.checkpoint_type='checkin_condominio') AS checkins,
                       count(c.id) FILTER (WHERE c.checkpoint_type='reuniao') AS reunioes
                FROM inspection_rounds r
                LEFT JOIN inspection_checkpoints c ON c.inspection_round_id = r.id
                WHERE r.is_active AND r.created_at >= now() - make_interval(days => :dias)
                GROUP BY r.inspector_id
                ORDER BY 2
                """
            ),
            {"dias": dias},
        )
    ).all()
    condominios = {
        r[0]: [x[0] for x in (
            await db.execute(
                text(
                    """SELECT DISTINCT c.post_name FROM inspection_checkpoints c
                       JOIN inspection_rounds r2 ON r2.id=c.inspection_round_id
                       WHERE r2.inspector_id=CAST(:i AS uuid) AND r2.is_active
                         AND r2.created_at >= now() - make_interval(days => :dias)
                         AND c.post_name IS NOT NULL"""
                ),
                {"i": r[0], "dias": dias},
            )
        ).all()]
        for r in rows
    }
    return {
        "janela_dias": dias,
        "gerado_em": datetime.now(_TZ_MANAUS_RESUMO).replace(tzinfo=None).isoformat(timespec="seconds"),
        "inspetores": [
            {
                "inspector_id": r[0], "nome": r[1], "papel": r[2],
                "rondas": int(r[3]), "concluidas": int(r[4]),
                "agendadas_pendentes": int(r[5]), "canceladas": int(r[6]),
                "cumprimento_pct": round(100 * int(r[4]) / int(r[3]), 1) if int(r[3]) else None,
                "duracao_media_min": round(float(r[7]), 1) if r[7] is not None else None,
                "checkpoints": int(r[8]), "condominios_distintos": int(r[9]),
                "condominios": condominios.get(r[0], []),
                "fotos": int(r[10]),
                "dias_com_registro": int(r[11]),
                "dias_sem_registro": max(0, dias - int(r[11])),
                "primeira_atividade": str(r[12]) if r[12] else None,
                "ultima_atividade": str(r[13]) if r[13] else None,
                "checkins_condominio": int(r[14]), "reunioes": int(r[15]),
            }
            for r in rows
        ],
        "aviso": "Sem registro aqui = sem visita registrada no sistema. Combine a política: visita só conta se registrada.",
    }


@router.get(
    "/{round_id}",
    response_model=InspectionRoundResponse,
    summary="Buscar ronda",
    description="Busca uma ronda por ID.",
)
async def get_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Busca ronda por ID."""
    try:
        inspection_round = await service.get_by_id(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch(
    "/{round_id}",
    response_model=InspectionRoundResponse,
    summary="Atualizar ronda",
    description="Atualiza uma ronda existente.",
)
async def update_round(
    round_id: UUID,
    data: InspectionRoundUpdate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Atualiza uma ronda."""
    try:
        inspection_round = await service.update(str(round_id), data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{round_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover ronda",
    description="Remove uma ronda (soft delete).",
)
async def delete_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
):
    """Remove uma ronda."""
    try:
        await service.delete(str(round_id))
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# WORKFLOW ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/iniciar",
    response_model=InspectionRoundResponse,
    summary="Iniciar ronda",
    description="Inicia uma ronda agendada.",
    status_code=201,
)
async def start_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    data: StartRoundRequest | None = None,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Inicia uma ronda."""
    try:
        inspection_round = await service.start_round(str(round_id), data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/pausar",
    response_model=InspectionRoundResponse,
    summary="Pausar ronda",
    description="Pausa uma ronda em andamento.",
    status_code=201,
)
async def pause_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Pausa uma ronda."""
    try:
        inspection_round = await service.pause_round(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/retomar",
    response_model=InspectionRoundResponse,
    summary="Retomar ronda",
    description="Retoma uma ronda pausada.",
    status_code=201,
)
async def resume_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Retoma uma ronda pausada."""
    try:
        inspection_round = await service.resume_round(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/concluir",
    response_model=InspectionRoundResponse,
    summary="Concluir ronda",
    description="Conclui uma ronda em andamento.",
    status_code=201,
)
async def complete_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    data: CompleteRoundRequest | None = None,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Conclui uma ronda."""
    try:
        inspection_round = await service.complete_round(str(round_id), data)
        asyncio.create_task(
            publish_ronda_concluida(
                ronda_id=str(round_id),
                inspector_id=str(getattr(inspection_round, "inspector_id", "") or getattr(current_user, "id", "")),
                cliente_id=str(getattr(inspection_round, "tenant_id", "") or ""),
                total_checkpoints=len(getattr(inspection_round, "checkpoints", []) or []),
                tem_ocorrencias=bool(getattr(inspection_round, "has_occurrences", False)),
                data=datetime.utcnow().isoformat(),
            )
        )
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/cancelar",
    response_model=InspectionRoundResponse,
    summary="Cancelar ronda",
    description="Cancela uma ronda.",
    status_code=201,
)
async def cancel_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    reason: str | None = Query(None, description="Motivo do cancelamento"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Cancela uma ronda."""
    try:
        inspection_round = await service.cancel_round(str(round_id), reason)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# CHECKPOINT ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/checkpoints",
    response_model=CheckpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar checkpoint",
    description="Cria um checkpoint durante a ronda.",
)
async def create_checkpoint(
    round_id: UUID,
    data: CheckpointCreate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> CheckpointResponse:
    """Cria um checkpoint."""
    try:
        checkpoint = await service.create_checkpoint(str(round_id), data)
        return CheckpointResponse.model_validate(checkpoint)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{round_id}/checkpoints",
    response_model=list[CheckpointResponse],
    summary="Listar checkpoints",
    description="Lista checkpoints de uma ronda.",
)
async def get_checkpoints(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> list[CheckpointResponse]:
    """Lista checkpoints de uma ronda."""
    try:
        checkpoints = await service.get_checkpoints(str(round_id))
        return [CheckpointResponse.model_validate(c) for c in checkpoints]
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch(
    "/{round_id}/checkpoints/{checkpoint_id}",
    response_model=CheckpointResponse,
    summary="Atualizar checkpoint",
    description="Atualiza um checkpoint.",
)
async def update_checkpoint(
    _round_id: UUID,
    checkpoint_id: UUID,
    data: CheckpointUpdate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> CheckpointResponse:
    """Atualiza um checkpoint."""
    try:
        checkpoint = service.update_checkpoint(str(checkpoint_id), data)
        return CheckpointResponse.model_validate(checkpoint)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# OCORRENCIA E MEDIDA DISCIPLINAR ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/registrar-ocorrencia",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar ocorrencia",
    description="Registra uma ocorrencia durante a ronda.",
)
async def register_occurrence(
    round_id: UUID,
    data: RegisterOccurrenceRequest,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> dict:
    """Registra uma ocorrencia durante a ronda."""
    try:
        checkpoint, occurrence_info = service.register_occurrence(str(round_id), data)
        return {
            "checkpoint": CheckpointResponse.model_validate(checkpoint),
            "occurrence": occurrence_info,
            "message": f"Ocorrencia {occurrence_info['occurrence_code']} registrada com sucesso",
        }
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao registrar ocorrencia: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao registrar ocorrencia",
        )


@router.post(
    "/{round_id}/aplicar-medida-disciplinar",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Aplicar medida disciplinar",
    description="Aplica medida disciplinar durante a ronda.",
)
async def apply_disciplinary_action(
    round_id: UUID,
    data: ApplyDisciplinaryRequest,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> dict:
    """Aplica medida disciplinar durante a ronda."""
    try:
        checkpoint, action_info = service.apply_disciplinary_action(str(round_id), data)
        return {
            "checkpoint": CheckpointResponse.model_validate(checkpoint),
            "disciplinary_action": action_info,
            "message": (f"Medida disciplinar {action_info['disciplinary_action_code']} aplicada com sucesso"),
        }
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao aplicar medida disciplinar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao aplicar medida disciplinar",
        )


# =============================================================================
# FOTOS DE CHECKPOINT — evidências REAIS no sistema (nada em grupo de WhatsApp)
# =============================================================================

FOTOS_DIR = Path("/app/uploads/rondas")
_MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_FOTO_BYTES = 10 * 1024 * 1024  # 10 MB
_TZ_MANAUS = ZoneInfo("America/Manaus")


async def _checkpoint_da_ronda(db: AsyncSession, round_id: UUID, checkpoint_id: UUID):
    row = (
        await db.execute(
            text(
                """SELECT id::text FROM inspection_checkpoints
                   WHERE id=CAST(:c AS uuid) AND inspection_round_id=CAST(:r AS uuid)"""
            ),
            {"c": str(checkpoint_id), "r": str(round_id)},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Checkpoint não encontrado nesta ronda.")


@router.post(
    "/{round_id}/checkpoints/{checkpoint_id}/fotos",
    status_code=status.HTTP_201_CREATED,
    summary="Anexar foto ao checkpoint",
    description="Sobe uma foto (jpeg/png/webp, máx. 10MB) como evidência do checkpoint.",
)
async def anexar_foto_checkpoint(
    round_id: UUID,
    checkpoint_id: UUID,
    current_user: CurrentActiveUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _checkpoint_da_ronda(db, round_id, checkpoint_id)
    ext = _MIME_EXT.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status_code=422, detail="Formato inválido — envie JPEG, PNG ou WebP.")
    conteudo = await file.read()
    if len(conteudo) > _MAX_FOTO_BYTES:
        raise HTTPException(status_code=422, detail="Foto acima de 10MB.")
    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    base = unicodedata.normalize("NFKD", Path(file.filename or "foto").stem)
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base.encode("ascii", "ignore").decode())[:40] or "foto"
    nome = f"{uuid4().hex[:8]}_{base}{ext}"
    destino = FOTOS_DIR / str(round_id) / str(checkpoint_id)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nome).write_bytes(conteudo)

    foto = {
        "arquivo": nome,
        "tamanho_bytes": len(conteudo),
        "content_type": file.content_type,
        "enviada_em": datetime.now(_TZ_MANAUS).replace(tzinfo=None).isoformat(timespec="seconds"),
        "enviada_por": getattr(current_user, "email", None) or str(getattr(current_user, "id", "")),
        "url": f"/api/v1/operacional/rondas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}",
    }
    total = (
        await db.execute(
            text(
                """UPDATE inspection_checkpoints
                   SET photos = COALESCE(photos, '[]'::jsonb) || CAST(:foto AS jsonb),
                       updated_at = now()
                   WHERE id = CAST(:c AS uuid)
                   RETURNING jsonb_array_length(photos)"""
            ),
            {"foto": json.dumps([foto]), "c": str(checkpoint_id)},
        )
    ).scalar()
    await db.commit()
    logger.info(f"[rondas] foto anexada ao checkpoint {checkpoint_id} ({nome}, {len(conteudo)}b)")
    return {"ok": True, "foto": foto, "total_fotos": int(total or 1)}


@router.get(
    "/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}",
    summary="Baixar foto do checkpoint",
)
async def baixar_foto_checkpoint(
    round_id: UUID,
    checkpoint_id: UUID,
    nome: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await _checkpoint_da_ronda(db, round_id, checkpoint_id)
    base = (FOTOS_DIR / str(round_id) / str(checkpoint_id)).resolve()
    alvo = (base / nome).resolve()
    if not str(alvo).startswith(str(base)) or not alvo.is_file():
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return FileResponse(alvo)
