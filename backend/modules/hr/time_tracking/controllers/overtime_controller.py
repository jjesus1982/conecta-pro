"""Controller para Overtime (Horas Extras)."""
# pylint: disable=unused-argument

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.hr.time_tracking.models import OvertimeStatus, OvertimeType
from modules.hr.time_tracking.repositories import OvertimeRepository
from modules.hr.time_tracking.schemas import (
    OvertimeApproval,
    OvertimeCompensation,
    OvertimeCreate,
    OvertimeFilter,
    OvertimeListResponse,
    OvertimePayment,
    OvertimePreApproval,
    OvertimeRejection,
    OvertimeResponse,
    OvertimeStats,
    OvertimeSummary,
    OvertimeUpdate,
)

router = APIRouter(
    prefix="/overtime",
    tags=["Ponto Eletrônico - Horas Extras"],
)


@router.post(
    "/",
    response_model=OvertimeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar hora extra",
)
async def create_overtime(
    data: OvertimeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cria um novo registro de hora extra.

    Pode ser criado manualmente ou automaticamente pelo sistema
    ao detectar horas trabalhadas além da jornada.
    """
    repo = OvertimeRepository(db)

    overtime = await repo.create(data, created_by_id=getattr(current_user, "id", None))
    await db.commit()

    return overtime


@router.get(
    "/",
    response_model=list[OvertimeListResponse],
    summary="Listar horas extras",
)
async def list_overtime(  # pylint: disable=too-many-locals
    employee_id: str | None = None,
    overtime_type: OvertimeType | None = None,
    overtime_status: OvertimeStatus | None = Query(None, alias="status"),
    condominium_id: str | None = None,
    department_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    is_approved: bool | None = None,
    is_compensated: bool | None = None,
    is_paid: bool | None = None,
    requires_pre_approval: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista registros de hora extra com filtros."""
    repo = OvertimeRepository(db)

    filters = OvertimeFilter(
        employee_id=employee_id,
        overtime_type=overtime_type,
        status=overtime_status,
        condominium_id=condominium_id,
        department_id=department_id,
        date_from=date_from,
        date_to=date_to,
        is_approved=is_approved,
        is_compensated=is_compensated,
        is_paid=is_paid,
        requires_pre_approval=requires_pre_approval,
    )

    overtimes, _total = await repo.list(filters, skip, limit)

    return overtimes


@router.get(
    "/stats",
    response_model=OvertimeStats,
    summary="Estatísticas de horas extras",
)
async def get_overtime_stats(
    condominium_id: str | None = None,
    employee_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Retorna estatísticas consolidadas de horas extras."""
    repo = OvertimeRepository(db)

    stats = await repo.get_stats(
        condominium_id=condominium_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
    )

    return OvertimeStats(**stats)


@router.get(
    "/pending-approval",
    response_model=list[OvertimeListResponse],
    summary="Horas extras pendentes de aprovação",
)
async def get_pending_approval(
    condominium_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Lista horas extras pendentes de aprovação."""
    repo = OvertimeRepository(db)

    overtimes = await repo.get_pending_approval(condominium_id, skip, limit)

    return overtimes


@router.get(
    "/pending-compensation",
    response_model=list[OvertimeListResponse],
    summary="Horas extras pendentes de compensação",
)
async def get_pending_compensation(
    employee_id: str | None = None,
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista horas extras aprovadas pendentes de compensação (banco de horas)."""
    repo = OvertimeRepository(db)

    overtimes = await repo.get_pending_compensation(employee_id, condominium_id)

    return overtimes


@router.get(
    "/pending-payment",
    response_model=list[OvertimeListResponse],
    summary="Horas extras pendentes de pagamento",
)
async def get_pending_payment(
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista horas extras aprovadas pendentes de pagamento."""
    repo = OvertimeRepository(db)

    overtimes = await repo.get_pending_payment(condominium_id)

    return overtimes


@router.get(
    "/employee/{employee_id}/summary",
    response_model=OvertimeSummary,
    summary="Resumo do funcionário",
)
async def get_employee_summary(
    employee_id: str,
    reference_month: int = Query(..., ge=1, le=12),
    reference_year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna resumo de horas extras do funcionário no mês."""
    repo = OvertimeRepository(db)

    summary = await repo.get_employee_summary(employee_id, reference_month, reference_year)

    return OvertimeSummary(**summary)


@router.get(
    "/{overtime_id}",
    response_model=OvertimeResponse,
    summary="Buscar hora extra por ID",
)
async def get_overtime(
    overtime_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna detalhes de um registro de hora extra."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    return overtime


@router.patch(
    "/{overtime_id}",
    response_model=OvertimeResponse,
    summary="Atualizar hora extra",
)
async def update_overtime(
    overtime_id: UUID,
    data: OvertimeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Atualiza um registro de hora extra."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status == OvertimeStatus.APROVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hora extra já aprovada não pode ser alterada",
        )

    overtime = await repo.update(overtime, data)
    await db.commit()

    return overtime


@router.post(
    "/{overtime_id}/pre-approve",
    response_model=OvertimeResponse,
    summary="Pré-aprovar hora extra",
)
async def pre_approve_overtime(
    overtime_id: UUID,
    data: OvertimePreApproval = OvertimePreApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Pré-aprova uma hora extra (para casos que requerem autorização prévia)."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status != OvertimeStatus.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hora extra com status '{overtime.status.value}' não pode ser pré-aprovada",
        )

    overtime.pre_approve(
        approved_by_id=getattr(current_user, "id", None),
        approved_by_name=getattr(current_user, "name", ""),
        notes=data.notes,
    )

    await db.commit()
    await db.refresh(overtime)

    return overtime


@router.post(
    "/{overtime_id}/approve",
    response_model=OvertimeResponse,
    summary="Aprovar hora extra",
)
async def approve_overtime(
    overtime_id: UUID,
    data: OvertimeApproval = OvertimeApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Aprova uma hora extra."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status not in [OvertimeStatus.PENDENTE, OvertimeStatus.EM_ANALISE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hora extra com status '{overtime.status.value}' não pode ser aprovada",
        )

    overtime.approve(
        approved_by_id=getattr(current_user, "id", None),
        approved_by_name=getattr(current_user, "name", ""),
        compensation_type=data.compensation_type,
        notes=data.notes,
    )

    await db.commit()
    await db.refresh(overtime)

    return overtime


@router.post(
    "/{overtime_id}/reject",
    response_model=OvertimeResponse,
    summary="Rejeitar hora extra",
)
async def reject_overtime(
    overtime_id: UUID,
    data: OvertimeRejection,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Rejeita uma hora extra."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status == OvertimeStatus.APROVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hora extra já aprovada não pode ser rejeitada",
        )

    overtime.reject(
        rejected_by_id=getattr(current_user, "id", None),
        rejected_by_name=getattr(current_user, "name", ""),
        reason=data.reason,
    )

    await db.commit()
    await db.refresh(overtime)

    return overtime


@router.post(
    "/{overtime_id}/compensate",
    response_model=OvertimeResponse,
    summary="Registrar compensação",
)
async def compensate_overtime(
    overtime_id: UUID,
    data: OvertimeCompensation,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Registra compensação de hora extra (banco de horas)."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status != OvertimeStatus.APROVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas horas extras aprovadas podem ser compensadas",
        )

    if overtime.is_compensated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hora extra já foi compensada",
        )

    overtime.compensate(
        compensation_date=data.compensation_date,
        compensation_minutes=data.compensation_minutes,
    )

    await db.commit()
    await db.refresh(overtime)

    return overtime


@router.post(
    "/{overtime_id}/mark-paid",
    response_model=OvertimeResponse,
    summary="Marcar como paga",
)
async def mark_overtime_paid(
    overtime_id: UUID,
    data: OvertimePayment,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Marca hora extra como paga."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status != OvertimeStatus.APROVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas horas extras aprovadas podem ser marcadas como pagas",
        )

    if overtime.is_paid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hora extra já foi paga",
        )

    overtime.mark_as_paid(
        payroll_reference=data.payroll_reference,
        payment_date=data.payment_date,
    )

    await db.commit()
    await db.refresh(overtime)

    return overtime


@router.delete(
    "/{overtime_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir hora extra",
)
async def delete_overtime(
    overtime_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Exclui um registro de hora extra (soft delete)."""
    repo = OvertimeRepository(db)

    overtime = await repo.get_by_id(overtime_id)
    if not overtime:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hora extra não encontrada",
        )

    if overtime.status == OvertimeStatus.APROVADA and (overtime.is_paid or overtime.is_compensated):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir hora extra já paga ou compensada",
        )

    await repo.delete(overtime)
    await db.commit()
