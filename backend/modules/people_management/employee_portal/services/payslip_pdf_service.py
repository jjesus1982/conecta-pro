"""
Serviço de geração de PDF de Holerite/Contracheque.

Usa reportlab para gerar PDF profissional com layout CLT padrão.
"""

import io
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

EMPRESA = {
    "nome": "CONECTA MAIS SEGURANÇA E TECNOLOGIA LTDA",
    "cnpj": "35.710.481/0001-03",
    "endereco": "Manaus - AM",
}


async def gerar_pdf_holerite(db: AsyncSession, payslip_id: UUID) -> bytes:
    """Gera PDF do holerite/contracheque via reportlab.

    Args:
        db: Sessão assíncrona do banco.
        payslip_id: UUID do contracheque.

    Returns:
        Bytes do PDF gerado.

    Raises:
        ValueError: Se contracheque não encontrado.
    """
    from modules.hr.employee_portal.models.payslip import PaySlip

    # 1. Buscar holerite
    result = await db.execute(select(PaySlip).where(PaySlip.id == payslip_id))
    payslip = result.scalar_one_or_none()
    if not payslip:
        raise ValueError(f"Contracheque {payslip_id} não encontrado")

    # 2. Buscar dados do funcionário (best-effort)
    employee_data = await _get_employee_data(db, payslip.employee_id)

    # 3. Gerar PDF
    return _render_pdf(payslip, employee_data)


async def _get_employee_data(db: AsyncSession, employee_id: UUID) -> dict:
    """Tenta buscar dados do funcionário. Retorna dict vazio se falhar."""
    try:
        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == str(employee_id)))
        emp = result.scalar_one_or_none()
        if emp:
            return {
                "nome": getattr(emp, "nome", "") or "",
                "cpf": getattr(emp, "cpf", "") or "",
                "cargo": getattr(emp, "cargo", "") or "",
                "departamento": getattr(emp, "departamento", "") or "",
                "data_admissao": getattr(emp, "data_admissao", None),
                "matricula": getattr(emp, "matricula", "") or str(employee_id)[:8],
            }
    except Exception as exc:
        logger.debug("Falha ao buscar employee para PDF: %s", exc)
    return {
        "nome": "Funcionário",
        "cpf": "",
        "cargo": "",
        "departamento": "",
        "data_admissao": None,
        "matricula": str(employee_id)[:8],
    }


def _brand_page(canvas, doc):
    """Desenha a marca Conecta Mais (logo + linha no topo, rodapé oficial) em TODAS as páginas."""
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
                lp,
                15 * mm,
                h - 20 * mm,
                width=50 * mm,
                height=12 * mm,
                preserveAspectRatio=True,
                anchor="sw",
                mask="auto",
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


