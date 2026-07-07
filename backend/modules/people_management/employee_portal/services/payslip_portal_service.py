"""Service para contracheques do Portal do Funcionario.

Conecta o portal (people_management) ao repositório real (hr_payslips).
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Códigos de LINHA DE TOTAL nas rubricas (Domínio/Portte). Não são itens
# individuais: incluí-los duplica a contagem (ex.: 'Proventos Totais' somado a
# 'Salário Base' > bruto real). Filtramos do detalhamento do contracheque.
_TOTAL_ROW_CODES = {"0099", "99", "9999", "0999"}


def _is_total_row(rubrica: dict) -> bool:
    """True se a rubrica é uma linha de TOTAL (não itemizável)."""
    code_raw = str(rubrica.get("code") or "").strip()
    if code_raw in _TOTAL_ROW_CODES:
        return True
    desc = str(rubrica.get("description") or rubrica.get("descricao") or "").upper()
    return (
        "PROVENTOS TOTAIS" in desc
        or "TOTAL DESCONTOS" in desc
        or desc.strip() in {"TOTAIS", "TOTAL"}
    )


class PayslipPortalService:
    """Service para consulta de contracheques no portal do funcionario.

    Usa o PaySlipRepository do modulo hr para acessar a tabela hr_payslips.
    Fornece fallback seguro quando nao ha dados (lista vazia + mensagem).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _get_repo(self):
        """Instancia o PaySlipRepository de forma lazy (evita import circular)."""
        from modules.hr.employee_portal.repositories.payslip_repository import PaySlipRepository

        return PaySlipRepository(self.db)

    async def get_payslips_list(
        self,
        employee_id: UUID,
        year: int | None = None,
    ) -> dict:
        """Retorna lista de contracheques do funcionario para o ano.

        Args:
            employee_id: UUID do funcionario.
            year: Ano de referencia (default: ano atual).

        Returns:
            Dict com chaves 'payslips' (list) e 'message' (str|None).
            'payslips' eh lista vazia se nao houver dados no banco.
        """
        target_year = year or datetime.utcnow().year
        repo = self._get_repo()

        try:
            payslips, total = await repo.list_by_employee(
                employee_id,
                year=target_year,
                only_viewable=True,
                page=1,
                page_size=24,  # 12 meses x 2 (mensal + 13º)
            )

            if not payslips:
                return {
                    "payslips": [],
                    "total": 0,
                    "message": (
                        "Nenhum contracheque disponivel para o ano selecionado. "
                        "Entre em contato com o Departamento Pessoal."
                    ),
                }

            items = [self._to_portal_dict(p) for p in payslips]
            return {
                "payslips": items,
                "total": total,
                "message": None,
            }

        except Exception:
            logger.exception(
                "Erro ao buscar contracheques do funcionario %s (ano=%d)",
                employee_id,
                target_year,
            )
            return {
                "payslips": [],
                "total": 0,
                "message": ("Nenhum contracheque disponivel no momento. Entre em contato com o Departamento Pessoal."),
            }

    async def get_payslip_detail(
        self,
        employee_id: UUID,
        month: int,
        year: int,
    ) -> dict | None:
        """Busca contracheque especifico e registra visualizacao.

        Args:
            employee_id: UUID do funcionario.
            month: Mes (1-12).
            year: Ano.

        Returns:
            Dict com dados do contracheque, ou None se nao encontrado
            (o controller converte em 404).
        """
        repo = self._get_repo()
        payslip = await repo.get_by_employee_month_year(employee_id, month, year)

        if not payslip:
            # Vazio-real: sem holerite no mes/ano -> None -> controller emite 404.
            return None

        # Registrar visualizacao
        await repo.record_view(payslip.id)

        return self._to_portal_dict(payslip, include_items=True)

    async def get_payslip_pdf_url(
        self,
        employee_id: UUID,
        month: int,
        year: int,
    ) -> str | None:
        """Retorna caminho do PDF do contracheque.

        Se o PDF nao foi gerado ainda, retorna None (o controller gerara).

        Args:
            employee_id: UUID do funcionario.
            month: Mes (1-12).
            year: Ano.

        Returns:
            Caminho do arquivo PDF, ou None se o contracheque nao existe
            ou o PDF ainda nao foi gerado (o controller trata o None).
        """
        repo = self._get_repo()
        payslip = await repo.get_by_employee_month_year(employee_id, month, year)

        if not payslip:
            # Vazio-real: sem holerite no mes/ano -> None (nao quebra com 500).
            return None

        # Registrar download
        await repo.record_download(payslip.id)

        return payslip.pdf_path  # None se PDF ainda nao foi gerado

    async def get_available_years(self, employee_id: UUID) -> list[int]:
        """Retorna anos disponiveis para o funcionario."""
        repo = self._get_repo()
        try:
            return await repo.get_years_available(employee_id)
        except Exception:
            logger.exception("Erro ao buscar anos disponiveis para %s", employee_id)
            return []

    async def get_summary(self, employee_id: UUID) -> dict:
        """Retorna resumo de contracheques do funcionario.

        Inclui contagem de nao lidos, ultimo contracheque e anos disponiveis.
        """
        repo = self._get_repo()
        try:
            unread = await repo.get_unread_count(employee_id)
            years = await repo.get_years_available(employee_id)
            latest = await repo.get_latest(employee_id)

            last_payslip = None
            if latest:
                last_payslip = {
                    "id": str(latest.id),
                    "reference_period": latest.reference_period_fmt,
                    "net_salary": float(latest.net_salary or 0),
                    "payment_date": (latest.payment_date.isoformat() if latest.payment_date else None),
                    "status": latest.status,
                }

            return {
                "unread_count": unread,
                "available_years": years,
                "last_payslip": last_payslip,
            }
        except Exception:
            logger.exception("Erro ao gerar resumo de contracheques para %s", employee_id)
            return {
                "unread_count": 0,
                "available_years": [],
                "last_payslip": None,
            }

    # ------------------------------------------------------------------
    # Helpers de mapeamento
    # ------------------------------------------------------------------

    def _to_portal_dict(self, payslip, *, include_items: bool = False) -> dict:
        """Converte PaySlip para dicionario compativel com o portal.

        Normaliza os campos para o formato esperado pelo frontend
        (MyPayslipResponse schema).
        """
        earnings = payslip.earnings or []
        deductions = payslip.deductions or []

        # Calcular totais a partir do detalhamento se os campos nao estiverem populados
        gross_salary = float(payslip.total_earnings or payslip.base_salary or 0)
        total_deductions = float(payslip.total_deductions or 0)
        net_salary = float(payslip.net_salary or 0)

        data = {
            "id": str(payslip.id),
            "month": payslip.reference_month,
            "year": payslip.reference_year,
            "reference_period": payslip.reference_period_fmt,
            "gross_salary": gross_salary,
            "deductions": total_deductions,
            "net_salary": net_salary,
            "status": payslip.status,
            "payment_date": (payslip.payment_date.isoformat() if payslip.payment_date else None),
            "viewed": payslip.first_viewed_at is not None,
            "acknowledged": payslip.acknowledged_at is not None,
            "contested": payslip.contested,
            "pdf_available": payslip.pdf_path is not None,
        }

        if include_items:
            # Construir lista de itens no formato do portal (PayslipItem)
            items = []
            for e in earnings if isinstance(earnings, list) else []:
                if isinstance(e, dict) and not _is_total_row(e):
                    items.append(
                        {
                            "description": e.get("description", ""),
                            "type": "provento",
                            "reference": str(e.get("reference", "")) if e.get("reference") else None,
                            "value": float(e.get("value", 0)),
                        }
                    )
            for d in deductions if isinstance(deductions, list) else []:
                if isinstance(d, dict) and not _is_total_row(d):
                    items.append(
                        {
                            "description": d.get("description", ""),
                            "type": "desconto",
                            "reference": str(d.get("reference", "")) if d.get("reference") else None,
                            "value": float(d.get("value", 0)),
                        }
                    )
            data["items"] = items

        return data
