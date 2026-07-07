"""
Controller de Folha de Pagamento — Departamento Pessoal.

Re-exporta endpoints de folha do módulo HR e adiciona endpoints
para cálculo individual, fechamento mensal e contracheque PDF.
"""

import asyncio
import logging
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.publishers import publish_folha_fechada
from modules.people_management.hr.services.payroll_service import PayrollService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payroll", tags=["DP - Folha de Pagamento"])

# Re-export do router existente de payroll
# IMPORTANTE: usar include_router (NÃO append) para preservar prefixos
try:
    from modules.hr.payroll_integration.controllers import router as _payroll_router

    router.include_router(_payroll_router)
except ImportError:
    logger.info("Router de payroll não disponível para re-export")


@router.get(
    "/summary",
    summary="Resumo da folha salarial",
    description=(
        "Retorna totais consolidados da folha para a competência: "
        "proventos, descontos, INSS, IRRF e FGTS. "
        "Usa hr_payslips quando disponível, com fallback em employees.salario_base."
    ),
)
async def get_payroll_summary(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    mes: int = Query(None, ge=1, le=12, description="Mês (1-12). Padrão: mês atual"),
    ano: int = Query(None, ge=2020, le=2030, description="Ano. Padrão: ano atual"),
) -> Any:
    """Resumo consolidado da folha de pagamento."""
    from datetime import datetime

    from sqlalchemy import text as _text

    mes = mes or datetime.now().month
    ano = ano or datetime.now().year

    # Tentar hr_payslips primeiro
    try:
        result = await db.execute(
            _text(
                # [Veracidade] colunas reais de hr_payslips (eram total_proventos/salario_liquido/inss/
                # competencia inexistentes -> caia no except -> fallback com 0s escondendo os 51 holerites reais)
                "SELECT "
                "COUNT(DISTINCT employee_id) as funcionarios, "
                "COALESCE(SUM(total_earnings), 0) as total_proventos, "
                "COALESCE(SUM(total_deductions), 0) as total_descontos, "
                "COALESCE(SUM(net_salary), 0) as total_liquido, "
                "COALESCE(SUM(inss_value), 0) as total_inss, "
                "COALESCE(SUM(irrf_value), 0) as total_irrf, "
                "COALESCE(SUM(fgts_value), 0) as total_fgts "
                "FROM hr_payslips "
                "WHERE reference_month = :mes AND reference_year = :ano"
            ),
            {"mes": mes, "ano": ano},
        )
        row = result.mappings().first()
        if row and float(row.get("total_proventos") or 0) > 0:
            return {
                "competencia": f"{mes:02d}/{ano}",
                "funcionarios": int(row.get("funcionarios") or 0),
                "total_proventos": float(row.get("total_proventos") or 0),
                "total_bruto": float(row.get("total_proventos") or 0),
                "total_descontos": float(row.get("total_descontos") or 0),
                "total_liquido": float(row.get("total_liquido") or 0),
                "total_inss": float(row.get("total_inss") or 0),
                "total_irrf": float(row.get("total_irrf") or 0),
                "total_fgts": float(row.get("total_fgts") or 0),
                "fonte": "hr_payslips",
            }
    except Exception:
        await db.rollback()

    # Fallback: calcular direto dos funcionários ativos
    result2 = await db.execute(
        _text(
            "SELECT "
            "COUNT(*) as funcionarios, "
            "COALESCE(SUM(salario_base), 0) as total_proventos, "
            "0 as total_descontos, "
            "COALESCE(SUM(salario_base), 0) as total_liquido, "
            "0 as total_inss, "
            "0 as total_irrf, "
            "COALESCE(SUM(salario_base * 0.08), 0) as total_fgts "
            "FROM employees "
            "WHERE status = 'ativo'"
        )
    )
    row2 = result2.mappings().first() or {}
    return {
        "competencia": f"{mes:02d}/{ano}",
        "funcionarios": int(row2.get("funcionarios") or 0),
        "total_proventos": float(row2.get("total_proventos") or 0),
        "total_bruto": float(row2.get("total_proventos") or 0),
        "total_descontos": float(row2.get("total_descontos") or 0),
        "total_liquido": float(row2.get("total_liquido") or 0),
        "total_inss": float(row2.get("total_inss") or 0),
        "total_irrf": float(row2.get("total_irrf") or 0),
        "total_fgts": float(row2.get("total_fgts") or 0),
        "fonte": "estimado_salario_base",
    }


