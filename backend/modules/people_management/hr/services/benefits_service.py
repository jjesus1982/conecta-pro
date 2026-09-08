"""
Serviço de Benefícios — Departamento Pessoal.

CRUD de benefícios por funcionário e cálculo de custo total de benefícios.
"""

import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.hr.models.benefits import (
    BenefitStatus,
    EmployeeBenefit,
)

logger = logging.getLogger(__name__)


class BenefitsService:
    """Serviço de Benefícios — visão DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_benefit(self, data: dict) -> EmployeeBenefit:
        """Cria um novo benefício para o funcionário.

        Args:
            data: Dados do benefício (schema BenefitCreate).

        Returns:
            Instância de EmployeeBenefit criada.
        """
        benefit = EmployeeBenefit(
            id=uuid4(),
            employee_id=data["employee_id"],
            type=data["type"],
            provider=data.get("provider"),
            plan_name=data.get("plan_name"),
            employee_contribution=data.get("employee_contribution", 0),
            company_contribution=data.get("company_contribution", 0),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            card_number=data.get("card_number"),
            notes=data.get("notes"),
            status=BenefitStatus.ACTIVE,
        )
        self.db.add(benefit)
        await self.db.flush()
        await self.db.refresh(benefit)
        logger.info("Benefício criado: %s para employee %s", benefit.id, benefit.employee_id)
        return benefit

    async def get_by_id(self, benefit_id: str | UUID) -> EmployeeBenefit | None:
        """Busca benefício por ID."""
        result = await self.db.execute(select(EmployeeBenefit).where(EmployeeBenefit.id == str(benefit_id)))
        return result.scalar_one_or_none()

    async def list_by_employee(
        self,
        employee_id: str | UUID,
        status: BenefitStatus | None = None,
    ) -> list[EmployeeBenefit]:
        """Lista benefícios de um funcionário.

        Args:
            employee_id: ID do funcionário.
            status: Filtro opcional por status.

        Returns:
            Lista de benefícios.
        """
        query = select(EmployeeBenefit).where(EmployeeBenefit.employee_id == str(employee_id))
        if status:
            query = query.where(EmployeeBenefit.status == status)
        query = query.order_by(EmployeeBenefit.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_benefit(self, benefit_id: str | UUID, data: dict) -> EmployeeBenefit | None:
        """Atualiza um benefício existente.

        Args:
            benefit_id: ID do benefício.
            data: Campos a atualizar.

        Returns:
            Benefício atualizado ou None.
        """
        benefit = await self.get_by_id(benefit_id)
        if not benefit:
            return None

        update_data = {k: v for k, v in data.items() if v is not None}
        for key, value in update_data.items():
            if hasattr(benefit, key):
                setattr(benefit, key, value)

        await self.db.flush()
        await self.db.refresh(benefit)
        return benefit

    async def cancel_benefit(self, benefit_id: str | UUID) -> EmployeeBenefit | None:
        """Cancela um benefício.

        Args:
            benefit_id: ID do benefício.

        Returns:
            Benefício cancelado ou None.
        """
        benefit = await self.get_by_id(benefit_id)
        if not benefit:
            return None

        benefit.status = BenefitStatus.CANCELLED
        await self.db.flush()
        await self.db.refresh(benefit)
        logger.info("Benefício %s cancelado", benefit_id)
        return benefit

    async def calculate_total_benefits(self, employee_id: str | UUID) -> dict:
        """Calcula o custo total de benefícios de um funcionário.

        Args:
            employee_id: ID do funcionário.

        Returns:
            Dicionário com totais por tipo e geral.
        """
        benefits = await self.list_by_employee(employee_id, status=BenefitStatus.ACTIVE)

        by_type: dict[str, dict] = {}
        total_employee = 0.0
        total_company = 0.0

        for b in benefits:
            emp_contrib = float(b.employee_contribution or 0)
            comp_contrib = float(b.company_contribution or 0)
            total_employee += emp_contrib
            total_company += comp_contrib

            by_type[b.type] = {
                "provider": b.provider,
                "plan_name": b.plan_name,
                "employee_contribution": emp_contrib,
                "company_contribution": comp_contrib,
                "total": emp_contrib + comp_contrib,
            }

        return {
            "employee_id": str(employee_id),
            "benefits_count": len(benefits),
            "by_type": by_type,
            "total_employee_contribution": round(total_employee, 2),
            "total_company_contribution": round(total_company, 2),
            "total_cost": round(total_employee + total_company, 2),
            # aliases lidos pela tela de benefícios (active_count/total_company/total_employee/total)
            "active_count": len(benefits),
            "total_company": round(total_company, 2),
            "total_employee": round(total_employee, 2),
            "total": round(total_employee + total_company, 2),
        }
