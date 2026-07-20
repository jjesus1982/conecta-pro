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

    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
    )
    from sqlalchemy import text

    from modules.crm.services import pdf_branding as B

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
    sal_fmt = B.brl(sal)
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

    # ── 4. Construir PDF com reportlab (padrão-ouro Conecta Mais) ─────────────
    st = B.styles()
    s_corpo = st["corpo"]
    s_subtitulo = ParagraphStyle(
        "Subtitulo",
        parent=st["corpo"],
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=B.AZUL_MEDIO,
        spaceAfter=8,
    )
    empregada_cpf = ct.get("employee_cpf", "N/I")
    if empregada_cpf == "N/I":
        empregada_cpf = None

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
        title=f"Contrato de Trabalho — {employee_name}",
        author=B.EMPRESA["nome"],
    )

    story: list = []

    # Subtítulo com o tipo de contrato
    story.append(Paragraph(type_label, s_subtitulo))

    # Partes
    story += B.secao("DAS PARTES", st)
    story.append(
        Paragraph(
            f"<b>EMPREGADORA:</b> {B.EMPRESA['razao']}, "
            f"CNPJ {B.EMPRESA['cnpj']}, com sede em {B.EMPRESA['endereco']}, "
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

    story += B.secao("DAS CLÁUSULAS", st)
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

    # Multi-CNPJ: contrato de trabalho sai pela empresa dona do vínculo (Patrimonial CLT).
    _empresa_doc = B.empresa_branding_por_cpf(empregada_cpf)

    # Assinaturas (padrão-ouro: funcionário assina digital pelo Portal; empresa = CEO Jordan)
    story += B.campos_assinatura(
        st,
        funcionario_nome=employee_name,
        funcionario_cpf=empregada_cpf,
        data_str=data_extenso,
        digital_funcionario=True,
        digital_empresa=True,
        espaco_antes=14,
        empresa=_empresa_doc,
    )

    # Autenticidade branded: se já houver assinaturas coletadas (motor universal),
    # imprime o bloco padrão-ouro com nome/hash/data (não-repúdio visual).
    try:
        from modules.signatures.services.universal_signature_service import (
            UniversalSignatureService,
        )

        _sig = await UniversalSignatureService(db).status(
            document_type="contract", document_id=str(contract_id)
        )
        story += B.bloco_autenticidade_assinaturas(
            st, signatarios=_sig.get("signatarios"), empresa=_empresa_doc
        )
    except Exception:  # noqa: BLE001
        pass

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRATO DE TRABALHO", empresa=_empresa_doc),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRATO DE TRABALHO", empresa=_empresa_doc),
    )
    return buffer.getvalue()
