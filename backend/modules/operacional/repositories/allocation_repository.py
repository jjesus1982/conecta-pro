"""
Repository para operações de banco de dados com Allocation.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.models.allocation import Allocation, AllocationStatus
from modules.operacional.models.employee import Employee
from modules.operacional.models.post import Post
from modules.operacional.schemas.allocation import (
    AllocationBulkUpdateItem,
    AllocationCreate,
    AllocationFilter,
    AllocationUpdate,
)


class AllocationRepository:
    """Repository para operações CRUD de Allocation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _update_post_headcount(self, post_id: str) -> None:
        """
        Atualiza o current_headcount de um posto baseado nas alocações ativas.

        Args:
            post_id: ID do posto
        """
        count_query = select(func.count(Allocation.id)).where(
            Allocation.post_id == post_id,
            Allocation.is_active.is_(True),
            Allocation.status == AllocationStatus.ACTIVE.value,
        )
        result = await self.db.execute(count_query)
        count = result.scalar_one()

        update_stmt = update(Post).where(Post.id == post_id).values(current_headcount=count)
        await self.db.execute(update_stmt)
        logger.debug(f"Post {post_id} current_headcount atualizado para {count}")

    async def check_active_allocation(
        self,
        employee_id: str,
        post_id: str,
        start_date: date,
        end_date: date | None = None,
        exclude_allocation_id: str | None = None,
    ) -> Allocation | None:
        """
        Verifica se já existe alocação ativa para o funcionário no posto e período.

        Args:
            employee_id: ID do funcionário
            post_id: ID do posto
            start_date: Data de início da nova alocação
            end_date: Data de fim da nova alocação (opcional)
            exclude_allocation_id: ID de alocação a excluir da verificação (para updates)

        Returns:
            Allocation conflitante ou None se não houver conflito

        Raises:
            ValueError: Se detectar conflito de alocação
        """
        query = select(Allocation).where(
            Allocation.employee_id == employee_id,
            Allocation.post_id == post_id,
            Allocation.status == AllocationStatus.ACTIVE.value,
            Allocation.is_active.is_(True),
        )

        # Excluir alocação atual em caso de update
        if exclude_allocation_id:
            query = query.where(Allocation.id != exclude_allocation_id)

        result = await self.db.execute(query)
        existing_allocations = list(result.scalars().all())

        # Verificar sobreposição de datas
        for alloc in existing_allocations:
            # Alocação existente sem data fim (indefinida)
            if alloc.end_date is None:
                # Nova alocação começa antes ou durante a existente
                if start_date >= alloc.start_date:
                    return alloc

            # Nova alocação sem data fim
            elif end_date is None:
                # Sobrepõe se a nova começa antes do fim da existente
                if start_date <= alloc.end_date:
                    return alloc

            # Ambas com data fim - verificar sobreposição
            else:
                # Sobreposição: nova começa antes do fim da existente E termina depois do início da existente
                if start_date <= alloc.end_date and end_date >= alloc.start_date:
                    return alloc

        return None

    async def create(self, data: AllocationCreate, created_by: str | None = None) -> Allocation:
        """
        Cria uma nova alocação.

        Args:
            data: Dados da alocação
            created_by: ID do usuário criador

        Returns:
            Allocation criada

        Raises:
            ValueError: Se já existir alocação ativa para o funcionário no posto
        """
        # Validar se já existe alocação ativa
        conflicting = await self.check_active_allocation(
            employee_id=data.employee_id,
            post_id=data.post_id,
            start_date=data.start_date,
            end_date=data.end_date,
        )

        if conflicting:
            raise ValueError(
                f"Funcionário já possui alocação ativa neste posto "
                f"(alocação {conflicting.id}, início: {conflicting.start_date}, "
                f"fim: {conflicting.end_date or 'indefinido'})"
            )

        allocation = Allocation(
            id=str(uuid4()),
            post_id=data.post_id,
            employee_id=data.employee_id,
            status=AllocationStatus.ACTIVE.value,
            start_date=data.start_date,
            end_date=data.end_date,
            is_primary=data.is_primary,
            is_temporary=data.is_temporary,
            setor=getattr(data, "setor", None),
            hourly_rate=data.hourly_rate,
            monthly_salary=data.monthly_salary,
            additional_benefits=data.additional_benefits,
            role=data.role,
            qualifications=data.qualifications,
            notes=data.notes,
            created_by=created_by,
        )

        self.db.add(allocation)
        await self.db.commit()
        await self.db.refresh(allocation)

        # Atualizar contador do posto
        await self._update_post_headcount(allocation.post_id)
        await self.db.commit()

        logger.info(f"Allocation criada: {allocation.id}")
        return allocation

    async def get_by_id(self, allocation_id: str) -> Allocation | None:
        """
        Busca alocação por ID.

        Args:
            allocation_id: ID da alocação

        Returns:
            Allocation ou None
        """
        result = await self.db.execute(
            select(Allocation).where(
                Allocation.id == allocation_id,
                Allocation.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_current_by_employee(self, employee_id: str) -> list[Allocation]:
        """
        Busca alocações atuais de um funcionário.

        Args:
            employee_id: ID do funcionário

        Returns:
            Lista de alocações
        """
        today = date.today()
        result = await self.db.execute(
            select(Allocation).where(
                Allocation.employee_id == employee_id,
                Allocation.status == AllocationStatus.ACTIVE.value,
                Allocation.start_date <= today,
                Allocation.is_active.is_(True),
            )
        )
        allocations = list(result.scalars().all())

        # Filtrar por end_date (pode ser null)
        return [a for a in allocations if a.end_date is None or a.end_date >= today]

    async def get_by_post(self, post_id: str) -> list[Allocation]:
        """
        Busca alocações de um posto.

        Args:
            post_id: ID do posto

        Returns:
            Lista de alocações
        """
        result = await self.db.execute(
            select(Allocation).where(
                Allocation.post_id == post_id,
                Allocation.status == AllocationStatus.ACTIVE.value,
                Allocation.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def list(
        self,
        filters: AllocationFilter | None = None,
        page: int = 1,
        page_size: int = 20,
        include_names: bool = True,
    ) -> tuple[list[dict], int]:
        """
        Lista alocações com filtros e paginação.

        Args:
            filters: Filtros de busca
            page: Página atual
            page_size: Itens por página
            include_names: Se deve incluir nomes de funcionário e posto

        Returns:
            Tupla (alocações com dados enriquecidos, total)
        """
        query = select(Allocation).where(Allocation.is_active.is_(True))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Allocation.id)).where(Allocation.is_active.is_(True))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Allocation.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        allocations = list(result.scalars().all())

        if not include_names:
            return allocations, total

        # Enriquecer com dados de funcionário e posto
        enriched = await self._enrich_allocations(allocations)
        return enriched, total

    async def _enrich_allocations(self, allocations: list[Allocation]) -> list[dict]:
        """
        Enriquece alocações com dados de funcionário e posto.

        Args:
            allocations: Lista de alocações

        Returns:
            Lista de dicts com dados enriquecidos
        """
        if not allocations:
            return []

        # Coletar IDs únicos
        employee_ids = list({str(a.employee_id) for a in allocations if a.employee_id})
        post_ids = list({str(a.post_id) for a in allocations if a.post_id})

        # Buscar funcionários
        employees_map = {}
        if employee_ids:
            emp_result = await self.db.execute(select(Employee).where(Employee.id.in_(employee_ids)))
            for emp in emp_result.scalars().all():
                employees_map[str(emp.id)] = {
                    "name": emp.nome,
                    "matricula": emp.matricula,
                    "cargo": emp.cargo,
                }

        # Buscar postos
        posts_map = {}
        if post_ids:
            post_result = await self.db.execute(select(Post).where(Post.id.in_(post_ids)))
            for post in post_result.scalars().all():
                posts_map[str(post.id)] = {
                    "name": post.name,
                    "code": post.code,
                }

        # Enriquecer dados
        enriched = []
        for alloc in allocations:
            alloc_dict = {
                "id": str(alloc.id),
                "post_id": str(alloc.post_id),
                "employee_id": str(alloc.employee_id),
                "status": alloc.status,
                "start_date": alloc.start_date,
                "end_date": alloc.end_date,
                "is_primary": alloc.is_primary,
                "is_temporary": alloc.is_temporary,
                "hourly_rate": alloc.hourly_rate,
                "monthly_salary": alloc.monthly_salary,
                "additional_benefits": alloc.additional_benefits,
                "role": alloc.role,
                "qualifications": alloc.qualifications,
                "notes": alloc.notes,
                "termination_reason": alloc.termination_reason,
                "is_active": alloc.is_active,
                "created_at": alloc.created_at,
                "updated_at": alloc.updated_at,
                "is_current": alloc.is_current,
                "days_allocated": alloc.days_allocated,
                "total_monthly_cost": alloc.total_monthly_cost,
                # Dados enriquecidos
                "employee_name": employees_map.get(str(alloc.employee_id), {}).get("name"),
                "employee_matricula": employees_map.get(str(alloc.employee_id), {}).get("matricula"),
                "employee_cargo": employees_map.get(str(alloc.employee_id), {}).get("cargo"),
                "post_name": posts_map.get(str(alloc.post_id), {}).get("name"),
                "post_code": posts_map.get(str(alloc.post_id), {}).get("code"),
            }
            enriched.append(alloc_dict)

        return enriched

    def _apply_filters(self, query, filters: AllocationFilter):
        """Aplica filtros à query."""
        if filters.post_id:
            query = query.where(Allocation.post_id == filters.post_id)

        if filters.employee_id:
            query = query.where(Allocation.employee_id == filters.employee_id)

        if filters.status:
            query = query.where(Allocation.status == filters.status.value)

        if filters.is_primary is not None:
            query = query.where(Allocation.is_primary == filters.is_primary)

        if filters.is_temporary is not None:
            query = query.where(Allocation.is_temporary == filters.is_temporary)

        if filters.is_current:
            today = date.today()
            query = query.where(
                and_(
                    Allocation.status == AllocationStatus.ACTIVE.value,
                    Allocation.start_date <= today,
                )
            )

        if filters.start_date_from:
            query = query.where(Allocation.start_date >= filters.start_date_from)

        if filters.start_date_to:
            query = query.where(Allocation.start_date <= filters.start_date_to)

        return query

    async def update(self, allocation_id: str, data: AllocationUpdate) -> Allocation | None:
        """
        Atualiza uma alocação.

        Args:
            allocation_id: ID da alocação
            data: Dados para atualização

        Returns:
            Allocation atualizada ou None

        Raises:
            ValueError: Se houver conflito de alocação
        """
        allocation = await self.get_by_id(allocation_id)
        if not allocation:
            return None

        old_post_id = allocation.post_id
        update_data = data.model_dump(exclude_unset=True)

        # Se está alterando datas ou posto/funcionário, validar conflitos
        if any(field in update_data for field in ["start_date", "end_date", "post_id", "employee_id"]):
            new_employee_id = update_data.get("employee_id", allocation.employee_id)
            new_post_id = update_data.get("post_id", allocation.post_id)
            new_start_date = update_data.get("start_date", allocation.start_date)
            new_end_date = update_data.get("end_date", allocation.end_date)

            conflicting = await self.check_active_allocation(
                employee_id=new_employee_id,
                post_id=new_post_id,
                start_date=new_start_date,
                end_date=new_end_date,
                exclude_allocation_id=allocation_id,
            )

            if conflicting:
                raise ValueError(
                    f"Funcionário já possui alocação ativa neste posto "
                    f"(alocação {conflicting.id}, início: {conflicting.start_date}, "
                    f"fim: {conflicting.end_date or 'indefinido'})"
                )

        for field, value in update_data.items():
            if field == "status" and value:
                setattr(allocation, field, value.value)
            else:
                setattr(allocation, field, value)

        allocation.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(allocation)

        # Atualizar contador do(s) posto(s) afetado(s)
        await self._update_post_headcount(allocation.post_id)
        if old_post_id != allocation.post_id:
            await self._update_post_headcount(old_post_id)
        await self.db.commit()

        logger.info(f"Allocation atualizada: {allocation.id}")
        return allocation

    async def terminate(
        self,
        allocation_id: str,
        end_date: date,
        reason: str,
        notes: str | None = None,
    ) -> Allocation | None:
        """
        Encerra uma alocação.

        Args:
            allocation_id: ID da alocação
            end_date: Data de encerramento
            reason: Motivo
            notes: Observações

        Returns:
            Allocation encerrada ou None
        """
        allocation = await self.get_by_id(allocation_id)
        if not allocation:
            return None

        allocation.status = AllocationStatus.TERMINATED.value
        allocation.end_date = end_date
        allocation.termination_reason = reason
        if notes:
            allocation.notes = f"{allocation.notes or ''}\n[Encerramento] {notes}".strip()
        allocation.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(allocation)

        # Atualizar contador do posto
        await self._update_post_headcount(allocation.post_id)
        await self.db.commit()

        logger.info(f"Allocation encerrada: {allocation.id}")
        return allocation

    async def delete(self, allocation_id: str) -> bool:
        """
        Soft delete de alocação.

        Args:
            allocation_id: ID da alocação

        Returns:
            True se deletada
        """
        allocation = await self.get_by_id(allocation_id)
        if not allocation:
            return False

        post_id = allocation.post_id
        allocation.is_active = False
        allocation.updated_at = datetime.utcnow()

        await self.db.commit()

        # Atualizar contador do posto
        await self._update_post_headcount(post_id)
        await self.db.commit()

        logger.info(f"Allocation deletada (soft): {allocation.id}")
        return True

    async def get_available_employees(
        self,
        shift_date: date | str,
        post_id: str | None = None,  # pylint: disable=unused-argument
    ) -> list[str]:
        """
        Lista funcionários disponíveis em uma data.

        Args:
            shift_date: Data (date ou string ISO "YYYY-MM-DD")
            post_id: ID do posto (opcional, para priorizar)

        Returns:
            Lista de IDs de funcionários disponíveis
        """
        # A data pode chegar como string do query param; comparar str com
        # coluna Date quebra no Postgres ("operator does not exist:
        # date <= character varying"). Converter antes do bind.
        if isinstance(shift_date, str):
            shift_date = date.fromisoformat(shift_date)

        # Disponivel = funcionario ATIVO sem alocacao ativa cobrindo a data.
        # (Antes retornava exatamente os JA alocados, como lista de strings —
        # quebrava o response_model list[dict] e invertia a semantica.)
        result = await self.db.execute(
            sa_text(
                "SELECT e.id::text AS id, e.nome, e.cargo "
                "FROM employees e "
                "WHERE e.status = 'ativo' AND NOT EXISTS ("
                "  SELECT 1 FROM allocations a "
                "  WHERE a.employee_id = e.id "
                "    AND a.status = 'active' AND a.is_active = true "
                "    AND a.start_date <= :shift_date "
                "    AND (a.end_date IS NULL OR a.end_date >= :shift_date)"
                ") ORDER BY e.nome"
            ),
            {"shift_date": shift_date},
        )
        return [dict(row) for row in result.mappings().all()]

    async def bulk_delete(self, allocation_ids: list[str]) -> dict:
        """
        Deleta múltiplas alocações em lote (soft delete).

        Args:
            allocation_ids: Lista de IDs de alocações para deletar

        Returns:
            Dict com:
                - success_count: quantidade de sucessos
                - error_count: quantidade de erros
                - errors: lista de erros [{"id": allocation_id, "error": mensagem}]
        """
        success_count = 0
        error_count = 0
        errors = []

        for allocation_id in allocation_ids:
            try:
                deleted = await self.delete(allocation_id)
                if deleted:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(
                        {
                            "id": allocation_id,
                            "error": "Alocação não encontrada",
                        }
                    )
            except Exception as e:  # pylint: disable=broad-except
                error_count += 1
                errors.append(
                    {
                        "id": allocation_id,
                        "error": str(e),
                    }
                )
                logger.error(
                    "Erro ao deletar alocação em bulk",
                    action="bulk_delete_allocation",
                    allocation_id=allocation_id,
                    error=str(e),
                )

        logger.info(
            "Bulk delete finalizado",
            action="bulk_delete_allocations",
            total=len(allocation_ids),
            success=success_count,
            errors=error_count,
        )

        return {
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }

    async def bulk_update(self, items: list[AllocationBulkUpdateItem]) -> dict:
        """
        Atualiza múltiplas alocações em lote.

        Args:
            items: Lista de itens com allocation_id e dados para atualização

        Returns:
            Dict com:
                - success_count: quantidade de sucessos
                - error_count: quantidade de erros
                - errors: lista de erros [{"id": allocation_id, "error": mensagem}]
        """
        success_count = 0
        error_count = 0
        errors = []

        for item in items:
            try:
                allocation = await self.update(item.allocation_id, item.data)
                if allocation:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(
                        {
                            "id": item.allocation_id,
                            "error": "Alocação não encontrada",
                        }
                    )
            except ValueError as e:
                # Conflito de alocação
                error_count += 1
                errors.append(
                    {
                        "id": item.allocation_id,
                        "error": str(e),
                    }
                )
                logger.warning(
                    "Conflito ao atualizar alocação em bulk",
                    action="bulk_update_allocation",
                    allocation_id=item.allocation_id,
                    error=str(e),
                )
            except Exception as e:  # pylint: disable=broad-except
                error_count += 1
                errors.append(
                    {
                        "id": item.allocation_id,
                        "error": str(e),
                    }
                )
                logger.error(
                    "Erro ao atualizar alocação em bulk",
                    action="bulk_update_allocation",
                    allocation_id=item.allocation_id,
                    error=str(e),
                )

        logger.info(
            "Bulk update finalizado",
            action="bulk_update_allocations",
            total=len(items),
            success=success_count,
            errors=error_count,
        )

        return {
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }
