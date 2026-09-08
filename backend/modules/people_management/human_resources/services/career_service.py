"""
Service para Plano de Carreira.

Implementa logica de negocio para gestao de planos de carreira:
- CRUD de planos de carreira
- Gestao de milestones (criacao, atualizacao, conclusao)
- Acompanhamento de progresso
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.human_resources.models.career import (
    CareerPlan,
    CareerPlanStatus,
)
from modules.people_management.human_resources.schemas.career import (
    CareerPlanCreate,
    CareerPlanUpdate,
    MilestoneCreate,
)

logger = logging.getLogger(__name__)


class CareerService:
    """Service para operacoes de plano de carreira."""

    def __init__(self, session: AsyncSession) -> None:
        """Inicializa o service.

        Args:
            session: Sessao async do SQLAlchemy.
        """
        self.session = session

    async def create_plan(self, data: CareerPlanCreate) -> CareerPlan:
        """Cria um novo plano de carreira.

        Args:
            data: Dados do plano.

        Returns:
            Plano criado.

        Raises:
            ValueError: Se funcionario ja tem plano ativo.
        """
        # Verificar se ja existe plano ativo
        existing = await self.session.execute(
            select(CareerPlan).where(
                CareerPlan.employee_id == data.employee_id,
                CareerPlan.status == CareerPlanStatus.ACTIVE,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Funcionario {data.employee_id} ja possui um plano de carreira ativo.")

        # Preparar milestones
        milestones_data = []
        if data.milestones:
            for m in data.milestones:
                milestone = {
                    "title": m.title,
                    "description": m.description,
                    "target_date": m.target_date.isoformat() if m.target_date else None,
                    "completed": False,
                    "completed_at": None,
                }
                milestones_data.append(milestone)

        plan_data = data.model_dump(exclude={"milestones"})
        plan = CareerPlan(
            id=uuid.uuid4(),
            milestones=milestones_data,
            **plan_data,
        )
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        logger.info(
            f"Plano de carreira criado: {data.current_position} -> {data.target_position} "
            f"(funcionario: {data.employee_id}, ID: {plan.id})"
        )
        return plan

    async def get_plan(self, plan_id: uuid.UUID) -> CareerPlan | None:
        """Busca um plano de carreira por ID.

        Args:
            plan_id: ID do plano.

        Returns:
            Plano encontrado ou None.
        """
        result = await self.session.execute(select(CareerPlan).where(CareerPlan.id == plan_id))
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        employee_id: uuid.UUID | None = None,
        status: str | None = None,
        mentor_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Lista planos de carreira com filtros e paginacao.

        Args:
            employee_id: Filtro por funcionario.
            status: Filtro por status.
            mentor_id: Filtro por mentor.
            page: Numero da pagina.
            page_size: Itens por pagina.

        Returns:
            Dicionario com items, total, page e page_size.
        """
        query = select(CareerPlan)
        count_query = select(func.count(CareerPlan.id))

        if employee_id:
            query = query.where(CareerPlan.employee_id == employee_id)
            count_query = count_query.where(CareerPlan.employee_id == employee_id)
        if status:
            query = query.where(CareerPlan.status == status)
            count_query = count_query.where(CareerPlan.status == status)
        if mentor_id:
            query = query.where(CareerPlan.mentor_id == mentor_id)
            count_query = count_query.where(CareerPlan.mentor_id == mentor_id)

        total = (await self.session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(CareerPlan.started_at.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        # Batch-fetch employee names to populate employee_name
        all_ids = list({str(p.employee_id) for p in items})
        names: dict[str, str] = {}
        if all_ids:
            stmt = text("SELECT id::text, nome FROM employees WHERE id::text IN :ids").bindparams(
                bindparam("ids", expanding=True)
            )
            rows = await self.session.execute(stmt, {"ids": all_ids})
            names = {row[0]: row[1] for row in rows}

        enriched = []
        for p in items:
            d = {c.key: getattr(p, c.key) for c in p.__table__.columns}
            d["employee_name"] = names.get(str(p.employee_id))
            enriched.append(d)

        return {"items": enriched, "total": total, "page": page, "page_size": page_size}

    async def update_plan(self, plan_id: uuid.UUID, data: CareerPlanUpdate) -> CareerPlan | None:
        """Atualiza um plano de carreira.

        Args:
            plan_id: ID do plano.
            data: Dados para atualizacao.

        Returns:
            Plano atualizado ou None.
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Converter milestones se fornecidos
        if "milestones" in update_data and update_data["milestones"] is not None:
            milestones_data = []
            for m in data.milestones:  # type: ignore[union-attr]
                milestone = {
                    "title": m.title,
                    "description": m.description,
                    "target_date": m.target_date.isoformat() if m.target_date else None,
                    "completed": False,
                    "completed_at": None,
                }
                milestones_data.append(milestone)
            update_data["milestones"] = milestones_data

        for field, value in update_data.items():
            setattr(plan, field, value)

        await self.session.commit()
        await self.session.refresh(plan)
        logger.info(f"Plano de carreira atualizado (ID: {plan.id})")
        return plan

    async def update_milestones(self, plan_id: uuid.UUID, milestones: list[MilestoneCreate]) -> CareerPlan | None:
        """Substitui os milestones de um plano.

        Args:
            plan_id: ID do plano.
            milestones: Novos milestones.

        Returns:
            Plano atualizado ou None.
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            return None

        milestones_data = []
        for m in milestones:
            milestone = {
                "title": m.title,
                "description": m.description,
                "target_date": m.target_date.isoformat() if m.target_date else None,
                "completed": False,
                "completed_at": None,
            }
            milestones_data.append(milestone)

        plan.milestones = milestones_data
        await self.session.commit()
        await self.session.refresh(plan)
        logger.info(f"Milestones atualizados para plano {plan.id}: {len(milestones)} milestones")
        return plan

    async def complete_milestone(self, plan_id: uuid.UUID, milestone_index: int) -> CareerPlan | None:
        """Marca um milestone como concluido.

        Args:
            plan_id: ID do plano.
            milestone_index: Indice do milestone na lista.

        Returns:
            Plano atualizado ou None.

        Raises:
            ValueError: Se indice invalido ou milestone ja concluido.
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            return None

        if not plan.milestones:
            raise ValueError("Plano nao possui milestones.")

        if milestone_index < 0 or milestone_index >= len(plan.milestones):
            raise ValueError(f"Indice de milestone invalido: {milestone_index}. Total: {len(plan.milestones)}")

        milestone = plan.milestones[milestone_index]
        if milestone.get("completed"):
            raise ValueError(f"Milestone '{milestone.get('title')}' ja esta concluido.")

        # Atualizar milestone (JSONB precisa de reassign para detectar mudanca)
        updated_milestones = list(plan.milestones)
        updated_milestones[milestone_index] = {
            **milestone,
            "completed": True,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        plan.milestones = updated_milestones

        # Verificar se todos milestones foram concluidos
        all_completed = all(m.get("completed", False) for m in plan.milestones)
        if all_completed:
            plan.status = CareerPlanStatus.COMPLETED
            plan.completed_at = datetime.now(UTC)
            logger.info(f"Plano de carreira concluido (ID: {plan.id}) - todos milestones completos")

        await self.session.commit()
        await self.session.refresh(plan)
        logger.info(f"Milestone {milestone_index} concluido no plano {plan.id}: '{milestone.get('title')}'")
        return plan

    async def delete_plan(self, plan_id: uuid.UUID) -> bool:
        """Remove um plano de carreira.

        Args:
            plan_id: ID do plano.

        Returns:
            True se removido com sucesso.
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            return False

        await self.session.delete(plan)
        await self.session.commit()
        logger.info(f"Plano de carreira removido (ID: {plan_id})")
        return True
