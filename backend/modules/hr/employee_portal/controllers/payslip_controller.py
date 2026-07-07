"""Controller para contracheques/holerites."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_async_session
from modules.hr.employee_portal.models import PaySlipType
from modules.hr.employee_portal.schemas import (
    PaySlipListResponse,
    PaySlipResponse,
    PaySlipSummary,
)
from modules.hr.employee_portal.services import PaySlipService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payslips", tags=["Portal - Contracheques"])


@router.get(
    "/",
    response_model=PaySlipListResponse,
    summary="Listar contracheques",
)
async def list_payslips(
    year: int | None = Query(None, description="Filtrar por ano"),
    payslip_type: PaySlipType | None = Query(None, description="Tipo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Lista contracheques do funcionário logado."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    payslips, total = await service.list_employee_payslips(
        employee_id,
        page=page,
        page_size=page_size,
        year=year,
        payslip_type=payslip_type,
    )

    return PaySlipListResponse(
        items=[PaySlipSummary.model_validate(p) for p in payslips],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/summary",
    summary="Resumo de contracheques",
)
async def get_payslips_summary(
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Retorna resumo de contracheques do funcionário."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    return await service.get_employee_summary(employee_id)


@router.get(
    "/{payslip_id}",
    response_model=PaySlipResponse,
    summary="Visualizar contracheque",
)
async def view_payslip(
    payslip_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Visualiza contracheque específico (registra visualização)."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    payslip = await service.view_payslip(payslip_id, employee_id)
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contracheque não encontrado",
        )

    return PaySlipResponse.model_validate(payslip)


@router.get(
    "/{payslip_id}/download",
    summary="Download do contracheque",
)
async def download_payslip(
    payslip_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Download do PDF do contracheque."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    payslip = await service.download_payslip(payslip_id, employee_id)
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contracheque não encontrado",
        )

    # Sempre (re)gera no padrão-ouro atual — evita servir PDF antigo em cache.
    pdf_path = await service.generate_pdf(payslip_id)
    if not pdf_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar PDF",
        )

    return FileResponse(
        path=pdf_path,
        filename=f"contracheque_{payslip.payslip_code}.pdf",
        media_type="application/pdf",
    )


@router.post("/{payslip_id}/acknowledge", response_model=PaySlipResponse, summary="Dar ciência no contracheque")
async def acknowledge_payslip(
    payslip_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Registra ciência no contracheque."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    payslip = await service.acknowledge_payslip(payslip_id, employee_id)
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contracheque não encontrado",
        )

    return PaySlipResponse.model_validate(payslip)


@router.post("/{payslip_id}/contest", response_model=PaySlipResponse, summary="Contestar contracheque")
async def contest_payslip(
    payslip_id: UUID,
    reason: str = Query(..., min_length=10, max_length=1000),
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Contesta valores do contracheque."""
    service = PaySlipService(db)
    employee_id = UUID(current_user["employee_id"])

    try:
        payslip = await service.contest_payslip(payslip_id, employee_id, reason)
        if not payslip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contracheque não encontrado",
            )
        return PaySlipResponse.model_validate(payslip)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# --- Endpoints administrativos ---


@router.post(
    "/{payslip_id}/publish",
    response_model=PaySlipResponse,
    summary="Publicar contracheque",
    dependencies=[Depends(require_roles(["admin", "hr"]))],
)
async def publish_payslip(
    payslip_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Publica contracheque para visualização do funcionário."""
    service = PaySlipService(db)

    payslip = await service.publish_payslip(
        payslip_id,
        published_by=UUID(current_user["sub"]),
    )

    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contracheque não encontrado",
        )

    return PaySlipResponse.model_validate(payslip)


@router.post(
    "/bulk-publish",
    summary="Publicar contracheques em lote",
    dependencies=[Depends(require_roles(["admin", "hr"]))],
)
async def bulk_publish_payslips(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """Publica todos os contracheques de um período."""
    service = PaySlipService(db)
    condominio_id = UUID(current_user["condominio_id"])

    count = await service.bulk_publish(
        condominio_id,
        year,
        month,
        published_by=UUID(current_user["sub"]),
    )

    return {
        "message": f"Publicados {count} contracheques",
        "count": count,
        "period": f"{month:02d}/{year}",
    }
