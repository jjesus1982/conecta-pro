"""Controller para TimeJustification (Justificativas)."""
# pylint: disable=unused-argument

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.hr.time_tracking.models import (
    JustificationCategory,
    JustificationStatus,
    JustificationType,
)
from modules.hr.time_tracking.repositories import TimeJustificationRepository
from modules.hr.time_tracking.schemas import (
    TimeJustificationAnalysis,
    TimeJustificationApproval,
    TimeJustificationCreate,
    TimeJustificationFilter,
    TimeJustificationListResponse,
    TimeJustificationPartialApproval,
    TimeJustificationRejection,
    TimeJustificationResponse,
    TimeJustificationStats,
    TimeJustificationUpdate,
    TimeJustificationVerification,
)

router = APIRouter(
    prefix="/justifications",
    tags=["Ponto Eletrônico - Justificativas"],
)


@router.post(
    "/",
    response_model=TimeJustificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar justificativa",
)
async def create_justification(
    data: TimeJustificationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cria uma nova justificativa de ausência, atraso ou outro tipo.

    Pode incluir informações médicas (atestados) e anexos.
    """
    repo = TimeJustificationRepository(db)

    # Verifica sobreposição
    overlap = await repo.check_overlap(
        data.employee_id,
        data.start_date,
        data.end_date,
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe justificativa para este período (código: {overlap.code})",
        )

    justification = await repo.create(data, created_by_id=getattr(current_user, "id", None))
    await db.commit()

    return justification


@router.get(
    "/",
    response_model=list[TimeJustificationListResponse],
    summary="Listar justificativas",
)
async def list_justifications(  # pylint: disable=too-many-locals,unused-argument
    employee_id: str | None = None,
    justification_type: JustificationType | None = None,
    category: JustificationCategory | None = None,
    justification_status: JustificationStatus | None = Query(None, alias="status"),
    condominium_id: str | None = None,
    department_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    is_pending: bool | None = None,
    is_verified: bool | None = None,
    has_attachments: bool | None = None,
    is_late_submission: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista justificativas com filtros avançados."""
    repo = TimeJustificationRepository(db)

    filters = TimeJustificationFilter(
        employee_id=employee_id,
        justification_type=justification_type,
        category=category,
        status=justification_status,
        condominium_id=condominium_id,
        department_id=department_id,
        date_from=date_from,
        date_to=date_to,
        is_pending=is_pending,
        is_verified=is_verified,
        has_attachments=has_attachments,
        is_late_submission=is_late_submission,
    )

    justifications, _total = await repo.list(filters, skip, limit)

    return justifications


@router.get(
    "/stats",
    response_model=TimeJustificationStats,
    summary="Estatísticas de justificativas",
)
async def get_justification_stats(  # pylint: disable=unused-argument
    condominium_id: str | None = None,
    employee_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Retorna estatísticas consolidadas de justificativas."""
    repo = TimeJustificationRepository(db)

    stats = await repo.get_stats(
        condominium_id=condominium_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
    )

    return TimeJustificationStats(**stats)


@router.get(
    "/pending-approval",
    response_model=list[TimeJustificationListResponse],
    summary="Justificativas pendentes de aprovação",
)
async def get_pending_approval(  # pylint: disable=unused-argument
    condominium_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Lista justificativas pendentes de aprovação."""
    repo = TimeJustificationRepository(db)

    justifications = await repo.get_pending_approval(condominium_id, skip, limit)

    return justifications


@router.get(
    "/pending-verification",
    response_model=list[TimeJustificationListResponse],
    summary="Justificativas pendentes de verificação RH",
)
async def get_pending_verification(  # pylint: disable=unused-argument
    condominium_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista justificativas aprovadas pendentes de verificação do RH."""
    repo = TimeJustificationRepository(db)

    justifications = await repo.get_pending_verification(condominium_id, skip, limit)

    return justifications


@router.get(
    "/medical-leaves",
    response_model=list[TimeJustificationListResponse],
    summary="Atestados médicos",
)
async def get_medical_leaves(
    employee_id: str | None = None,
    condominium_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista todos os atestados médicos e licenças."""
    repo = TimeJustificationRepository(db)

    justifications = await repo.get_medical_leaves(
        employee_id=employee_id,
        condominium_id=condominium_id,
        date_from=date_from,
        date_to=date_to,
    )

    return justifications


@router.get(
    "/{justification_id}",
    response_model=TimeJustificationResponse,
    summary="Buscar justificativa por ID",
)
async def get_justification(
    justification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna detalhes de uma justificativa."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    return justification


@router.patch(
    "/{justification_id}",
    response_model=TimeJustificationResponse,
    summary="Atualizar justificativa",
)
async def update_justification(
    justification_id: UUID,
    data: TimeJustificationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Atualiza uma justificativa (apenas se ainda em rascunho)."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status != JustificationStatus.RASCUNHO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas justificativas em rascunho podem ser alteradas",
        )

    # Verifica sobreposição se datas mudaram
    if data.start_date or data.end_date:
        overlap = await repo.check_overlap(
            justification.employee_id,
            data.start_date or justification.start_date,
            data.end_date or justification.end_date,
            exclude_id=justification_id,
        )
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe justificativa para este período (código: {overlap.code})",
            )

    justification = await repo.update(justification, data)
    await db.commit()

    return justification


@router.post(
    "/{justification_id}/submit",
    response_model=TimeJustificationResponse,
    summary="Submeter justificativa",
)
async def submit_justification(
    justification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Submete uma justificativa para análise."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status != JustificationStatus.RASCUNHO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas justificativas em rascunho podem ser submetidas",
        )

    justification.submit()
    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/analyze",
    response_model=TimeJustificationResponse,
    summary="Iniciar análise",
)
async def analyze_justification(
    justification_id: UUID,
    data: TimeJustificationAnalysis = TimeJustificationAnalysis(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Marca justificativa como em análise."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status != JustificationStatus.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas justificativas submetidas podem entrar em análise",
        )

    justification.status = JustificationStatus.EM_ANALISE
    justification.analyzed_by_id = getattr(current_user, "id", None)
    justification.analyzed_by_name = getattr(current_user, "name", "")

    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/approve",
    response_model=TimeJustificationResponse,
    summary="Aprovar justificativa",
)
async def approve_justification(
    justification_id: UUID,
    data: TimeJustificationApproval = TimeJustificationApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Aprova uma justificativa."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status not in [
        JustificationStatus.PENDENTE,
        JustificationStatus.EM_ANALISE,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Justificativa com status '{justification.status.value}' não pode ser aprovada",
        )

    justification.approve(
        approved_by_id=getattr(current_user, "id", None),
        approved_by_name=getattr(current_user, "name", ""),
        notes=data.notes,
    )

    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/partial-approve",
    response_model=TimeJustificationResponse,
    summary="Aprovar parcialmente",
)
async def partial_approve_justification(
    justification_id: UUID,
    data: TimeJustificationPartialApproval,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Aprova parcialmente uma justificativa (menos dias que solicitado)."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status not in [
        JustificationStatus.PENDENTE,
        JustificationStatus.EM_ANALISE,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Justificativa com status '{justification.status.value}' não pode ser aprovada",
        )

    justification.status = JustificationStatus.APROVADA_PARCIAL
    justification.partial_approved_days = data.approved_days
    justification.partial_approved_minutes = data.approved_minutes
    justification.approved_by_id = getattr(current_user, "id", None)
    justification.approved_by_name = getattr(current_user, "name", "")
    justification.approval_notes = data.notes

    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/reject",
    response_model=TimeJustificationResponse,
    summary="Rejeitar justificativa",
)
async def reject_justification(
    justification_id: UUID,
    data: TimeJustificationRejection,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Rejeita uma justificativa."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status in [
        JustificationStatus.APROVADA,
        JustificationStatus.REJEITADA,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Justificativa com status '{justification.status.value}' não pode ser rejeitada"),
        )

    justification.reject(
        rejected_by_id=getattr(current_user, "id", None),
        rejected_by_name=getattr(current_user, "name", ""),
        reason=data.reason,
    )

    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/verify",
    response_model=TimeJustificationResponse,
    summary="Verificar justificativa (RH)",
)
async def verify_justification(
    justification_id: UUID,
    data: TimeJustificationVerification = TimeJustificationVerification(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Verifica uma justificativa aprovada (etapa final do RH)."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status not in [
        JustificationStatus.APROVADA,
        JustificationStatus.APROVADA_PARCIAL,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas justificativas aprovadas podem ser verificadas",
        )

    justification.verify(
        verified_by_id=getattr(current_user, "id", None),
        verified_by_name=getattr(current_user, "name", ""),
        notes=data.notes,
    )

    await db.commit()
    await db.refresh(justification)

    return justification


@router.post(
    "/{justification_id}/attachments",
    response_model=TimeJustificationResponse,
    summary="Adicionar anexo",
    status_code=201,
)
async def add_attachment(
    justification_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Adiciona um anexo à justificativa (atestado, documento, etc)."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    # Validações de arquivo
    _max_size = 10 * 1024 * 1024  # 10MB (reservado para validação futura)
    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/gif",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de arquivo não permitido",
        )

    # Por enquanto, simula adição
    attachment_info = {
        "name": file.filename,
        "type": file.content_type,
        "size": 0,  # file.size quando disponível
        "url": f"/attachments/{justification_id}/{file.filename}",
    }

    justification.add_attachment(attachment_info)

    await db.commit()
    await db.refresh(justification)

    return justification


@router.delete(
    "/{justification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir justificativa",
)
async def delete_justification(
    justification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Exclui uma justificativa (soft delete)."""
    repo = TimeJustificationRepository(db)

    justification = await repo.get_by_id(justification_id)
    if not justification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificativa não encontrada",
        )

    if justification.status == JustificationStatus.APROVADA and justification.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir justificativa aprovada e verificada",
        )

    await repo.delete(justification)
    await db.commit()
