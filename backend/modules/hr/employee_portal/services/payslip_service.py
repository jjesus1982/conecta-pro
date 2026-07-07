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
        """Gera o PDF do contracheque no PADRÃO-OURO Conecta Mais (mesmo do holerite do DP).

        Recalcula pelo motor da folha (idêntico ao holerite oficial); se o colaborador não
        estiver ativo/calculável, usa os dados publicados no próprio contracheque (JSONB).
        """
        payslip = await self.repo.get_by_id(payslip_id)
        if not payslip:
            return None

        from pathlib import Path

        from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf

        out_dir = Path(f"/app/uploads/payslips/{payslip.condominio_id}")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = out_dir / f"{payslip.payslip_code}.pdf"

        emp_id = str(payslip.employee_id)
        mes = int(payslip.reference_month)
        ano = int(payslip.reference_year)

        data_pag = None
        if getattr(payslip, "payment_date", None):
            try:
                data_pag = payslip.payment_date.strftime("%d/%m/%Y")
            except Exception:
                data_pag = str(payslip.payment_date)

        holerite = None
        fdad: dict = {}
        # 1) Padrão-ouro: recalcula pelo motor da folha (idêntico ao holerite do DP)
        try:
            from sqlalchemy import text as _text

            from core.database.session import get_sync_db_dependency
            from modules.people_management.folha.services.calculo_service import (
                calcular_folha_colaborador,
            )

            sdb = next(get_sync_db_dependency())
            try:
                res = calcular_folha_colaborador(sdb, emp_id, mes, ano)
                if "error" not in res:
                    holerite = res
                    row = sdb.execute(
                        _text("SELECT cpf, pis, matricula, data_admissao FROM employees WHERE CAST(id AS TEXT) = :e"),
                        {"e": emp_id},
                    ).first()
                    if row:
                        adm = row[3]
                        fdad = {
                            "cpf": row[0],
                            "pis": row[1] or "—",
                            "matricula": row[2] or "—",
                            "data_admissao": adm.strftime("%d/%m/%Y") if hasattr(adm, "strftime") else (adm or "—"),
                            "posto": res.get("posto") or res.get("condominio") or "—",
                        }
            finally:
                sdb.close()
        except Exception:
            logger.exception("Falha ao recalcular contracheque %s pelo motor; usando dados publicados", payslip_id)
            holerite = None

        # 2) Fallback: monta a partir dos dados publicados no contracheque (JSONB)
        if holerite is None:

            def _map(items):
                mapped = []
                for it in items or []:
                    if isinstance(it, dict):
                        mapped.append(
                            {
                                "descricao": it.get("description") or it.get("descricao") or "—",
                                "referencia": it.get("reference") or it.get("referencia") or "",
                                "valor": float(it.get("value") or it.get("valor") or 0),
                            }
                        )
                return mapped

            holerite = {
                "employee_nome": getattr(payslip, "employee_name", "") or "—",
                "cargo": getattr(payslip, "employee_cargo", "") or "—",
                "escala": getattr(payslip, "employee_escala", "") or "—",
                "mes": mes,
                "ano": ano,
                "proventos": _map(getattr(payslip, "earnings", [])),
                "descontos": _map(getattr(payslip, "deductions", [])),
                "total_proventos": float(payslip.total_earnings or 0),
                "total_descontos": float(payslip.total_deductions or 0),
                "liquido": float(payslip.net_salary or 0),
                "base_inss": float(payslip.inss_base or 0),
                "base_fgts": float(payslip.fgts_base or 0),
                "base_irrf": float(payslip.irrf_base or 0),
                "fgts_empresa": float(payslip.fgts_value or 0),
            }
            fdad = {
                "matricula": getattr(payslip, "employee_matricula", "") or "—",
                "posto": getattr(payslip, "employee_departamento", "") or "—",
            }

        if data_pag:
            holerite["data_pagamento"] = data_pag

        pdf_file.write_bytes(montar_holerite_pdf(holerite, fdad))

        pdf_path = str(pdf_file)
        payslip.pdf_path = pdf_path
        payslip.pdf_generated_at = datetime.utcnow()
        await self.db.commit()

        logger.info("PDF (padrão-ouro) gerado para contracheque %s em %s", payslip_id, pdf_path)
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
