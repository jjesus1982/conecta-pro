"""
Serviço de Contratos de Trabalho — Departamento Pessoal.

CRUD de contratos de trabalho e geração de documento contratual em PDF.
"""

import logging
from io import BytesIO
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.hr.models.contract import (
    ContractType,
    EmploymentContract,
)

logger = logging.getLogger(__name__)


def _contrato_brand_page(canvas, doc):
    """Marca Conecta Mais (logo + linha no topo, rodapé oficial) no contrato de trabalho."""
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
                lp, 30 * mm, h - 20 * mm, width=50 * mm, height=12 * mm,
                preserveAspectRatio=True, anchor="sw", mask="auto",
            )
            drew = True
        except Exception:  # noqa: BLE001
            pass
    if not drew:
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(B.AZUL_ESCURO)
        canvas.drawString(30 * mm, h - 15 * mm, B.EMPRESA["nome"])
    canvas.setStrokeColor(B.LARANJA)
    canvas.setLineWidth(1.2)
    canvas.line(30 * mm, h - 22 * mm, w - 20 * mm, h - 22 * mm)
    canvas.setStrokeColor(B.AZUL_ESCURO)
    canvas.setLineWidth(0.6)
    canvas.line(30 * mm, 14 * mm, w - 20 * mm, 14 * mm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(B.AZUL_MEDIO)
    canvas.drawString(
        30 * mm, 10 * mm, f"{B.EMPRESA['nome']} | CNPJ: {B.EMPRESA['cnpj']} | {B.EMPRESA['fone']} | {B.EMPRESA['site']}"
    )
    canvas.drawRightString(w - 20 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


class ContractService:
    """Serviço de Contratos de Trabalho — visão DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_contract(self, data: dict) -> EmploymentContract:
        """Cria um novo contrato de trabalho.

        Se houver contrato vigente, marca-o como não atual.

        Args:
            data: Dados do contrato (schema ContractCreate).

        Returns:
            Instância de EmploymentContract criada.
        """
        # Desativar contrato vigente anterior
        current_result = await self.db.execute(
            select(EmploymentContract).where(
                EmploymentContract.employee_id == data["employee_id"],
                EmploymentContract.is_current.is_(True),
            )
        )
        current_contract = current_result.scalar_one_or_none()

        previous_id = None
        if current_contract:
            current_contract.is_current = False
            previous_id = str(current_contract.id)

        contract = EmploymentContract(
            id=uuid4(),
            employee_id=data["employee_id"],
            type=data["type"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            work_schedule=data.get("work_schedule"),
            weekly_hours=data.get("weekly_hours"),
            base_salary=data["base_salary"],
            hazard_pay_percent=data.get("hazard_pay_percent", 0),
            unhealthy_pay_percent=data.get("unhealthy_pay_percent", 0),
            night_shift_percent=data.get("night_shift_percent", 0),
            job_title=data.get("job_title"),
            department=data.get("department"),
            cost_center=data.get("cost_center"),
            workplace_id=data.get("workplace_id"),
            union_name=data.get("union_name"),
            union_code=data.get("union_code"),
            is_current=True,
            previous_contract_id=previous_id,
            notes=data.get("notes"),
        )
        self.db.add(contract)
        await self.db.flush()
        await self.db.refresh(contract)
        logger.info("Contrato criado: %s para employee %s", contract.id, contract.employee_id)
        return contract

    async def list_all(self, page: int = 1, page_size: int = 20) -> dict:
        """Lista todos os contratos com paginação.

        Args:
            page: Página atual.
            page_size: Itens por página.

        Returns:
            Dicionário com items, total, page, page_size, total_pages.
        """
        from sqlalchemy import func

        count_query = select(func.count()).select_from(EmploymentContract)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        query = (
            select(EmploymentContract)
            .order_by(EmploymentContract.start_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": list(items),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_by_id(self, contract_id: str | UUID) -> EmploymentContract | None:
        """Busca contrato por ID."""
        result = await self.db.execute(select(EmploymentContract).where(EmploymentContract.id == str(contract_id)))
        return result.scalar_one_or_none()

    async def get_current_contract(self, employee_id: str | UUID) -> EmploymentContract | None:
        """Busca o contrato vigente de um funcionário."""
        result = await self.db.execute(
            select(EmploymentContract).where(
                EmploymentContract.employee_id == str(employee_id),
                EmploymentContract.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_employee(self, employee_id: str | UUID) -> list[EmploymentContract]:
        """Lista todos os contratos de um funcionário (histórico).

        Args:
            employee_id: ID do funcionário.

        Returns:
            Lista de contratos ordenados por data de início (desc).
        """
        result = await self.db.execute(
            select(EmploymentContract)
            .where(EmploymentContract.employee_id == str(employee_id))
            .order_by(EmploymentContract.start_date.desc())
        )
        return list(result.scalars().all())

    async def update_contract(self, contract_id: str | UUID, data: dict) -> EmploymentContract | None:
        """Atualiza dados de um contrato.

        Args:
            contract_id: ID do contrato.
            data: Campos a atualizar.

        Returns:
            Contrato atualizado ou None.
        """
        contract = await self.get_by_id(contract_id)
        if not contract:
            return None

        update_data = {k: v for k, v in data.items() if v is not None}
        for key, value in update_data.items():
            if hasattr(contract, key):
                setattr(contract, key, value)

        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    def generate_contract_document(
        self,
        contract: EmploymentContract,
        employee_name: str,
        company_name: str = "CONECTAMAIS ELETRONICA LTDA",
        company_cnpj: str = "35.710.481/0001-03",
    ) -> dict:
        """Gera dados para documento de contrato de trabalho.

        Args:
            contract: Instância do contrato.
            employee_name: Nome do funcionário.
            company_name: Razão social da empresa.
            company_cnpj: CNPJ da empresa.

        Returns:
            Dicionário com dados do documento contratual.
        """
        contract_type_labels = {
            ContractType.CLT_INDETERMINATE: "Contrato por Prazo Indeterminado",
            ContractType.CLT_DETERMINATE: "Contrato por Prazo Determinado",
            ContractType.TEMPORARY: "Contrato Temporário",
            ContractType.INTERMITTENT: "Contrato Intermitente",
            ContractType.APPRENTICE: "Contrato de Aprendizagem",
            ContractType.INTERN: "Contrato de Estágio",
        }

        total_salary = float(contract.base_salary)
        if contract.hazard_pay_percent:
            total_salary += total_salary * (float(contract.hazard_pay_percent) / 100)
        if contract.unhealthy_pay_percent:
            total_salary += float(contract.base_salary) * (float(contract.unhealthy_pay_percent) / 100)

        return {
            "document_type": "employment_contract",
            "contract_id": str(contract.id),
            "company": {
                "name": company_name,
                "cnpj": company_cnpj,
            },
            "employee": {
                "name": employee_name,
                "employee_id": str(contract.employee_id),
            },
            "contract": {
                "type_label": contract_type_labels.get(
                    ContractType(contract.type) if contract.type in [e.value for e in ContractType] else None,
                    str(contract.type),
                ),
                "start_date": contract.start_date.isoformat(),
                "end_date": contract.end_date.isoformat() if contract.end_date else None,
                "work_schedule": contract.work_schedule,
                "weekly_hours": float(contract.weekly_hours) if contract.weekly_hours else None,
                "base_salary": float(contract.base_salary),
                "hazard_pay_percent": float(contract.hazard_pay_percent or 0),
                "unhealthy_pay_percent": float(contract.unhealthy_pay_percent or 0),
                "night_shift_percent": float(contract.night_shift_percent or 0),
                "total_salary_estimate": round(total_salary, 2),
                "job_title": contract.job_title,
                "department": contract.department,
                "union_name": contract.union_name,
            },
            "generated_at": None,  # Será preenchido na geração do PDF
        }


# ─── Geração real de PDF ──────────────────────────────────────────────────────


async def gerar_pdf_contrato(db: AsyncSession, contract_id: str) -> bytes:
    """Gera PDF real do contrato de trabalho usando reportlab.

    Busca dados do contrato + funcionário, consulta contract_templates
    para clauses customizadas, e gera PDF via reportlab.

    Args:
        db: Sessão async do banco.
        contract_id: UUID do contrato.

    Returns:
        Bytes do arquivo PDF gerado.

    Raises:
        ValueError: Se o contrato não for encontrado.
    """
    from datetime import datetime

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from sqlalchemy import text

    # ── 1. Buscar contrato + funcionário ──────────────────────────────────────
    r = await db.execute(
        text("""
        SELECT
            ec.id::text            AS contract_id,
            ec.type,
            ec.start_date,
            ec.end_date,
            ec.base_salary::float  AS base_salary,
            ec.work_schedule,
            ec.weekly_hours::float AS weekly_hours,
            ec.hazard_pay_percent::float  AS hazard_pay_percent,
            ec.unhealthy_pay_percent::float AS unhealthy_pay_percent,
            ec.night_shift_percent::float   AS night_shift_percent,
            ec.job_title,
            ec.department,
            ec.union_name,
            e.nome            AS employee_name,
            COALESCE(e.cpf, 'N/I')   AS employee_cpf,
            COALESCE(e.pis, 'N/I')   AS employee_pis,
            COALESCE(e.cargo, ec.job_title, 'N/I') AS employee_cargo
        FROM employment_contracts ec
        JOIN employees e ON e.id = ec.employee_id
        WHERE ec.id = CAST(:cid AS uuid)
        LIMIT 1
        """),
        {"cid": contract_id},
    )
    row = r.mappings().first()
    if not row:
        raise ValueError(f"Contrato {contract_id} não encontrado")

    ct = dict(row)

    # ── 2. Buscar template customizado (se existir) ───────────────────────────
    r2 = await db.execute(
        text("""
        SELECT name, clauses
        FROM contract_templates
        WHERE is_active = true
          AND (service_type ILIKE '%clt%'
            OR service_type ILIKE '%contrat%'
            OR service_type IS NULL)
        ORDER BY approved_by_legal DESC NULLS LAST,
                 created_at ASC
        LIMIT 1
        """)
    )
    tmpl_row = r2.mappings().first()
    extra_clauses: list[dict] = []
    if tmpl_row and tmpl_row.get("clauses"):
        raw = tmpl_row["clauses"]
        if isinstance(raw, list):
            extra_clauses = raw
        elif isinstance(raw, str):
            import json

            try:
                extra_clauses = json.loads(raw) or []
            except Exception:
                extra_clauses = []

    # ── 3. Montar variáveis ───────────────────────────────────────────────────
    type_labels = {
        "clt_indeterminate": "CLT — Prazo Indeterminado",
        "clt_determinate": "CLT — Prazo Determinado",
        "temporary": "Contrato Temporário",
        "intermittent": "Contrato Intermitente",
        "apprentice": "Contrato de Aprendizagem",
        "intern": "Contrato de Estágio",
    }
    type_label = type_labels.get(ct["type"], ct["type"].upper())

    sal = float(ct.get("base_salary") or 0)
    sal_fmt = f"R$ {sal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    hoje = datetime.now()
    meses_pt = [
        "",
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    data_extenso = f"{hoje.day} de {meses_pt[hoje.month]} de {hoje.year}"

    employee_name = ct.get("employee_name") or "N/A"
    job_title = ct.get("job_title") or ct.get("employee_cargo") or "N/A"
    department = ct.get("department") or "N/A"
    union_name = ct.get("union_name") or "Sindicato da categoria"
    start_date = str(ct.get("start_date") or "")
    end_date = str(ct.get("end_date")) if ct.get("end_date") else "Indeterminado"
    work_schedule = ct.get("work_schedule") or "44h/semana"
    weekly_hours = str(ct.get("weekly_hours") or 44)
    hazard = float(ct.get("hazard_pay_percent") or 0)
    unhealthy = float(ct.get("unhealthy_pay_percent") or 0)
    night = float(ct.get("night_shift_percent") or 0)

    # ── 4. Construir PDF com reportlab ────────────────────────────────────────
    AZUL = colors.HexColor("#1E3A5F")
    CINZA = colors.HexColor("#555555")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2 * cm,
        topMargin=3.2 * cm,
        bottomMargin=2.2 * cm,
        title=f"Contrato de Trabalho — {employee_name}",
        author="Conecta Mais Segurança e Tecnologia Ltda",
    )

    styles = getSampleStyleSheet()
    s_titulo = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=4,
        textColor=AZUL,
        fontName="Helvetica-Bold",
    )
    s_subtitulo = ParagraphStyle(
        "Subtitulo",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=14,
        textColor=CINZA,
    )
    s_secao = ParagraphStyle(
        "Secao",
        parent=styles["Normal"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
        textColor=AZUL,
        fontName="Helvetica-Bold",
    )
    s_corpo = ParagraphStyle(
        "Corpo",
        parent=styles["Normal"],
        fontSize=11,
        alignment=TA_JUSTIFY,
        leading=18,
        spaceAfter=8,
    )
    s_assina = ParagraphStyle(
        "Assina",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        leading=16,
    )

    story: list = []

    # Cabeçalho
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("CONTRATO INDIVIDUAL DE TRABALHO", s_titulo))
    story.append(Paragraph(type_label, s_subtitulo))
    story.append(HRFlowable(width="100%", thickness=1.5, color=AZUL))
    story.append(Spacer(1, 0.4 * cm))

    # Partes
    story.append(Paragraph("DAS PARTES", s_secao))
    story.append(
        Paragraph(
            "<b>EMPREGADORA:</b> Conecta Mais Segurança e Tecnologia Ltda, "
            "CNPJ 35.710.481/0001-03, com sede em Manaus/AM, "
            "doravante denominada simplesmente <b>EMPREGADORA</b>;",
            s_corpo,
        )
    )
    story.append(
        Paragraph(
            f"<b>EMPREGADO(A):</b> {employee_name}, "
            f"CPF {ct.get('employee_cpf', 'N/I')}, "
            f"PIS {ct.get('employee_pis', 'N/I')}, "
            f"doravante denominado(a) <b>EMPREGADO(A)</b>.",
            s_corpo,
        )
    )

    # Cláusulas padrão
    clausulas_padrao = [
        (
            "1ª — DO OBJETO",
            f"A EMPREGADORA admite o(a) EMPREGADO(A) para exercer a função de "
            f"<b>{job_title}</b>"
            + (f", no departamento de {department}" if department != "N/A" else "")
            + ", nos termos da CLT e demais normas trabalhistas vigentes.",
        ),
        (
            "2ª — DO PRAZO",
            f"O presente contrato tem início em <b>{start_date}</b> e término em <b>{end_date}</b>.",
        ),
        (
            "3ª — DA REMUNERAÇÃO",
            f"O(A) EMPREGADO(A) perceberá salário base de <b>{sal_fmt}</b> mensais"
            + (f", acrescido de adicional de periculosidade de {hazard:.0f}%" if hazard else "")
            + (f", adicional de insalubridade de {unhealthy:.0f}%" if unhealthy else "")
            + (f", adicional noturno de {night:.0f}%" if night else "")
            + ", pago até o 5° dia útil do mês subsequente.",
        ),
        (
            "4ª — DA JORNADA",
            f"A jornada de trabalho será de <b>{weekly_hours} horas semanais</b>, "
            f"conforme escala <b>{work_schedule}</b>, nos termos do Art. 58 da CLT.",
        ),
        (
            "5ª — DO SINDICATO",
            f"O(A) EMPREGADO(A) é representado(a) pelo sindicato: <b>{union_name}</b>.",
        ),
        (
            "6ª — DAS DISPOSIÇÕES GERAIS",
            "O presente contrato obedece às demais disposições da CLT, acordos e "
            "convenções coletivas vigentes, e ao Código Civil Brasileiro no que "
            "for aplicável.",
        ),
    ]

    story.append(Paragraph("DAS CLÁUSULAS", s_secao))
    for titulo, texto in clausulas_padrao:
        story.append(Paragraph(f"<b>CLÁUSULA {titulo}</b>", s_corpo))
        story.append(Paragraph(texto, s_corpo))

    # Cláusulas extras vindas do contract_templates
    for i, cl in enumerate(extra_clauses, start=len(clausulas_padrao) + 1):
        titulo_cl = cl.get("titulo") or cl.get("title") or f"{i}ª"
        texto_cl = cl.get("texto") or cl.get("text") or cl.get("content") or ""
        if texto_cl:
            story.append(Paragraph(f"<b>CLÁUSULA {titulo_cl}</b>", s_corpo))
            story.append(Paragraph(texto_cl, s_corpo))

    # Assinaturas
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"Manaus/AM, {data_extenso}", s_assina))
    story.append(Spacer(1, 1.2 * cm))

    sign_data = [
        [
            Paragraph(
                "______________________________<br/><b>Conecta Mais Segurança e Tecnologia Ltda</b><br/>EMPREGADORA",
                s_assina,
            ),
            Paragraph(
                f"______________________________<br/><b>{employee_name}</b><br/>EMPREGADO(A)",
                s_assina,
            ),
        ]
    ]
    sign_table = Table(sign_data, colWidths=[8 * cm, 8 * cm])
    sign_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(sign_table)

    doc.build(story, onFirstPage=_contrato_brand_page, onLaterPages=_contrato_brand_page)
    return buffer.getvalue()
