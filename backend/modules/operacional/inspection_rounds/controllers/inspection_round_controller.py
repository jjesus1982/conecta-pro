"""
Controller de Rondas de Inspecao - Endpoints FastAPI.

Author: Conecta PRO Team
Date: 2026-01-23
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, get_current_active_user
from core.database import get_db
from modules.operacional.publishers import publish_ronda_concluida

from ..schemas import (
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
    "/minhas-rondas",
    response_model=list[InspectionRoundSummary],
    summary="Rondas do inspetor (mais recentes primeiro)",
)
async def minhas_rondas(
    current_user: CurrentActiveUser,
    inspector_id: UUID = Query(..., description="ID do inspetor"),
    tenant_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> list[InspectionRoundSummary]:
    """A ronda-mobile chamava esta rota e caía em /{round_id} (422) — frente 6 (12/09/2026)."""
    rounds = await service.get_rounds_by_inspector(str(inspector_id), str(tenant_id) if tenant_id else None, limit)
    return [InspectionRoundSummary.model_validate(r) for r in rounds]


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


# =============================================================================
# FOTOS DE CHECKPOINT — evidências REAIS no sistema (nada em grupo de WhatsApp)
# =============================================================================

# produção monta /opt/conecta-pro/uploads em /app/uploads; staging tem /app somente-leitura e UPLOADS_DIR=/tmp/uploads
FOTOS_DIR = Path(os.environ.get("UPLOADS_DIR", "/app/uploads")) / "rondas"
_MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_FOTO_BYTES = 10 * 1024 * 1024  # 10 MB
_TZ_MANAUS = ZoneInfo("America/Manaus")


def _parse_hora(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"hora_aparelho inválida: {v!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _gravar_foto(
    round_id: UUID, checkpoint_id: str, file: UploadFile, current_user,
    capturada_na_hora: bool, hora_aparelho: datetime | None,
) -> dict:
    """Valida, grava em disco e devolve o registro da foto com os carimbos (frente 6).

    hora_servidor é a oficial; hora_aparelho vai ao lado; hash identifica a imagem (retentativa
    não duplica). capturada_na_hora=True só quando veio da câmera do app — a galeria é False.
    """
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
    agora = datetime.now(UTC)
    return {
        "arquivo": nome,
        "tamanho_bytes": len(conteudo),
        "content_type": file.content_type,
        "hash_imagem": hashlib.sha256(conteudo).hexdigest(),
        "capturada_na_hora": bool(capturada_na_hora),
        "hora_aparelho": hora_aparelho.isoformat(timespec="seconds") if hora_aparelho else None,
        "hora_servidor": agora.isoformat(timespec="seconds"),
        "enviada_em": agora.astimezone(_TZ_MANAUS).replace(tzinfo=None).isoformat(timespec="seconds"),
        "enviada_por": getattr(current_user, "email", None) or str(getattr(current_user, "id", "")),
        "url": f"/api/v1/operacional/rondas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}",
    }


@router.post(
    "/{round_id}/checkpoints/completo",
    status_code=status.HTTP_201_CREATED,
    summary="Checkpoint + fotos numa única requisição (frente 6)",
    description=(
        "multipart: `dados` = JSON de CheckpointCreate; `fotos` = imagens da CÂMERA (capturada_na_hora); "
        "`anexos` = imagens da galeria (não valem como prova). Repetição da mesma `chave_idempotente` "
        "devolve 200 com o checkpoint já gravado, sem duplicar."
    ),
)
async def create_checkpoint_completo(
    round_id: UUID,
    current_user: CurrentActiveUser,
    response: Response,
    dados: str = Form(...),
    fotos: list[UploadFile] = File(default=[]),
    anexos: list[UploadFile] = File(default=[]),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> dict:
    try:
        data = CheckpointCreate.model_validate_json(dados)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    if data.chave_idempotente:
        existente = await service.repository.get_checkpoint_by_chave(data.chave_idempotente)
        if existente:
            response.status_code = status.HTTP_200_OK
            return {"repetida": True, "checkpoint": CheckpointResponse.model_validate(existente)}

    hora_aparelho = data.hora_aparelho
    if hora_aparelho and not hora_aparelho.tzinfo:
        hora_aparelho = hora_aparelho.replace(tzinfo=UTC)
    checkpoint_id = str(uuid4())
    registros: list[dict] = []
    try:
        for f in fotos:
            registros.append(await _gravar_foto(round_id, checkpoint_id, f, current_user, True, hora_aparelho))
        for f in anexos:
            registros.append(await _gravar_foto(round_id, checkpoint_id, f, current_user, False, hora_aparelho))
        checkpoint, repetida = await service.create_checkpoint_completo(
            str(round_id), data, fotos=registros, checkpoint_id=checkpoint_id
        )
        await service.db.commit()
    except Exception as e:
        # transação única: sem checkpoint, sem arquivo em disco (nada de foto órfã)
        shutil.rmtree(FOTOS_DIR / str(round_id) / checkpoint_id, ignore_errors=True)
        if isinstance(e, InspectionRoundNotFoundError):
            raise HTTPException(status_code=404, detail=str(e))
        if isinstance(e, InspectionRoundValidationError):
            raise HTTPException(status_code=422, detail=str(e))
        if isinstance(e, HTTPException):
            raise
        logger.exception(f"[rondas] falha no checkpoint completo da ronda {round_id}")
        raise HTTPException(status_code=500, detail="Erro interno ao gravar checkpoint com fotos")
    if repetida:
        # a chave já existia (corrida entre retentativas): os arquivos desta chamada são descartados
        shutil.rmtree(FOTOS_DIR / str(round_id) / checkpoint_id, ignore_errors=True)
        response.status_code = status.HTTP_200_OK
    return {"repetida": repetida, "checkpoint": CheckpointResponse.model_validate(checkpoint)}


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
    capturada_na_hora: bool = Form(False),
    hora_aparelho: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rota antiga (duas requisições). Um checkpoint `pendente_foto` só vira válido quando chega
    foto capturada na hora; a mesma imagem (hash) reenviada não duplica — frente 6."""
    await _checkpoint_da_ronda(db, round_id, checkpoint_id)
    h_ap = _parse_hora(hora_aparelho)
    if capturada_na_hora and h_ap is None:
        raise HTTPException(status_code=422, detail="Foto capturada na hora exige hora_aparelho.")
    foto = await _gravar_foto(round_id, str(checkpoint_id), file, current_user, capturada_na_hora, h_ap)
    caminho = FOTOS_DIR / str(round_id) / str(checkpoint_id) / foto["arquivo"]

    try:
        ja_tem = (
            await db.execute(
                text(
                    """SELECT f->>'arquivo' FROM inspection_checkpoints c,
                       jsonb_array_elements(COALESCE(c.photos,'[]'::jsonb)) f
                       WHERE c.id = CAST(:c AS uuid) AND f->>'hash_imagem' = :h LIMIT 1"""
                ),
                {"c": str(checkpoint_id), "h": foto["hash_imagem"]},
            )
        ).scalar()
        if ja_tem:
            caminho.unlink(missing_ok=True)
            return {"ok": True, "repetida": True, "foto": {"arquivo": ja_tem}, "total_fotos": None}

        row = (
            await db.execute(
                text(
                    """UPDATE inspection_checkpoints
                       SET photos = COALESCE(photos, '[]'::jsonb) || CAST(:foto AS jsonb),
                           hora_aparelho = COALESCE(hora_aparelho, CAST(:h_ap AS timestamptz)),
                           status = CASE WHEN status = 'pendente_foto' AND CAST(:na_hora AS boolean)
                                         THEN COALESCE(extra_data->>'status_pretendido', 'conforme')
                                         ELSE status END,
                           updated_at = now()
                       WHERE id = CAST(:c AS uuid)
                       RETURNING jsonb_array_length(photos), status"""
                ),
                {"foto": json.dumps([foto]), "c": str(checkpoint_id), "na_hora": bool(capturada_na_hora),
                 "h_ap": h_ap},
            )
        ).first()
        await db.commit()
    except Exception:
        # banco não aceitou: o arquivo não pode ficar sozinho em disco (órfã medida em 12/09)
        caminho.unlink(missing_ok=True)
        raise
    logger.info(f"[rondas] foto anexada ao checkpoint {checkpoint_id} ({foto['arquivo']}, {foto['tamanho_bytes']}b)")
    return {"ok": True, "repetida": False, "foto": foto, "total_fotos": int(row[0] or 1), "status": row[1]}


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


