"""Service: renderiza contratos CLT com Jinja2 e persiste em disco."""

from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_TEMPLATE_CANDIDATES = [
    Path("/app/templates/contrato_trabalho.html"),
    Path("/app/templates/templates/contrato_trabalho.html"),
]
_UPLOAD_DIR = Path("/app/uploads/contratos_gerados")
_AVISOS_DIR = Path("/app/uploads/avisos_gerados")

_AVISO_FERIAS_CANDIDATES = [
    Path("/app/templates/aviso_previo_ferias.html"),
    Path("/app/templates/templates/aviso_previo_ferias.html"),
]


class ContratoGerado(BaseModel):
    template_slug: str
    employee_id: str
    employee_name: str
    file_path: str
    file_url: str
    generated_at: datetime
    formato: str


class ContractGeneratorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def gerar_contrato_trabalho_html(self, employee_id: str) -> ContratoGerado:
        emp = await self._get_employee(employee_id)
        if not emp:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        html_template = await self._get_template()

        sal = float(emp["salario_base"] or 0)
        sal_fmt = f"R$ {sal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        adm = emp["data_admissao"]
        start_date_str = adm.strftime("%d/%m/%Y") if adm else ""

        context = {
            "employee_name": emp["nome"] or "",
            "cpf": emp["cpf"] or "",
            "role": emp["cargo"] or "",
            "start_date": start_date_str,
            "base_salary": sal_fmt,
            "contract_date": date.today().strftime("%d/%m/%Y"),
        }

        rendered = Template(html_template, undefined=StrictUndefined).render(context)

        output_dir = _UPLOAD_DIR / employee_id
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contrato_trabalho_{ts}.html"
        file_path = output_dir / filename
        file_path.write_text(rendered, encoding="utf-8")

        file_url = f"/api/v1/people-management/hr/contracts/employee/{employee_id}/download/{filename}"

        return ContratoGerado(
            template_slug="contrato_trabalho",
            employee_id=employee_id,
            employee_name=emp["nome"] or "",
            file_path=str(file_path),
            file_url=file_url,
            generated_at=datetime.now(),
            formato="html",
        )

    async def gerar_aviso_previo_ferias_html(
        self,
        employee_id: str,
        data_inicio_ferias: str,
        dias: int = 30,
    ) -> ContratoGerado:
        """Gera Aviso Prévio de Férias CLT (30 dias antes do início).

        Raises:
            ValueError: data no passado, dias inválidos, ou employee inexistente.
        """
        if dias <= 0 or dias > 30:
            raise ValueError(f"dias deve estar entre 1 e 30, recebido: {dias}")

        try:
            data_inicio = datetime.fromisoformat(data_inicio_ferias).date()
        except (ValueError, TypeError) as exc:
            raise ValueError(f"data_inicio_ferias inválida: {data_inicio_ferias!r}") from exc

        # Antecedência (30 dias) é orientação legal, NÃO trava técnica (decisão Jordan 25/07):
        # o aviso é um documento/registro formal que também precisa ser emitível para férias já
        # iniciadas ou retroativas. Mantém-se a validação de FORMATO da data (acima), não a de passado.

        emp = await self._get_employee(employee_id)
        if not emp:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        html_template = await self._get_template_by_service_type("ferias", _AVISO_FERIAS_CANDIDATES)

        data_fim = data_inicio + timedelta(days=dias - 1)
        data_retorno = data_inicio + timedelta(days=dias)
        data_aviso = date.today()

        adm: date | None = emp["data_admissao"]
        adm_str = adm.strftime("%d/%m/%Y") if adm else ""

        # Período aquisitivo: último aniversário de admissão antes do início das férias
        period_start, period_end = self._calc_periodo_aquisitivo(adm, data_inicio)

        context = {
            "employee_name": emp["nome"] or "",
            "role": emp["cargo"] or "",
            "admission_date": adm_str,
            "period_start": period_start,
            "period_end": period_end,
            "vacation_start": data_inicio.strftime("%d/%m/%Y"),
            "vacation_end": data_fim.strftime("%d/%m/%Y"),
            "vacation_days": str(dias),
            "return_date": data_retorno.strftime("%d/%m/%Y"),
            "notice_date": data_aviso.strftime("%d/%m/%Y"),
        }

        rendered = Template(html_template, undefined=StrictUndefined).render(context)

        output_dir = _AVISOS_DIR / employee_id
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"aviso_previo_ferias_{ts}.html"
        file_path = output_dir / filename
        file_path.write_text(rendered, encoding="utf-8")

        file_url = f"/api/v1/people-management/hr/contracts/employee/{employee_id}/download-aviso/{filename}"

        return ContratoGerado(
            template_slug="aviso_previo_ferias",
            employee_id=employee_id,
            employee_name=emp["nome"] or "",
            file_path=str(file_path),
            file_url=file_url,
            generated_at=datetime.now(),
            formato="html",
        )

    @staticmethod
    def _calc_periodo_aquisitivo(data_admissao: date | None, data_inicio_ferias: date) -> tuple[str, str]:
        """Calcula período aquisitivo (último aniversário de admissão antes das férias)."""
        if not data_admissao:
            # fallback: período de 1 ano terminando no dia antes das férias
            period_end = data_inicio_ferias - timedelta(days=1)
            period_start = period_end.replace(year=period_end.year - 1) + timedelta(days=1)
            return period_start.strftime("%d/%m/%Y"), period_end.strftime("%d/%m/%Y")

        ano = data_inicio_ferias.year
        try:
            aniversario_atual = data_admissao.replace(year=ano)
        except ValueError:
            # 29/02 em ano não-bissexto
            aniversario_atual = date(ano, 3, 1)

        if aniversario_atual > data_inicio_ferias:
            ano -= 1
            try:
                aniversario_atual = data_admissao.replace(year=ano)
            except ValueError:
                aniversario_atual = date(ano, 3, 1)

        period_start = aniversario_atual
        try:
            period_end = data_admissao.replace(year=ano + 1) - timedelta(days=1)
        except ValueError:
            period_end = date(ano + 1, 3, 1) - timedelta(days=1)

        return period_start.strftime("%d/%m/%Y"), period_end.strftime("%d/%m/%Y")

    async def _get_employee(self, employee_id: str) -> dict | None:
        r = await self.db.execute(
            text("""
                SELECT nome, cpf, cargo, data_admissao, salario_base
                FROM employees
                WHERE id = CAST(:eid AS uuid)
                  AND status = 'ativo'
                LIMIT 1
            """),
            {"eid": employee_id},
        )
        row = r.mappings().first()
        return dict(row) if row else None

    async def _get_template(self) -> str:
        return await self._get_template_by_service_type("admissao", _TEMPLATE_CANDIDATES)

    async def _get_template_by_service_type(self, service_type: str, fallback_paths: list[Path]) -> str:
        r = await self.db.execute(
            text("""
                SELECT content_template
                FROM contract_templates
                WHERE service_type = :st
                  AND is_active = true
                ORDER BY created_at ASC
                LIMIT 1
            """),
            {"st": service_type},
        )
        row = r.first()
        if row and row[0]:
            return row[0]
        for p in fallback_paths:
            if p.exists():
                return p.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Template service_type='{service_type}' não encontrado")
