"""
Controller para o módulo de Relatórios Gerenciais
Sprint 34: Relatórios Gerenciais
"""
# pylint: disable=unused-argument,too-many-locals,redefined-outer-name

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.reports.schemas import (
    BenchmarkCompanyValue,
    BenchmarkCreate,
    BenchmarkList,
    BenchmarkResponse,
    BenchmarkUpdate,
    ExecutiveDashboard,
    ExecutiveKPICreate,
    ExecutiveKPIList,
    ExecutiveKPIResponse,
    ExecutiveKPIUpdate,
    ExecutiveKPIValueUpdate,
    KPIDashboard,
    ReportExportCreate,
    ReportExportDownload,
    ReportExportList,
    ReportExportResponse,
    ReportScheduleCreate,
    ReportScheduleList,
    ReportScheduleResponse,
    ReportScheduleUpdate,
    ReportsDashboard,
    ReportTemplateCreate,
    ReportTemplateList,
    ReportTemplateResponse,
    ReportTemplateUpdate,
)
from modules.reports.services import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])


def get_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    """Retorna instância do serviço."""
    return ReportService(db)


def get_tenant_id() -> UUID:
    """Retorna tenant ID (mock para desenvolvimento)."""
    return UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


# ========================
# ReportTemplate Endpoints
# ========================