@router.get(
    "/employee/{employee_id}/calculate",
    summary="Calcular Folha Individual",
    description="Calcula proventos e descontos da folha de pagamento individual para a competência informada.",
)
async def calculate_employee_payroll(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    month: int = Query(..., ge=1, le=12, description="Mês de referência"),
    year: int = Query(..., ge=2020, le=2030, description="Ano de referência"),
) -> Any:
    """Calcula a folha de pagamento de um funcionário."""
    service = PayrollService(db)
    try:
        return await service.calculate_employee_payroll(employee_id, month, year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/employee/{employee_id}/payslip-pdf",
    summary="Gerar Contracheque PDF",
    description="Gera e retorna contracheque em formato PDF para download.",
)
async def generate_payslip_pdf(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    month: int = Query(..., ge=1, le=12, description="Mes de referencia"),
    year: int = Query(..., ge=2020, le=2030, description="Ano de referencia"),
) -> StreamingResponse:
    """Gera contracheque em PDF para um funcionario e competencia."""
    service = PayrollService(db)
    try:
        calc = await service.calculate_employee_payroll(employee_id, month, year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pdf_bytes = _build_payslip_pdf(calc, month, year)

    filename = f"contracheque_{calc['employee_name'].replace(' ', '_')}_{month:02d}_{year}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _build_payslip_pdf(calc: dict, month: int, year: int) -> bytes:
    """Gera bytes do PDF do contracheque usando ReportLab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=42 * mm, bottomMargin=22 * mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title2", parent=styles["Heading1"], fontSize=14, alignment=1)
    normal = styles["Normal"]
    bold_style = ParagraphStyle("Bold", parent=normal, fontName="Helvetica-Bold", fontSize=9)
    # small style reservado para uso futuro

    elements = []

    # Faixa de competência (a marca e o título "CONTRACHEQUE" vêm do topo via B.header_footer)
    elements.append(Paragraph(f"CONTRACHEQUE — Competencia {month:02d}/{year}", title_style))
    elements.append(Spacer(1, 4 * mm))

    # Dados do funcionario
    emp_data = [
        ["Funcionario:", calc.get("employee_name", ""), "Cargo:", calc.get("cargo", "")],
        ["Matricula:", calc.get("matricula", "-"), "CPF:", calc.get("cpf", "-")],
        ["Admissao:", calc.get("data_admissao", "-"), "Referencia:", calc.get("reference", f"{month:02d}/{year}")],
    ]
    emp_table = Table(emp_data, colWidths=[2.5 * cm, 7 * cm, 2.5 * cm, 6 * cm])
    emp_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(emp_table)
    elements.append(Spacer(1, 4 * mm))

    # Proventos
    proventos = calc.get("proventos", [])
    prov_rows = [["Cod", "Descricao", "Ref", "Valor (R$)"]]
    for p in proventos:
        prov_rows.append([p.get("codigo", ""), p.get("descricao", ""), p.get("ref", ""), f"{p.get('valor', 0):,.2f}"])
    prov_rows.append(["", "", "TOTAL PROVENTOS", f"{calc.get('total_proventos', 0):,.2f}"])

    prov_table = Table(prov_rows, colWidths=[1.5 * cm, 8 * cm, 3 * cm, 3.5 * cm])
    prov_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
                ("FONTNAME", (2, -1), (3, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(Paragraph("<b>PROVENTOS</b>", bold_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(prov_table)
    elements.append(Spacer(1, 4 * mm))

    # Descontos
    descontos = calc.get("descontos", [])
    desc_rows = [["Cod", "Descricao", "Ref", "Valor (R$)"]]
    for d in descontos:
        desc_rows.append([d.get("codigo", ""), d.get("descricao", ""), d.get("ref", ""), f"{d.get('valor', 0):,.2f}"])
    desc_rows.append(["", "", "TOTAL DESCONTOS", f"{calc.get('total_descontos', 0):,.2f}"])

    desc_table = Table(desc_rows, colWidths=[1.5 * cm, 8 * cm, 3 * cm, 3.5 * cm])
    desc_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DC2626")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF2F2")),
                ("FONTNAME", (2, -1), (3, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(Paragraph("<b>DESCONTOS</b>", bold_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(desc_table)
    elements.append(Spacer(1, 6 * mm))

    # Resumo
    resumo_data = [
        ["SALARIO LIQUIDO", f"R$ {calc.get('salario_liquido', 0):,.2f}"],
        ["Base INSS", f"R$ {calc.get('base_inss', 0):,.2f}"],
        ["Base IRRF", f"R$ {calc.get('base_irrf', 0):,.2f}"],
        ["FGTS 8%", f"R$ {calc.get('fgts_8_pct', 0):,.2f}"],
    ]
    resumo_table = Table(resumo_data, colWidths=[10 * cm, 6 * cm])
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16A34A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(resumo_table)
    elements.append(Spacer(1, 10 * mm))

    # Rodape
    elements.append(
        Paragraph(
            "Documento gerado pelo Conecta PRO — Sistema ERP para Gestao de Vigilancia e Seguranca Patrimonial",
            ParagraphStyle("Footer", parent=normal, fontSize=7, textColor=colors.gray, alignment=1),
        )
    )

    doc.build(
        elements,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
    )
    return buffer.getvalue()


# =============================================================================
# RUBRICAS (BENEFITS) POR FUNCIONÁRIO
# =============================================================================


@router.get(
    "/benefits",
    summary="Listar Benefícios/Rubricas",
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def list_all_benefits(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None, description="Filtrar por funcionário"),
    status: str = Query("active", description="Status: active, inactive"),
) -> Any:
    """Lista rubricas/benefícios cadastrados por funcionário."""
    from sqlalchemy import text

    sql = "SELECT b.*, e.nome as employee_name FROM employee_benefits b JOIN employees e ON b.employee_id = e.id WHERE b.status = :status"
    params: dict = {"status": status}
    if employee_id:
        sql += " AND b.employee_id = :emp_id"
        params["emp_id"] = employee_id
    sql += " ORDER BY e.nome, b.type"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r.id),
                "employee_id": str(r.employee_id),
                "employee_name": r.employee_name,
                "type": r.type,
                "provider": r.provider,
                "plan_name": r.plan_name,
                "employee_contribution": float(r.employee_contribution or 0),
                "company_contribution": float(r.company_contribution or 0),
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "status": r.status,
                "notes": r.notes,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post(
    "/benefits",
    summary="Cadastrar Benefício",
    status_code=201,
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def create_benefit(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str = Query(..., description="ID do funcionário"),
    benefit_type: str = Query(
        ...,
        alias="type",
        description="Tipo: Emprestimo Consignado, Pensao Alimenticia, Vale Refeicao, Plano Saude, etc",
    ),
    employee_contribution: float = Query(0, description="Valor desconto do funcionário"),
    company_contribution: float = Query(0, description="Valor da empresa"),
    provider: str = Query("", description="Fornecedor/banco"),
    plan_name: str = Query("", description="Nome do plano/descrição"),
    notes: str = Query("", description="Observações"),
) -> Any:
    """Cadastra nova rubrica/benefício para um funcionário."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            "INSERT INTO employee_benefits (employee_id, type, provider, plan_name, employee_contribution, company_contribution, notes, status) "
            "VALUES (:emp_id, :type, :provider, :plan, :emp_val, :co_val, :notes, 'active') RETURNING id"
        ),
        {
            "emp_id": employee_id,
            "type": benefit_type,
            "provider": provider or None,
            "plan": plan_name or None,
            "emp_val": employee_contribution,
            "co_val": company_contribution,
            "notes": notes or None,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": str(new_id), "message": f"Rubrica '{benefit_type}' cadastrada para funcionário {employee_id}"}


@router.delete(
    "/benefits/{benefit_id}",
    summary="Desativar Benefício",
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def delete_benefit(
    benefit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Desativa uma rubrica/benefício."""
    from sqlalchemy import text

    await db.execute(
        text("UPDATE employee_benefits SET status = 'inactive', updated_at = now() WHERE id = :id"),
        {"id": benefit_id},
    )
    await db.commit()
    return {"message": "Rubrica desativada"}


@router.get(
    "/rubricas",
    summary="Listar Rubricas de Referência",
    description="Lista rubricas disponíveis na tabela de referência para cálculo de folha.",
)
async def list_rubricas(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista rubricas disponíveis (tabela de referência)."""
    from sqlalchemy import text

    result = await db.execute(text("SELECT * FROM rubricas_folha WHERE ativo ORDER BY codigo"))
    rows = result.fetchall()
    return {
        "items": [
            {
                "id": r.id,
                "codigo": r.codigo,
                "descricao": r.descricao,
                "tipo": r.tipo,
                "valor_fixo": float(r.valor_fixo) if r.valor_fixo else None,
                "percentual": float(r.percentual) if r.percentual else None,
                "incide_inss": r.incide_inss,
                "incide_irrf": r.incide_irrf,
                "incide_fgts": r.incide_fgts,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post(
    "/close",
    summary="Fechar Folha Mensal",
    status_code=201,
    description="Fecha e processa a folha de pagamento mensal para todos os funcionários ativos.",
)
async def close_payroll(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    month: int = Query(..., ge=1, le=12, description="Mês de referência"),
    year: int = Query(..., ge=2020, le=2030, description="Ano de referência"),
) -> Any:
    """Fecha a folha de pagamento mensal para todos os funcionários ativos."""
    service = PayrollService(db)
    result = await service.close_payroll(month, year)
    await db.commit()
    asyncio.create_task(
        publish_folha_fechada(
            competencia=f"{month:02d}/{year}",
            total_funcionarios=result.get("total_funcionarios", 0) if isinstance(result, dict) else 0,
            total_bruto=float(result.get("total_bruto", 0.0)) if isinstance(result, dict) else 0.0,
        )
    )
    return result
