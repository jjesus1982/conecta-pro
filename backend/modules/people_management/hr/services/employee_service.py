"""
Serviço de Funcionários para o Departamento Pessoal.

Encapsula operações CRUD sobre Employee do módulo operacional,
adicionando métodos específicos da visão DP (busca por CPF,
perfil completo com benefícios e contratos, etc.).
"""

import logging
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.employee import Employee

logger = logging.getLogger(__name__)


class EmployeeService:
    """Serviço de Funcionários — visão Departamento Pessoal."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_employees(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict:
        """Retorna funcionários ativos com paginação e busca.

        Args:
            page: Número da página (1-based).
            page_size: Itens por página.
            search: Termo de busca (nome, CPF, matrícula).

        Returns:
            Dicionário com items, total, page, page_size e total_pages.
        """
        active_filter = func.lower(Employee.status) == "ativo"
        query = select(Employee).where(active_filter)
        count_query = select(func.count()).select_from(Employee).where(active_filter)

        if search:
            search_filter = or_(
                Employee.nome.ilike(f"%{search}%"),
                Employee.cpf.ilike(f"%{search}%"),
                Employee.matricula.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        employees = result.scalars().all()

        return {
            "items": employees,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_by_id(self, employee_id: str | UUID) -> Employee | None:
        """Busca funcionário por ID.

        Args:
            employee_id: UUID do funcionário.

        Returns:
            Instância de Employee ou None.
        """
        result = await self.db.execute(select(Employee).where(Employee.id == str(employee_id)))
        return result.scalar_one_or_none()

    async def get_by_cpf(self, cpf: str) -> Employee | None:
        """Busca funcionário por CPF.

        Args:
            cpf: CPF do funcionário (somente dígitos ou formatado).

        Returns:
            Instância de Employee ou None.
        """
        import re

        cpf_digits = re.sub(r"\D", "", cpf)
        result = await self.db.execute(select(Employee).where(Employee.cpf == cpf_digits))
        return result.scalar_one_or_none()

    async def get_employee_full_profile(self, employee_id: str | UUID) -> dict | None:
        """Retorna perfil completo do funcionário com dados agregados.

        Inclui dados pessoais, benefícios ativos, contrato vigente
        e últimas ocorrências disciplinares.

        Args:
            employee_id: UUID do funcionário.

        Returns:
            Dicionário com perfil completo ou None se não encontrado.
        """
        from modules.people_management.hr.models.benefits import EmployeeBenefit
        from modules.people_management.hr.models.contract import EmploymentContract

        employee = await self.get_by_id(employee_id)
        if not employee:
            return None

        # Buscar benefícios ativos
        benefits_result = await self.db.execute(
            select(EmployeeBenefit).where(
                EmployeeBenefit.employee_id == str(employee_id),
                EmployeeBenefit.status == "active",
            )
        )
        benefits = benefits_result.scalars().all()

        # Buscar contrato vigente
        contract_result = await self.db.execute(
            select(EmploymentContract).where(
                EmploymentContract.employee_id == str(employee_id),
                EmploymentContract.is_current.is_(True),
            )
        )
        current_contract = contract_result.scalar_one_or_none()

        def _to_dict(obj):
            """Converte SQLAlchemy model para dict serializável.

            Itera pelos atributos mapeados (Python attribute names) e não pelos
            nomes de coluna do banco. Em modelos onde o nome do atributo difere
            do nome da coluna (ex.: curso_formacao mapeado para a coluna
            'curso_vigilante'), usar ``column.key`` causaria AttributeError.
            """
            if obj is None:
                return None
            from sqlalchemy import inspect as sa_inspect

            mapper = sa_inspect(type(obj))
            return {attr.key: getattr(obj, attr.key) for attr in mapper.column_attrs}

        return {
            "employee": _to_dict(employee),
            "benefits": [_to_dict(b) for b in benefits],
            "current_contract": _to_dict(current_contract),
            "documents": [],
        }

    async def update_employee(self, employee_id: str | UUID, data: dict) -> Employee | None:
        """Atualiza dados DP do funcionário.

        Args:
            employee_id: UUID do funcionário.
            data: Campos a atualizar (filtrados por schema).

        Returns:
            Instância atualizada ou None se não encontrado.
        """
        employee = await self.get_by_id(employee_id)
        if not employee:
            return None

        update_data = {k: v for k, v in data.items() if v is not None}

        # Captura cargo anterior para detectar mudança de função
        cargo_anterior = employee.cargo
        departamento_anterior = employee.departamento

        for key, value in update_data.items():
            if hasattr(employee, key):
                setattr(employee, key, value)

        await self.db.flush()
        await self.db.refresh(employee)

        # Publicar evento de mudança de função se cargo ou departamento mudou
        cargo_novo = employee.cargo
        departamento_novo = employee.departamento
        if (cargo_novo and cargo_novo != cargo_anterior) or (
            departamento_novo and departamento_novo != departamento_anterior
        ):
            try:
                import asyncio

                from infrastructure.message_bus.events import Event, EventType, publish_event

                event = Event(
                    type=EventType.FUNCIONARIO_MUDANCA_FUNCAO,
                    source="people_management.employee_service",
                    data={
                        "funcionario_id": str(employee.id),
                        "nome": employee.nome,
                        "cargo_anterior": cargo_anterior or "",
                        "cargo_novo": cargo_novo or "",
                        "departamento_anterior": departamento_anterior or "",
                        "departamento_novo": departamento_novo or "",
                    },
                )
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(publish_event(event))
                else:
                    asyncio.run(publish_event(event))
            except Exception as _pub_err:
                logger.warning("Falha ao publicar FUNCIONARIO_MUDANCA_FUNCAO: %s", _pub_err)

        return employee