@router.post("/templates", response_model=ReportTemplateResponse, status_code=201)
async def create_template(
    data: ReportTemplateCreate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cria um template de relatório."""
    template = await service.create_template(tenant_id, data)
    return template


@router.get("/templates", response_model=ReportTemplateList)
async def list_templates(
    current_user: CurrentActiveUser,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Lista templates de relatório."""
    templates, total = await service.list_templates(tenant_id, category, status, search, page, page_size)
    return ReportTemplateList(
        items=templates, total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size
    )


@router.get("/templates/{template_id}", response_model=ReportTemplateResponse)
async def get_template(
    template_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Busca template por ID."""
    template = await service.get_template(tenant_id, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return template


@router.put("/templates/{template_id}", response_model=ReportTemplateResponse)
async def update_template(
    template_id: UUID,
    data: ReportTemplateUpdate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza um template."""
    template = await service.update_template(tenant_id, template_id, data)
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return template


@router.post("/templates/{template_id}/activate", response_model=ReportTemplateResponse)
async def activate_template(
    template_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Ativa um template."""
    template = await service.activate_template(tenant_id, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return template


@router.post("/templates/{template_id}/deactivate", response_model=ReportTemplateResponse)
async def deactivate_template(
    template_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Desativa um template."""
    template = await service.deactivate_template(tenant_id, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Remove um template."""
    success = await service.delete_template(tenant_id, template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template não encontrado")


# ========================
# ReportSchedule Endpoints
# ========================


@router.post("/schedules", response_model=ReportScheduleResponse, status_code=201)
async def create_schedule(
    data: ReportScheduleCreate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cria um agendamento de relatório."""
    schedule = await service.create_schedule(tenant_id, data)
    return schedule


@router.get("/schedules", response_model=ReportScheduleList)
async def list_schedules(
    current_user: CurrentActiveUser,
    template_id: UUID | None = None,
    schedule_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Lista agendamentos."""
    schedules, total = await service.list_schedules(tenant_id, template_id, schedule_status, page, page_size)
    return ReportScheduleList(
        items=schedules, total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size
    )


@router.get("/schedules/{schedule_id}", response_model=ReportScheduleResponse)
async def get_schedule(
    schedule_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Busca agendamento por ID."""
    schedule = await service.get_schedule(tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return schedule


@router.put("/schedules/{schedule_id}", response_model=ReportScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    data: ReportScheduleUpdate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza um agendamento."""
    schedule = await service.update_schedule(tenant_id, schedule_id, data)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return schedule


@router.post("/schedules/{schedule_id}/pause", response_model=ReportScheduleResponse)
async def pause_schedule(
    schedule_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Pausa um agendamento."""
    schedule = await service.pause_schedule(tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return schedule


@router.post("/schedules/{schedule_id}/resume", response_model=ReportScheduleResponse)
async def resume_schedule(
    schedule_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Retoma um agendamento."""
    schedule = await service.resume_schedule(tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return schedule


@router.post("/schedules/{schedule_id}/cancel", response_model=ReportScheduleResponse)
async def cancel_schedule(
    schedule_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cancela um agendamento."""
    schedule = await service.cancel_schedule(tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return schedule


# ========================
# ReportExport Endpoints
# ========================


@router.post("/exports", response_model=ReportExportResponse, status_code=201)
async def create_export(
    data: ReportExportCreate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cria uma exportação de relatório."""
    export = await service.create_export(tenant_id, data)
    return export


@router.get("/exports", response_model=ReportExportList)
async def list_exports(
    current_user: CurrentActiveUser,
    template_id: UUID | None = None,
    schedule_id: UUID | None = None,
    export_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Lista exportações."""
    exports, total = await service.list_exports(
        tenant_id, template_id, schedule_id, export_status, None, None, page, page_size
    )
    return ReportExportList(
        items=exports, total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size
    )


@router.get("/exports/{export_id}", response_model=ReportExportResponse)
async def get_export(
    export_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Busca exportação por ID."""
    export = await service.get_export(tenant_id, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Exportação não encontrada")
    return export


@router.get("/exports/download/{token}", response_model=ReportExportDownload)
async def get_download_info(token: str, current_user: CurrentActiveUser, service: ReportService = Depends(get_service)):
    """Retorna informações para download."""
    export = await service.get_export_by_token(token)
    if not export:
        raise HTTPException(status_code=404, detail="Token inválido")
    if not export.is_downloadable:
        raise HTTPException(status_code=410, detail="Exportação expirada ou indisponível")

    return ReportExportDownload(
        download_url=export.download_url or f"/files/{export.file_path}",
        filename=export.file_name or f"report_{export.export_id}.{export.format.value}",
        content_type=export.mime_type or "application/octet-stream",
        file_size=export.file_size or 0,
        expires_at=export.expires_at,
    )


@router.post("/exports/download/{token}/record")
async def record_download(token: str, current_user: CurrentActiveUser, service: ReportService = Depends(get_service)):
    """Registra um download."""
    success = await service.record_download(token)
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível registrar o download")
    return {"status": "recorded"}


# ========================
# ExecutiveKPI Endpoints
# ========================


@router.post("/kpis", response_model=ExecutiveKPIResponse, status_code=201)
async def create_kpi(
    data: ExecutiveKPICreate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cria um KPI executivo."""
    kpi = await service.create_kpi(tenant_id, data)
    return kpi


@router.get("/kpis", response_model=ExecutiveKPIList)
async def list_kpis(
    current_user: CurrentActiveUser,
    category: str | None = None,
    kpi_status: str | None = Query(None, alias="status"),
    alert_level: str | None = None,
    visible_on_dashboard: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Lista KPIs."""
    kpis, total = await service.list_kpis(
        tenant_id, category, kpi_status, alert_level, visible_on_dashboard, page, page_size
    )
    return ExecutiveKPIList(
        items=kpis, total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size
    )


@router.get("/kpis/dashboard", response_model=KPIDashboard)
async def get_kpi_dashboard(
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Retorna dashboard de KPIs."""
    kpis = await service.get_dashboard_kpis(tenant_id)
    attention = await service.get_kpis_needing_attention(tenant_id)

    return KPIDashboard(
        kpis=kpis,
        summary={
            "total": len(kpis),
            "on_target": sum(1 for k in kpis if k.is_on_target),
            "improving": sum(1 for k in kpis if k.is_improving),
            "needs_attention": len(attention),
        },
        alerts=[{"kpi_id": str(k.id), "name": k.name, "level": k.alert_level.value} for k in attention],
        trends={},
    )


@router.get("/kpis/{kpi_id}", response_model=ExecutiveKPIResponse)
async def get_kpi(
    kpi_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Busca KPI por ID."""
    kpi = await service.get_kpi(tenant_id, kpi_id)
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI não encontrado")
    return kpi


@router.put("/kpis/{kpi_id}", response_model=ExecutiveKPIResponse)
async def update_kpi(
    kpi_id: UUID,
    data: ExecutiveKPIUpdate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza um KPI."""
    kpi = await service.update_kpi(tenant_id, kpi_id, data)
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI não encontrado")
    return kpi


@router.post("/kpis/{kpi_id}/value", response_model=ExecutiveKPIResponse)
async def update_kpi_value(
    kpi_id: UUID,
    data: ExecutiveKPIValueUpdate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza valor do KPI."""
    kpi = await service.update_kpi_value(tenant_id, kpi_id, data)
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI não encontrado")
    return kpi


# ========================
# Benchmark Endpoints
# ========================


@router.post("/benchmarks", response_model=BenchmarkResponse, status_code=201)
async def create_benchmark(
    data: BenchmarkCreate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Cria um benchmark."""
    benchmark = await service.create_benchmark(tenant_id, data)
    return benchmark


@router.get("/benchmarks", response_model=BenchmarkList)
async def list_benchmarks(
    current_user: CurrentActiveUser,
    category: str | None = None,
    benchmark_type: str | None = None,
    industry: str | None = None,
    benchmark_status: str | None = Query(None, alias="status"),
    visible_on_dashboard: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Lista benchmarks."""
    benchmarks, total = await service.list_benchmarks(
        tenant_id, category, benchmark_type, industry, benchmark_status, visible_on_dashboard, page, page_size
    )
    return BenchmarkList(
        items=benchmarks, total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size
    )


@router.get("/benchmarks/{benchmark_id}", response_model=BenchmarkResponse)
async def get_benchmark(
    benchmark_id: UUID,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Busca benchmark por ID."""
    benchmark = await service.get_benchmark(tenant_id, benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark não encontrado")
    return benchmark


@router.put("/benchmarks/{benchmark_id}", response_model=BenchmarkResponse)
async def update_benchmark(
    benchmark_id: UUID,
    data: BenchmarkUpdate,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza um benchmark."""
    benchmark = await service.update_benchmark(tenant_id, benchmark_id, data)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark não encontrado")
    return benchmark


@router.post("/benchmarks/{benchmark_id}/company-value", response_model=BenchmarkResponse)
async def update_company_value(
    benchmark_id: UUID,
    data: BenchmarkCompanyValue,
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Atualiza valor da empresa no benchmark."""
    benchmark = await service.update_company_value(tenant_id, benchmark_id, data)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark não encontrado")
    return benchmark


# ========================
# Dashboard Endpoints
# ========================


@router.get("/dashboard", response_model=ReportsDashboard)
async def get_reports_dashboard(
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Retorna dashboard de relatórios."""
    return await service.get_reports_dashboard(tenant_id)


@router.get("/executive-dashboard", response_model=ExecutiveDashboard)
async def get_executive_dashboard(
    current_user: CurrentActiveUser,
    service: ReportService = Depends(get_service),
    tenant_id: UUID = Depends(get_tenant_id),
):
    """Retorna dashboard executivo."""
    return await service.get_executive_dashboard(tenant_id)
