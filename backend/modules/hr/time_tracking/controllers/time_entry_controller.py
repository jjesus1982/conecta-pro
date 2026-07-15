"""Controller para TimeEntry (Registros de Ponto)."""
# pylint: disable=unused-argument

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.hr.time_tracking.models import (
    AnomalyType,
    EntryStatus,
    EntryType,
    RegistrationMethod,
)
from modules.hr.time_tracking.repositories import TimeEntryRepository
from modules.hr.time_tracking.schemas import (
    TimeEntryApproval,
    TimeEntryCreate,
    TimeEntryDaySummary,
    TimeEntryFilter,
    TimeEntryListResponse,
    TimeEntryManualAdjust,
    TimeEntryResponse,
    TimeEntryStats,
    TimeEntryUpdate,
)
from modules.hr.time_tracking.services import (
    AnomalyDetectionService,
    TimeCalculationService,
)

router = APIRouter(
    prefix="/time-entries",
    tags=["Ponto Eletrônico - Registros"],
)


@router.post(
    "/",
    response_model=TimeEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar ponto",
)
async def create_time_entry(
    data: TimeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cria um novo registro de ponto.

    Pode ser entrada, saída, intervalo, etc.
    Detecta automaticamente anomalias como atrasos e duplicatas.
    """
    repo = TimeEntryRepository(db)

    # Verifica duplicata
    existing = await repo.check_duplicate(
        data.employee_id,
        data.entry_date,
        data.entry_type,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Registro de {data.entry_type.value} já existe para esta data",
        )

    entry = await repo.create(data, created_by_id=getattr(current_user, "id", None))
    await db.commit()

    return entry


@router.get(
    "/",
    response_model=list[TimeEntryListResponse],
    summary="Listar registros de ponto",
)
async def list_time_entries(  # pylint: disable=too-many-locals
    employee_id: str | None = None,
    entry_type: EntryType | None = None,
    entry_status: EntryStatus | None = Query(None, alias="status"),
    registration_method: RegistrationMethod | None = None,
    anomaly_type: AnomalyType | None = None,
    condominium_id: str | None = None,
    department_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    has_anomaly: bool | None = None,
    requires_approval: bool | None = None,
    is_manual_entry: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista registros de ponto com filtros avançados."""
    repo = TimeEntryRepository(db)

    filters = TimeEntryFilter(
        employee_id=employee_id,
        entry_type=entry_type,
        status=entry_status,
        registration_method=registration_method,
        anomaly_type=anomaly_type,
        condominium_id=condominium_id,
        department_id=department_id,
        date_from=date_from,
        date_to=date_to,
        has_anomaly=has_anomaly,
        requires_approval=requires_approval,
        is_manual_entry=is_manual_entry,
    )

    entries, _total = await repo.list(filters, skip, limit)

    return entries


@router.get(
    "/stats",
    response_model=TimeEntryStats,
    summary="Estatísticas de registros",
)
async def get_time_entry_stats(
    condominium_id: str | None = None,
    employee_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna estatísticas consolidadas de registros de ponto."""
    repo = TimeEntryRepository(db)

    stats = await repo.get_stats(
        condominium_id=condominium_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
    )

    return TimeEntryStats(**stats)


@router.get(
    "/pending-approval",
    response_model=list[TimeEntryListResponse],
    summary="Registros pendentes de aprovação",
)
async def get_pending_approval(
    condominium_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Lista registros que precisam de aprovação."""
    repo = TimeEntryRepository(db)

    entries = await repo.get_pending_approval(condominium_id, skip, limit)

    return entries


@router.get(
    "/with-anomalies",
    response_model=list[TimeEntryListResponse],
    summary="Registros com anomalias",
)
async def get_with_anomalies(
    condominium_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Lista registros com anomalias não resolvidas."""
    repo = TimeEntryRepository(db)

    entries = await repo.get_with_anomalies(condominium_id, date_from, date_to, skip, limit)

    return entries


@router.get(
    "/employee/{employee_id}/day/{entry_date}",
    response_model=TimeEntryDaySummary,
    summary="Resumo do dia do funcionário",
)
async def get_employee_day_summary(
    employee_id: str,
    entry_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna resumo do dia com todos os registros e cálculos."""
    repo = TimeEntryRepository(db)
    calc_service = TimeCalculationService()
    anomaly_service = AnomalyDetectionService()

    entries = await repo.get_by_employee_date(employee_id, entry_date)

    if not entries:
        return TimeEntryDaySummary(
            employee_id=employee_id,
            date=entry_date,
            entries=[],
            worked_minutes=0,
            expected_minutes=0,
            balance_minutes=0,
            anomalies=[],
        )

    # Calcula horas
    calc_result = calc_service.calculate_worked_hours(entries)

    # Detecta anomalias
    anomalies = anomaly_service.analyze_entries(entries)

    return TimeEntryDaySummary(
        employee_id=employee_id,
        date=entry_date,
        entries=[TimeEntryListResponse.model_validate(e) for e in entries],
        worked_minutes=calc_result["worked_minutes"],
        expected_minutes=calc_result["expected_minutes"],
        balance_minutes=calc_result["balance_minutes"],
        overtime_minutes=calc_result["overtime_minutes"],
        night_minutes=calc_result["night_minutes"],
        late_minutes=calc_result["late_minutes"],
        early_departure_minutes=calc_result["early_departure_minutes"],
        anomalies=[
            {
                "type": a.anomaly_type.value,
                "score": a.score,
                "description": a.description,
                "severity": a.severity,
            }
            for a in anomalies
        ],
    )


@router.get(
    "/{entry_id}",
    response_model=TimeEntryResponse,
    summary="Buscar registro por ID",
)
async def get_time_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna detalhes de um registro de ponto."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    return entry


@router.patch(
    "/{entry_id}",
    response_model=TimeEntryResponse,
    summary="Atualizar registro",
)
async def update_time_entry(
    entry_id: UUID,
    data: TimeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Atualiza um registro de ponto existente."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    if entry.status == EntryStatus.APROVADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registro já aprovado não pode ser alterado",
        )

    entry = await repo.update(entry, data)
    await db.commit()

    return entry


@router.post(
    "/{entry_id}/approve",
    response_model=TimeEntryResponse,
    summary="Aprovar registro",
)
async def approve_time_entry(
    entry_id: UUID,
    data: TimeEntryApproval,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Aprova um registro de ponto pendente."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    if entry.status != EntryStatus.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registro com status '{entry.status.value}' não pode ser aprovado",
        )

    entry.approve(
        approved_by_id=getattr(current_user, "id", None),
        approved_by_name=getattr(current_user, "name", ""),
        notes=data.notes,
    )

    await db.commit()
    await db.refresh(entry)

    return entry


@router.post(
    "/{entry_id}/reject",
    response_model=TimeEntryResponse,
    summary="Rejeitar registro",
)
async def reject_time_entry(
    entry_id: UUID,
    reason: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Rejeita um registro de ponto."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    entry.reject(
        rejected_by_id=getattr(current_user, "id", None),
        rejected_by_name=getattr(current_user, "name", ""),
        reason=reason,
    )

    await db.commit()
    await db.refresh(entry)

    return entry


@router.post(
    "/{entry_id}/manual-adjust",
    response_model=TimeEntryResponse,
    summary="Ajuste manual",
)
async def manual_adjust_entry(
    entry_id: UUID,
    data: TimeEntryManualAdjust,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Realiza ajuste manual em um registro."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    # Guarda valores originais
    entry.original_time = entry.entry_time

    # Aplica ajuste
    entry.entry_time = data.new_time
    entry.mark_as_manual(
        adjusted_by_id=getattr(current_user, "id", None),
        adjusted_by_name=getattr(current_user, "name", ""),
        reason=data.reason,
    )

    await db.commit()
    await db.refresh(entry)

    return entry


@router.post(
    "/{entry_id}/resolve-anomaly",
    response_model=TimeEntryResponse,
    summary="Resolver anomalia",
)
async def resolve_anomaly(
    entry_id: UUID,
    resolution: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Marca anomalia como resolvida."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    if not entry.anomaly_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registro não possui anomalia",
        )

    entry.anomaly_resolved = True
    entry.anomaly_resolution = resolution

    await db.commit()
    await db.refresh(entry)

    return entry


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir registro",
)
async def delete_time_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Exclui um registro de ponto (soft delete)."""
    repo = TimeEntryRepository(db)

    entry = await repo.get_by_id(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    await repo.delete(entry)
    await db.commit()
