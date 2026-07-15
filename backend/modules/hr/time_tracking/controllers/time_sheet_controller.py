"""Controller para TimeSheet (Folha de Ponto)."""
# pylint: disable=unused-argument

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.hr.time_tracking.models import TimeSheetStatus
from modules.hr.time_tracking.repositories import TimeSheetRepository
from modules.hr.time_tracking.schemas import (
    TimeSheetBatchAction,
    TimeSheetCreate,
    TimeSheetEmployeeApproval,
    TimeSheetFilter,
    TimeSheetHRApproval,
    TimeSheetListResponse,
    TimeSheetManagerApproval,
    TimeSheetPayroll,
    TimeSheetRecalculate,
    TimeSheetReopen,
    TimeSheetResponse,
    TimeSheetStats,
)
from modules.hr.time_tracking.services import ReportService, TimeSheetService

router = APIRouter(
    prefix="/time-sheets",
    tags=["Ponto Eletrônico - Folha de Ponto"],
)


@router.post(
    "/",
    response_model=TimeSheetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar folha de ponto",
)
async def create_time_sheet(
    data: TimeSheetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Cria uma nova folha de ponto para um funcionário.

    Se já existir, retorna erro. Use o endpoint de geração automática
    para criar ou atualizar.
    """
    repo = TimeSheetRepository(db)

    # Verifica se já existe
    existing = await repo.get_by_employee_month(
        data.employee_id,
        data.reference_month,
        data.reference_year,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Folha de ponto já existe para este período",
        )

    sheet = await repo.create(data, created_by_id=getattr(current_user, "id", None))
    await db.commit()

    return sheet


@router.post(
    "/generate",
    response_model=TimeSheetResponse,
    summary="Gerar folha de ponto",
)
async def generate_time_sheet(
    employee_id: str,
    employee_name: str,
    reference_month: int = Query(..., ge=1, le=12),
    reference_year: int = Query(..., ge=2000, le=2100),
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Gera ou atualiza a folha de ponto de um funcionário.

    Calcula automaticamente todos os totais a partir dos registros,
    horas extras e justificativas do período.
    """
    service = TimeSheetService(db)

    sheet = await service.generate_time_sheet(
        employee_id=employee_id,
        employee_name=employee_name,
        reference_month=reference_month,
        reference_year=reference_year,
        condominium_id=condominium_id,
        created_by_id=getattr(current_user, "id", None),
    )

    await db.commit()

    return sheet


@router.post(
    "/generate-batch",
    response_model=list[TimeSheetListResponse],
    summary="Gerar folhas em lote",
)
async def generate_time_sheets_batch(
    employee_ids: list[str],
    employee_data: dict,
    reference_month: int = Query(..., ge=1, le=12),
    reference_year: int = Query(..., ge=2000, le=2100),
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Gera folhas de ponto para múltiplos funcionários."""
    repo = TimeSheetRepository(db)

    sheets = await repo.bulk_create(
        employee_ids=employee_ids,
        employee_data=employee_data,
        reference_month=reference_month,
        reference_year=reference_year,
        condominium_id=condominium_id,
        created_by_id=getattr(current_user, "id", None),
    )

    await db.commit()

    return sheets


@router.get(
    "/",
    response_model=list[TimeSheetListResponse],
    summary="Listar folhas de ponto",
)
async def list_time_sheets(  # pylint: disable=too-many-locals
    employee_id: str | None = None,
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2000, le=2100),
    sheet_status: TimeSheetStatus | None = Query(None, alias="status"),
    condominium_id: str | None = None,
    department_id: str | None = None,
    has_pending_issues: bool | None = None,
    is_fully_approved: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista folhas de ponto com filtros."""
    repo = TimeSheetRepository(db)

    filters = TimeSheetFilter(
        employee_id=employee_id,
        reference_month=reference_month,
        reference_year=reference_year,
        status=sheet_status,
        condominium_id=condominium_id,
        department_id=department_id,
        has_pending_issues=has_pending_issues,
        is_fully_approved=is_fully_approved,
    )

    sheets, _total = await repo.list(filters, skip, limit)

    return sheets


@router.get(
    "/stats",
    response_model=TimeSheetStats,
    summary="Estatísticas de folhas",
)
async def get_time_sheet_stats(
    condominium_id: str | None = None,
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Retorna estatísticas consolidadas das folhas de ponto."""
    repo = TimeSheetRepository(db)

    stats = await repo.get_stats(
        condominium_id=condominium_id,
        reference_month=reference_month,
        reference_year=reference_year,
    )

    return TimeSheetStats(**stats)


@router.get(
    "/pending-employee-approval",
    response_model=list[TimeSheetListResponse],
    summary="Pendentes aprovação funcionário",
)
async def get_pending_employee_approval(
    employee_id: str | None = None,
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista folhas pendentes de aprovação do funcionário."""
    repo = TimeSheetRepository(db)

    # Se não for admin/rh, filtra pelo próprio usuário. current_user é objeto User
    # (get_current_user), não dict → getattr (o .get() crashava: 'User' has no 'get').
    user_role = getattr(current_user, "role", "") or ""
    if user_role not in ["admin", "rh"] and not employee_id:
        employee_id = getattr(current_user, "employee_id", None) or getattr(current_user, "id", None)

    sheets = await repo.get_pending_employee_approval(employee_id, condominium_id)

    return sheets


@router.get(
    "/pending-manager-approval",
    response_model=list[TimeSheetListResponse],
    summary="Pendentes aprovação gestor",
)
async def get_pending_manager_approval(
    condominium_id: str | None = None,
    department_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Lista folhas pendentes de aprovação do gestor."""
    repo = TimeSheetRepository(db)

    sheets = await repo.get_pending_manager_approval(condominium_id, department_id)

    return sheets


@router.get(
    "/pending-hr-approval",
    response_model=list[TimeSheetListResponse],
    summary="Pendentes aprovação RH",
)
async def get_pending_hr_approval(
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista folhas pendentes de aprovação do RH."""
    repo = TimeSheetRepository(db)

    sheets = await repo.get_pending_hr_approval(condominium_id)

    return sheets


@router.get(
    "/ready-to-close",
    response_model=list[TimeSheetListResponse],
    summary="Prontas para fechamento",
)
async def get_ready_to_close(
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Lista folhas prontas para fechamento."""
    repo = TimeSheetRepository(db)

    sheets = await repo.get_ready_to_close(condominium_id)

    return sheets


@router.get(
    "/{sheet_id}",
    response_model=TimeSheetResponse,
    summary="Buscar folha por ID",
)
async def get_time_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna detalhes completos de uma folha de ponto."""
    repo = TimeSheetRepository(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    return sheet


@router.post(
    "/{sheet_id}/recalculate",
    response_model=TimeSheetResponse,
    summary="Recalcular folha",
)
async def recalculate_time_sheet(
    sheet_id: UUID,
    data: TimeSheetRecalculate = TimeSheetRecalculate(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Recalcula todos os totais da folha de ponto."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    sheet = await service.recalculate_time_sheet(sheet, force=data.force)
    await db.commit()

    return sheet


@router.post(
    "/{sheet_id}/approve/employee",
    response_model=TimeSheetResponse,
    summary="Aprovação do funcionário",
)
async def approve_by_employee(
    sheet_id: UUID,
    data: TimeSheetEmployeeApproval = TimeSheetEmployeeApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Funcionário aprova sua própria folha de ponto."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    # Verifica se é o próprio funcionário
    if sheet.employee_id != getattr(current_user, "id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o próprio funcionário pode aprovar sua folha",
        )

    try:
        sheet = await service.approve_by_employee(sheet, data.notes)
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/{sheet_id}/approve/manager",
    response_model=TimeSheetResponse,
    summary="Aprovação do gestor",
)
async def approve_by_manager(
    sheet_id: UUID,
    data: TimeSheetManagerApproval = TimeSheetManagerApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh", "gestor"])),
):
    """Gestor aprova a folha de ponto."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    try:
        sheet = await service.approve_by_manager(
            sheet,
            manager_id=getattr(current_user, "id", None),
            manager_name=getattr(current_user, "name", ""),
            notes=data.notes,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/{sheet_id}/approve/hr",
    response_model=TimeSheetResponse,
    summary="Aprovação do RH",
)
async def approve_by_hr(
    sheet_id: UUID,
    data: TimeSheetHRApproval = TimeSheetHRApproval(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """RH aprova a folha de ponto."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    try:
        sheet = await service.approve_by_hr(
            sheet,
            hr_id=getattr(current_user, "id", None),
            hr_name=getattr(current_user, "name", ""),
            notes=data.notes,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/{sheet_id}/close",
    response_model=TimeSheetResponse,
    summary="Fechar folha de ponto",
)
async def close_time_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Fecha a folha de ponto após todas as aprovações."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    try:
        sheet = await service.close_time_sheet(
            sheet,
            closed_by_id=getattr(current_user, "id", None),
            closed_by_name=getattr(current_user, "name", ""),
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/{sheet_id}/send-to-payroll",
    response_model=TimeSheetResponse,
    summary="Enviar para folha de pagamento",
)
async def send_to_payroll(
    sheet_id: UUID,
    data: TimeSheetPayroll,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Envia a folha de ponto para o sistema de folha de pagamento."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    try:
        sheet = await service.send_to_payroll(
            sheet,
            payroll_reference=data.payroll_reference,
            batch_id=data.batch_id,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/{sheet_id}/reopen",
    response_model=TimeSheetResponse,
    summary="Reabrir folha de ponto",
)
async def reopen_time_sheet(
    sheet_id: UUID,
    data: TimeSheetReopen,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Reabre uma folha de ponto fechada."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    try:
        sheet = await service.reopen_time_sheet(
            sheet,
            reason=data.reason,
            reopened_by_id=getattr(current_user, "id", None),
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return sheet


@router.post(
    "/batch-action",
    summary="Ação em lote",
)
async def batch_action(
    data: TimeSheetBatchAction,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Executa ação em várias folhas de ponto simultaneamente."""
    repo = TimeSheetRepository(db)
    service = TimeSheetService(db)

    results = {"success": [], "errors": []}

    for sheet_id in data.sheet_ids:
        try:
            sheet = await repo.get_by_id(UUID(sheet_id))
            if not sheet:
                results["errors"].append(
                    {
                        "id": sheet_id,
                        "error": "Folha não encontrada",
                    }
                )
                continue

            if data.action == "close":
                await service.close_time_sheet(
                    sheet,
                    closed_by_id=getattr(current_user, "id", None),
                    closed_by_name=getattr(current_user, "name", ""),
                )
            elif data.action == "send_to_payroll":
                await service.send_to_payroll(
                    sheet,
                    payroll_reference=data.payroll_reference or "",
                )
            elif data.action == "reopen":
                await service.reopen_time_sheet(
                    sheet,
                    reason=data.notes or "Reabertura em lote",
                    reopened_by_id=getattr(current_user, "id", None),
                )

            results["success"].append(sheet_id)

        except Exception as e:  # pylint: disable=broad-exception-caught
            results["errors"].append(
                {
                    "id": sheet_id,
                    "error": str(e),
                }
            )

    await db.commit()

    return results


@router.get(
    "/{sheet_id}/report",
    summary="Gerar relatório da folha",
)
async def get_time_sheet_report(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Gera relatório detalhado da folha de ponto."""
    repo = TimeSheetRepository(db)
    report_service = ReportService(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    report = await report_service.generate_employee_report(
        sheet.employee_id,
        sheet.reference_month,
        sheet.reference_year,
    )

    return report


@router.delete(
    "/{sheet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir folha de ponto",
)
async def delete_time_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin"])),
):
    """Exclui uma folha de ponto (soft delete)."""
    repo = TimeSheetRepository(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    if sheet.status == TimeSheetStatus.ENVIADO_FOLHA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir folha já enviada à folha de pagamento",
        )

    await repo.delete(sheet)
    await db.commit()