@router.get("/{round_id}/relatorio/pdf", summary="Relatório da ronda em PDF (marca Conecta)")
async def round_relatorio_pdf(
    round_id: str,
    download: bool = Query(False),
    service: InspectionRoundService = Depends(get_inspection_service),
):
    """Gera o relatório da ronda (dados + checkpoints + resumo) em PDF branded."""
    from fastapi.responses import Response as _Resp

    from modules.financial.services.relatorio_financeiro_pdf import gerar_relatorio_pdf

    r = await service.get_by_id(str(round_id))
    if not r:
        raise HTTPException(status_code=404, detail="ronda não encontrada")

    def g(o, k, d="—"):
        return getattr(o, k, d) or d

    def dt(v):
        try:
            return v.strftime("%d/%m/%Y %H:%M")
        except Exception:  # noqa: BLE001
            return str(v or "—")

    code = str(g(r, "code", ""))
    secoes = [{"titulo": f"Ronda {code}", "linhas": [
        ("Inspetor", f"{g(r, 'inspector_name')} ({g(r, 'inspector_role', '')})"),
        ("Status", str(g(r, "status"))),
        ("Agendada", dt(getattr(r, "scheduled_date", None))),
        ("Iniciada", dt(getattr(r, "started_at", None))),
        ("Concluída", dt(getattr(r, "completed_at", None))),
        ("Duração (min)", str(g(r, "duration_minutes", "—"))),
        ("Postos visitados", f"{g(r, 'posts_visited', '?')}/{g(r, 'posts_to_visit', '?')}"),
    ]}]
    cps = list(getattr(r, "checkpoints", []) or [])
    linhas_cp = []
    for cp in sorted(cps, key=lambda c: getattr(c, "sequence", 0) or 0):
        rot = f"{g(cp, 'post_name')} · {g(cp, 'checkpoint_type', '')}"
        emp = g(cp, "employee_name", "")
        val = str(g(cp, "status", "")) + (f" · {emp}" if emp and emp != "—" else "")
        linhas_cp.append((rot, val))
    secoes.append({"titulo": f"Checkpoints ({len(cps)})", "linhas": linhas_cp or [("(sem checkpoints)", "")]})
    secoes.append({"titulo": "Resumo", "linhas": [
        ("Total de checkpoints", str(g(r, "total_checkpoints", "0"))),
        ("Ocorrências", str(g(r, "total_occurrences", "0"))),
        ("Medidas disciplinares", str(g(r, "total_disciplinary_actions", "0"))),
    ]})
    obs = g(r, "observations", "")
    if obs and obs != "—":
        secoes.append({"titulo": "Observações", "linhas": [("", str(obs)[:400])]})

    pdf = gerar_relatorio_pdf("Relatório de Ronda", f"Ronda {code} · {dt(getattr(r, 'scheduled_date', None))}", secoes)
    disp = "attachment" if download else "inline"
    return _Resp(content=pdf, media_type="application/pdf",
                 headers={"Content-Disposition": f'{disp}; filename="ronda_{code or round_id}.pdf"'})
