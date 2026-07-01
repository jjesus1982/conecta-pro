"""Service para contracheques/holerites."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.employee_portal.models import PaySlip, PaySlipStatus, PaySlipType
from modules.hr.employee_portal.repositories import PaySlipRepository
from modules.hr.employee_portal.schemas import (
    PaySlipCreate,
    PaySlipDeductionItem,
    PaySlipEarningItem,
)

logger = logging.getLogger(__name__)


def _payslip_brand_page(canvas, doc):
    """Marca Conecta Mais (logo + linha no topo, rodapé oficial) em todas as páginas do holerite."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    from modules.crm.services import pdf_branding as B

    canvas.saveState()
    w, h = A4
    lp = B.logo_path("header")
    drew = False
    if lp:
        try:
            canvas.drawImage(
                lp, 15 * mm, h - 20 * mm, width=50 * mm, height=12 * mm,
                preserveAspectRatio=True, anchor="sw", mask="auto",
            )
            drew = True
        except Exception:  # noqa: BLE001
            pass
    if not drew:
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(B.AZUL_ESCURO)
        canvas.drawString(15 * mm, h - 15 * mm, B.EMPRESA["nome"])
    canvas.setStrokeColor(B.LARANJA)
    canvas.setLineWidth(1.2)
    canvas.line(15 * mm, h - 22 * mm, w - 15 * mm, h - 22 * mm)
    canvas.setStrokeColor(B.AZUL_ESCURO)
    canvas.setLineWidth(0.6)
    canvas.line(15 * mm, 14 * mm, w - 15 * mm, 14 * mm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(B.AZUL_MEDIO)
    canvas.drawString(
        15 * mm, 10 * mm, f"{B.EMPRESA['nome']} | CNPJ: {B.EMPRESA['cnpj']} | {B.EMPRESA['fone']} | {B.EMPRESA['site']}"
    )
    canvas.drawRightString(w - 15 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


class PaySlipService:
    """Service para operações de contracheques."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PaySlipRepository(db)

    async def create_payslip(
        self,
        data: PaySlipCreate,
        condominio_id: UUID,
        *,
        created_by: UUID | None = None,
    ) -> PaySlip:
        """Cria novo contracheque."""
        return await self.repo.create(data, condominio_id, created_by=created_by)

    async def get_payslip(self, payslip_id: UUID) -> PaySlip | None:
        """Busca contracheque por ID."""
        return await self.repo.get_by_id(payslip_id)

    async def list_employee_payslips(
        self,
        employee_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        year: int | None = None,
        payslip_type: PaySlipType | None = None,
    ) -> tuple[list[PaySlip], int]:
        """Lista contracheques do funcionário."""
        return await self.repo.list_by_employee(
            employee_id,
            page=page,
            page_size=page_size,
            year=year,
            payslip_type=payslip_type,
            only_viewable=True,
        )

    async def view_payslip(
        self,
        payslip_id: UUID,
        employee_id: UUID,
    ) -> PaySlip | None:
        """Visualiza contracheque (registra view)."""
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip or payslip.employee_id != employee_id:
            return None

        if not payslip.is_viewable:
            raise ValueError("Contracheque não disponível para visualização")

        return await self.repo.record_view(payslip_id)

    async def download_payslip(
        self,
        payslip_id: UUID,
        employee_id: UUID,
    ) -> PaySlip | None:
        """Download do contracheque (registra download)."""
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip or payslip.employee_id != employee_id:
            return None

        if not payslip.is_viewable:
            raise ValueError("Contracheque não disponível para download")

        return await self.repo.record_download(payslip_id)

    async def acknowledge_payslip(
        self,
        payslip_id: UUID,
        employee_id: UUID,
    ) -> PaySlip | None:
        """Registra ciência no contracheque."""
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip or payslip.employee_id != employee_id:
            return None

        return await self.repo.acknowledge(payslip_id)

    async def contest_payslip(
        self,
        payslip_id: UUID,
        employee_id: UUID,
        reason: str,
    ) -> PaySlip | None:
        """Contesta contracheque."""
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip or payslip.employee_id != employee_id:
            return None

        return await self.repo.contest(payslip_id, reason)

    async def get_employee_summary(
        self,
        employee_id: UUID,
    ) -> dict:
        """Retorna resumo de contracheques do funcionário."""
        unread_count = await self.repo.get_unread_count(employee_id)
        pending_ack = await self.repo.get_pending_ack_count(employee_id)
        years = await self.repo.get_years_available(employee_id)

        # Buscar último contracheque
        payslips, _ = await self.repo.list_by_employee(
            employee_id,
            page=1,
            page_size=1,
            only_viewable=True,
        )

        last_payslip = None
        if payslips:
            ps = payslips[0]
            last_payslip = {
                "id": str(ps.id),
                "reference_period": ps.reference_period,
                "net_salary": float(ps.net_salary),
                "payment_date": ps.payment_date.isoformat() if ps.payment_date else None,
            }

        return {
            "unread_count": unread_count,
            "pending_acknowledgement": pending_ack,
            "available_years": years,
            "last_payslip": last_payslip,
        }

    async def generate_pdf(
        self,
        payslip_id: UUID,
    ) -> str | None:
        """Gera PDF do contracheque com ReportLab."""
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip:
            return None

        from pathlib import Path

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        # Diretório de saída
        out_dir = Path(f"/app/uploads/payslips/{payslip.condominio_id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = out_dir / f"{payslip.payslip_code}.pdf"

        styles = getSampleStyleSheet()
        title_s = ParagraphStyle("T", parent=styles["Title"], fontSize=14, spaceAfter=2 * mm)
        normal_s = ParagraphStyle("N", parent=styles["Normal"], fontSize=8, leading=10)
        bold_s = ParagraphStyle("B", parent=normal_s, fontName="Helvetica-Bold")
        small_s = ParagraphStyle("S", parent=normal_s, fontSize=7, textColor=colors.grey)

        doc = SimpleDocTemplate(
            str(pdf_file),
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=2.7 * cm,
            bottomMargin=1.8 * cm,
        )
        story = []

        # Faixa de título (a marca Conecta Mais é desenhada no topo por _payslip_brand_page)
        story.append(Paragraph(f"CONTRACHEQUE — {payslip.payslip_code}", title_s))
        story.append(Spacer(1, 5 * mm))

        # Dados do funcionário
        emp_data = [
            [
                "Funcionário",
                str(getattr(payslip, "employee_name", "") or "—"),
                "Matrícula",
                str(getattr(payslip, "employee_matricula", "") or "—"),
            ],
            [
                "Cargo",
                str(getattr(payslip, "employee_cargo", "") or "—"),
                "Departamento",
                str(getattr(payslip, "employee_departamento", "") or "—"),
            ],
            [
                "Competência",
                str(payslip.payslip_code or ""),
                "Tipo",
                str(getattr(payslip, "payslip_type", "") or "MENSAL"),
            ],
        ]
        emp_table = Table(emp_data, colWidths=[2.5 * cm, 6.5 * cm, 2.5 * cm, 6.5 * cm])
        emp_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f0f0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(emp_table)
        story.append(Spacer(1, 5 * mm))

        # Proventos e descontos
        earnings = getattr(payslip, "earnings", []) or []
        deductions = getattr(payslip, "deductions", []) or []

        prov_header = [
            Paragraph("<b>Código</b>", small_s),
            Paragraph("<b>Descrição</b>", small_s),
            Paragraph("<b>Ref.</b>", small_s),
            Paragraph("<b>Valor (R$)</b>", small_s),
        ]
        prov_rows = [prov_header]
        total_prov = 0
        for e in earnings if isinstance(earnings, list) else []:
            val = float(e.get("value", 0) if isinstance(e, dict) else getattr(e, "value", 0))
            total_prov += val
            prov_rows.append(
                [
                    str(e.get("code", "") if isinstance(e, dict) else getattr(e, "code", "")),
                    str(e.get("description", "") if isinstance(e, dict) else getattr(e, "description", "")),
                    str(e.get("reference", "") if isinstance(e, dict) else getattr(e, "reference", "")),
                    f"{val:,.2f}",
                ]
            )
        prov_rows.append(["", Paragraph("<b>TOTAL PROVENTOS</b>", bold_s), "", f"{total_prov:,.2f}"])

        desc_header = [
            Paragraph("<b>Código</b>", small_s),
            Paragraph("<b>Descrição</b>", small_s),
            Paragraph("<b>Ref.</b>", small_s),
            Paragraph("<b>Valor (R$)</b>", small_s),
        ]
        desc_rows = [desc_header]
        total_desc = 0
        for d in deductions if isinstance(deductions, list) else []:
            val = float(d.get("value", 0) if isinstance(d, dict) else getattr(d, "value", 0))
            total_desc += val
            desc_rows.append(
                [
                    str(d.get("code", "") if isinstance(d, dict) else getattr(d, "code", "")),
                    str(d.get("description", "") if isinstance(d, dict) else getattr(d, "description", "")),
                    str(d.get("reference", "") if isinstance(d, dict) else getattr(d, "reference", "")),
                    f"{val:,.2f}",
                ]
            )
        desc_rows.append(["", Paragraph("<b>TOTAL DESCONTOS</b>", bold_s), "", f"{total_desc:,.2f}"])

        col_w = [2 * cm, 8.5 * cm, 2 * cm, 3 * cm]
        tbl_style = TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )

        story.append(Paragraph("<b>PROVENTOS</b>", bold_s))
        t1 = Table(prov_rows, colWidths=col_w)
        t1.setStyle(tbl_style)
        story.append(t1)
        story.append(Spacer(1, 3 * mm))

        story.append(Paragraph("<b>DESCONTOS</b>", bold_s))
        t2 = Table(desc_rows, colWidths=col_w)
        t2.setStyle(tbl_style)
        story.append(t2)
        story.append(Spacer(1, 5 * mm))

        # Líquido
        liquido = total_prov - total_desc
        liq_data = [
            [
                "SALÁRIO BRUTO",
                f"R$ {total_prov:,.2f}",
                "DESCONTOS",
                f"R$ {total_desc:,.2f}",
                "LÍQUIDO",
                f"R$ {liquido:,.2f}",
            ]
        ]
        liq_table = Table(liq_data, colWidths=[2.5 * cm, 3.5 * cm, 2.5 * cm, 3.5 * cm, 2.5 * cm, 3.5 * cm])
        liq_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (4, 0), (5, 0), colors.HexColor("#c6f6d5")),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                    ("ALIGN", (5, 0), (5, 0), "RIGHT"),
                ]
            )
        )
        story.append(liq_table)
        story.append(Spacer(1, 1 * cm))

        # Rodapé
        story.append(Paragraph("_" * 50, normal_s))
        story.append(Paragraph("Assinatura do Funcionário", small_s))
        story.append(Spacer(1, 5 * mm))
        story.append(
            Paragraph(
                f"Documento gerado eletronicamente pelo Conecta PRO em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                small_s,
            )
        )

        doc.build(story, onFirstPage=_payslip_brand_page, onLaterPages=_payslip_brand_page)

        pdf_path = str(pdf_file)
        payslip.pdf_path = pdf_path
        payslip.pdf_generated_at = datetime.utcnow()
        await self.db.commit()

        logger.info("PDF gerado para contracheque %s em %s", payslip_id, pdf_path)
        return pdf_path

    async def publish_payslip(
        self,
        payslip_id: UUID,
        *,
        published_by: UUID | None = None,
    ) -> PaySlip | None:
        """Publica contracheque (visível para funcionário)."""
        return await self.repo.publish(payslip_id, published_by=published_by)

    async def bulk_publish(
        self,
        condominio_id: UUID,
        year: int,
        month: int,
        *,
        published_by: UUID | None = None,
    ) -> int:
        """Publica contracheques em lote."""
        payslips, _ = await self.repo.list_by_condominio(
            condominio_id,
            status=PaySlipStatus.GENERATED,
            year=year,
            month=month,
            page_size=1000,
        )

        count = 0
        for payslip in payslips:
            if payslip.status == PaySlipStatus.GENERATED.value:
                await self.repo.publish(payslip.id, published_by=published_by)
                count += 1

        logger.info("Publicados %d contracheques de %02d/%d", count, month, year)
        return count

    def calculate_totals(
        self,
        earnings: list[PaySlipEarningItem],
        deductions: list[PaySlipDeductionItem],
    ) -> dict:
        """Calcula totais do contracheque."""
        total_earnings = sum(e.value for e in earnings)
        total_deductions = sum(d.value for d in deductions)
        net_salary = total_earnings - total_deductions

        return {
            "total_earnings": total_earnings,
            "total_deductions": total_deductions,
            "net_salary": net_salary,
        }