def _render_pdf(payslip: object, emp: dict) -> bytes:
    """Renderiza o PDF usando reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=27 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # Estilos customizados
    style_title = ParagraphStyle(
        "titulo",
        parent=styles["Normal"],
        fontSize=14,
        fontName="Helvetica-Bold",
        alignment=1,  # center
        spaceAfter=2,
    )
    style_subtitle = ParagraphStyle(
        "subtitulo",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
        alignment=1,
        spaceAfter=1,
    )
    style_label = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica",
        textColor=colors.HexColor("#666666"),
    )
    style_value = ParagraphStyle(
        "value",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
    )
    style_section = ParagraphStyle(
        "section",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        backColor=colors.HexColor("#1a365d"),
        leftIndent=3,
    )
    style_footer = ParagraphStyle(
        "footer",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica",
        textColor=colors.HexColor("#888888"),
        alignment=1,
    )

    # Cores
    AZUL_ESCURO = colors.HexColor("#1a365d")
    AZUL_CLARO = colors.HexColor("#ebf4ff")
    CINZA_LINHA = colors.HexColor("#f5f5f5")
    VERDE = colors.HexColor("#276749")

    story = []

    # ── CABEÇALHO ──────────────────────────────────────────────────
    mes_nome = MESES.get(payslip.reference_month or 1, "")
    ano = payslip.reference_year or datetime.now().year
    periodo = f"{mes_nome}/{ano}"

    # Faixa de título do documento (a marca/logo é desenhada no topo da página por _brand_page)
    header_data = [
        [
            Paragraph(f"HOLERITE — {periodo}", style_title),
        ],
        [
            Paragraph("CONTRACHEQUE DE PAGAMENTO", style_subtitle),
        ],
    ]
    header_table = Table(header_data, colWidths=[175 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
                ("LINEBELOW", (0, -1), (-1, -1), 1.5, AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # ── DADOS DO FUNCIONÁRIO ────────────────────────────────────────
    story.append(Paragraph("IDENTIFICAÇÃO DO FUNCIONÁRIO", style_section))
    story.append(Spacer(1, 1 * mm))

    admissao_str = ""
    if emp.get("data_admissao"):
        try:
            admissao_str = emp["data_admissao"].strftime("%d/%m/%Y")
        except Exception:
            admissao_str = str(emp["data_admissao"])

    func_data = [
        [
            _cell("Matrícula", emp.get("matricula", ""), style_label, style_value),
            _cell("Nome do Funcionário", emp.get("nome", ""), style_label, style_value),
            _cell("CPF", _fmt_cpf(emp.get("cpf", "")), style_label, style_value),
        ],
        [
            _cell("Cargo / Função", emp.get("cargo", ""), style_label, style_value),
            _cell("Departamento", emp.get("departamento", ""), style_label, style_value),
            _cell("Data de Admissão", admissao_str, style_label, style_value),
        ],
    ]
    func_table = Table(func_data, colWidths=[45 * mm, 80 * mm, 50 * mm])
    func_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(func_table)
    story.append(Spacer(1, 4 * mm))

    # ── PERÍODO E PAGAMENTO ─────────────────────────────────────────
    comp_start = payslip.competence_start
    comp_end = payslip.competence_end
    payment_date = payslip.payment_date

    period_data = [
        [
            _cell("Competência", periodo, style_label, style_value),
            _cell("Período", f"{_fmt_date(comp_start)} a {_fmt_date(comp_end)}", style_label, style_value),
            _cell("Data de Pagamento", _fmt_date(payment_date), style_label, style_value),
            _cell("Código", payslip.payslip_code or "", style_label, style_value),
            _cell("Tipo", _fmt_tipo(payslip.payslip_type), style_label, style_value),
        ]
    ]
    period_table = Table(period_data, colWidths=[35 * mm, 45 * mm, 40 * mm, 35 * mm, 20 * mm])
    period_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(period_table)
    story.append(Spacer(1, 4 * mm))

    # ── TABELA DE EVENTOS ───────────────────────────────────────────
    story.append(Paragraph("EVENTOS", style_section))
    story.append(Spacer(1, 1 * mm))

    # Cabeçalho da tabela de eventos
    col_style = ParagraphStyle(
        "colhead",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=1,
    )
    event_header = [
        Paragraph("Cód.", col_style),
        Paragraph("Descrição", col_style),
        Paragraph("Referência", col_style),
        Paragraph("Vencimentos (R$)", col_style),
        Paragraph("Descontos (R$)", col_style),
    ]

    event_rows = [event_header]

    earnings = payslip.earnings or []
    deductions = payslip.deductions or []

    # Proventos
    for item in earnings:
        if not isinstance(item, dict):
            continue
        event_rows.append(
            [
                Paragraph(str(item.get("code", "")), _small_style(styles)),
                Paragraph(str(item.get("description", item.get("descricao", ""))), _small_style(styles)),
                Paragraph(_fmt_ref(item.get("reference", item.get("referencia", ""))), _small_style(styles, align=2)),
                Paragraph(_fmt_brl(item.get("value", item.get("valor", 0))), _small_style(styles, align=2)),
                Paragraph("", _small_style(styles, align=2)),
            ]
        )

    # Descontos
    for item in deductions:
        if not isinstance(item, dict):
            continue
        event_rows.append(
            [
                Paragraph(str(item.get("code", "")), _small_style(styles)),
                Paragraph(str(item.get("description", item.get("descricao", ""))), _small_style(styles)),
                Paragraph(_fmt_ref(item.get("reference", item.get("referencia", ""))), _small_style(styles, align=2)),
                Paragraph("", _small_style(styles, align=2)),
                Paragraph(_fmt_brl(item.get("value", item.get("valor", 0))), _small_style(styles, align=2)),
            ]
        )

    # Linha vazia se sem eventos
    if len(event_rows) == 1:
        event_rows.append(
            [
                Paragraph("", _small_style(styles)),
                Paragraph("(sem eventos registrados)", _small_style(styles)),
                Paragraph("", _small_style(styles)),
                Paragraph("", _small_style(styles)),
                Paragraph("", _small_style(styles)),
            ]
        )

    event_table = Table(
        event_rows,
        colWidths=[15 * mm, 75 * mm, 25 * mm, 30 * mm, 30 * mm],
    )
    row_colors = []
    for i in range(1, len(event_rows)):
        bg = colors.white if i % 2 == 1 else CINZA_LINHA
        row_colors.append(("BACKGROUND", (0, i), (-1, i), bg))

    event_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                *row_colors,
            ]
        )
    )
    story.append(event_table)
    story.append(Spacer(1, 4 * mm))

    # ── BASES DE CÁLCULO ────────────────────────────────────────────
    story.append(Paragraph("BASES DE CÁLCULO", style_section))
    story.append(Spacer(1, 1 * mm))

    bases_data = [
        [
            _cell("Base INSS", _fmt_brl(payslip.inss_base or 0), style_label, style_value),
            _cell("INSS Retido", _fmt_brl(payslip.inss_value or 0), style_label, style_value),
            _cell("Base IRRF", _fmt_brl(payslip.irrf_base or 0), style_label, style_value),
            _cell("IRRF Retido", _fmt_brl(payslip.irrf_value or 0), style_label, style_value),
            _cell("Base FGTS", _fmt_brl(payslip.fgts_base or 0), style_label, style_value),
            _cell("FGTS Mês", _fmt_brl(payslip.fgts_value or 0), style_label, style_value),
        ]
    ]
    bases_table = Table(bases_data, colWidths=[29 * mm, 29 * mm, 29 * mm, 29 * mm, 29 * mm, 30 * mm])
    bases_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(bases_table)
    story.append(Spacer(1, 5 * mm))

    # ── TOTAIS ──────────────────────────────────────────────────────
    total_earnings = float(payslip.total_earnings or 0)
    total_deductions = float(payslip.total_deductions or 0)
    net_salary = float(payslip.net_salary or 0)

    totais_style = ParagraphStyle(
        "totais",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        alignment=2,
    )
    totais_label_style = ParagraphStyle(
        "totais_label",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica",
        alignment=2,
        textColor=colors.HexColor("#555555"),
    )
    liquido_style = ParagraphStyle(
        "liquido",
        parent=styles["Normal"],
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=VERDE,
        alignment=2,
    )

    totais_data = [
        [
            Paragraph("Total de Vencimentos:", totais_label_style),
            Paragraph(_fmt_brl(total_earnings), totais_style),
            Paragraph("Total de Descontos:", totais_label_style),
            Paragraph(_fmt_brl(total_deductions), totais_style),
            Paragraph("LÍQUIDO A RECEBER:", totais_label_style),
            Paragraph(_fmt_brl(net_salary), liquido_style),
        ]
    ]
    totais_table = Table(totais_data, colWidths=[45 * mm, 30 * mm, 40 * mm, 30 * mm, 45 * mm, 35 * mm])
    totais_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
                ("LINEABOVE", (0, 0), (-1, 0), 2, AZUL_ESCURO),
                ("LINEBELOW", (0, -1), (-1, -1), 2, AZUL_ESCURO),
                ("BACKGROUND", (4, 0), (5, 0), colors.HexColor("#f0fff4")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(totais_table)
    story.append(Spacer(1, 8 * mm))

    # ── ASSINATURAS ─────────────────────────────────────────────────
    sign_data = [
        [
            Paragraph("_" * 38, style_footer),
            Paragraph("_" * 38, style_footer),
        ],
        [
            Paragraph("Assinatura do Empregador", style_footer),
            Paragraph("Assinatura do Funcionário / Ciente", style_footer),
        ],
    ]
    sign_table = Table(sign_data, colWidths=[88 * mm, 88 * mm])
    sign_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(sign_table)
    story.append(Spacer(1, 5 * mm))

    # ── FOOTER ──────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            f"Documento gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')} "
            f"| Conecta PRO ERP | {EMPRESA['cnpj']}",
            style_footer,
        )
    )

    doc.build(story, onFirstPage=_brand_page, onLaterPages=_brand_page)
    return buf.getvalue()


# ── HELPERS ─────────────────────────────────────────────────────────


def _cell(label: str, value: str, label_style, value_style) -> object:
    from reportlab.platypus import Paragraph

    return Paragraph(f'<font size="6" color="#666666">{label}</font><br/><b>{value or "—"}</b>', value_style)


def _small_style(styles, align: int = 0):
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle(
        f"small_{align}",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica",
        alignment=align,
    )


def _fmt_brl(value) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _fmt_ref(value) -> str:
    if value is None or value == "":
        return ""
    try:
        v = float(value)
        if v == int(v):
            return str(int(v))
        return f"{v:.2f}"
    except Exception:
        return str(value)


def _fmt_date(d) -> str:
    if not d:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _fmt_cpf(cpf: str) -> str:
    digits = "".join(c for c in (cpf or "") if c.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return cpf or "—"


def _fmt_tipo(tipo: str | None) -> str:
    mapa = {
        "monthly": "Mensal",
        "advance": "Adiantamento",
        "thirteenth_1st": "13º 1ª",
        "thirteenth_2nd": "13º 2ª",
        "vacation": "Férias",
        "termination": "Rescisão",
        "plr": "PLR",
        "bonus": "Bônus",
    }
    return mapa.get(str(tipo or ""), str(tipo or "Mensal"))
