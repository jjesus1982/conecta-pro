"""
My Payslips Controller — Consulta de contracheques do funcionario.

Endpoints:
- GET /portal/my-payslips (historico)
- GET /portal/my-payslips/{month}/{year} (detalhado)
- GET /portal/my-payslips/{month}/{year}/pdf (download PDF)
"""

import io
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId
from modules.people_management.employee_portal.schemas.payslip import MyPayslipResponse
from modules.people_management.employee_portal.services.payslip_portal_service import (
    PayslipPortalService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Contracheques"])


@router.get(
    "/my-payslips",
    response_model=list[MyPayslipResponse],
    summary="Meus contracheques",
    description="Retorna lista de contracheques do funcionario para o ano especificado.",
)
async def get_my_payslips(
    employee_id: CurrentEmployeeId,
    year: int = Query(default=None, ge=2020, le=2030, description="Ano de referencia"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna contracheques do funcionario autenticado."""
    target_year = year or datetime.utcnow().year
    service = PayslipPortalService(db)
    result = await service.get_payslips_list(employee_id=employee_id, year=target_year)
    payslips = result.get("payslips", [])
    return [MyPayslipResponse(**p) for p in payslips]


@router.get(
    "/my-payslips/{month}/{year}",
    response_model=MyPayslipResponse,
    summary="Contracheque especifico",
    description="Retorna o contracheque de um mes/ano especifico.",
)
async def get_payslip_by_month(
    employee_id: CurrentEmployeeId,
    month: int = Path(..., ge=1, le=12, description="Mes (1-12)"),
    year: int = Path(..., ge=2020, le=2030, description="Ano"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna contracheque de um mes/ano especifico."""
    service = PayslipPortalService(db)
    data = await service.get_payslip_detail(employee_id=employee_id, month=month, year=year)
    if not data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Contracheque de {month:02d}/{year} nao encontrado.",
        )
    return MyPayslipResponse(**data)


@router.get(
    "/my-payslips/{month}/{year}/pdf",
    summary="Download PDF do contracheque",
    description="Gera e retorna o contracheque em formato PDF.",
)
async def get_payslip_pdf(
    employee_id: CurrentEmployeeId,
    month: int = Path(..., ge=1, le=12, description="Mes (1-12)"),
    year: int = Path(..., ge=2020, le=2030, description="Ano"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Gera PDF do contracheque de um mes/ano especifico."""
    service = PayslipPortalService(db)
    payslip_data = await service.get_payslip_detail(employee_id=employee_id, month=month, year=year)

    if not payslip_data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Contracheque de {month:02d}/{year} nao encontrado.",
        )

    # Buscar nome do funcionario
    nome = "Funcionario"
    cargo = ""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()
        if emp:
            nome = emp.nome
            cargo = getattr(emp, "cargo", "") or ""
    except ImportError:
        pass

    pdf_bytes = _generate_payslip_pdf(payslip_data, nome, cargo, month, year)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="contracheque_{month:02d}_{year}.pdf"'},
    )


def _generate_payslip_pdf(data: dict, nome: str, cargo: str, month: int, year: int) -> bytes:
    """Gera PDF simples do contracheque.

    Tenta usar reportlab se disponivel, senao retorna texto plano como PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Cabecalho
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "CONTRACHEQUE")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, height - 70, f"Competencia: {month:02d}/{year}")
        pdf.drawString(50, height - 85, "CCT: SINDECOMPRESTS/SINDICOND-AM 2026")

        # Dados do funcionario
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, height - 115, f"Funcionario: {nome}")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, height - 130, f"Cargo: {cargo}")

        # Linha separadora
        pdf.line(50, height - 145, width - 50, height - 145)

        # Itens
        y_pos = height - 170
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y_pos, "Descricao")
        pdf.drawString(300, y_pos, "Tipo")
        pdf.drawString(400, y_pos, "Valor (R$)")
        y_pos -= 20

        pdf.setFont("Helvetica", 10)
        for item in data.get("items", []):
            pdf.drawString(50, y_pos, item.get("description", ""))
            pdf.drawString(300, y_pos, item.get("type", ""))
            valor = item.get("value", 0)
            pdf.drawString(400, y_pos, f"{valor:,.2f}")
            y_pos -= 15

        # Totais
        y_pos -= 10
        pdf.line(50, y_pos, width - 50, y_pos)
        y_pos -= 20
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, y_pos, f"Bruto: R$ {data.get('gross_salary', 0):,.2f}")
        y_pos -= 15
        pdf.drawString(50, y_pos, f"Descontos: R$ {data.get('deductions', 0):,.2f}")
        y_pos -= 15
        pdf.drawString(50, y_pos, f"Liquido: R$ {data.get('net_salary', 0):,.2f}")

        pdf.save()
        return buffer.getvalue()

    except ImportError:
        # Fallback: gerar texto simples
        lines = [
            f"CONTRACHEQUE - {month:02d}/{year}",
            f"Funcionario: {nome}",
            f"Cargo: {cargo}",
            "CCT: SINDECOMPRESTS/SINDICOND-AM 2026",
            "",
            f"Bruto: R$ {data.get('gross_salary', 0):,.2f}",
            f"Descontos: R$ {data.get('deductions', 0):,.2f}",
            f"Liquido: R$ {data.get('net_salary', 0):,.2f}",
        ]
        return "\n".join(lines).encode("utf-8")
