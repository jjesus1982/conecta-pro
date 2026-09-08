"""
Repository para operações de banco de dados com ScaleTemplate.
"""

import builtins
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.models.scale_template import ScaleTemplate
from modules.operacional.schemas.scale_template import (
    ScaleTemplateCreate,
    ScaleTemplateUpdate,
)


class ScaleTemplateRepository:
    """Repository para operações CRUD de ScaleTemplate."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        data: ScaleTemplateCreate,
        tenant_id: str,
        created_by: str,
    ) -> ScaleTemplate:
        """
        Cria um novo template de escala.

        Args:
            data: Dados do template
            tenant_id: ID do tenant
            created_by: ID do usuário criador

        Returns:
            ScaleTemplate criado
        """
        template = ScaleTemplate(
            id=str(uuid4()),
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            template_data=data.template_data.model_dump(),
            created_by=created_by,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"ScaleTemplate criado: {template.id} - {template.name}")
        return template

    async def get_by_id(
        self,
        template_id: str,
        tenant_id: str | None = None,
    ) -> ScaleTemplate | None:
        """
        Busca template por ID.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant (para validação)

        Returns:
            ScaleTemplate ou None
        """
        query = select(ScaleTemplate).where(
            ScaleTemplate.id == template_id,
            ScaleTemplate.is_active.is_(True),
        )

        if tenant_id:
            query = query.where(ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> tuple[list[ScaleTemplate], int]:
        """
        Lista templates com paginação.

        Args:
            tenant_id: ID do tenant
            skip: Offset para paginação
            limit: Limite de resultados
            include_inactive: Se deve incluir inativos

        Returns:
            Tupla (templates, total)
        """
        query = select(ScaleTemplate).where(ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]))

        if not include_inactive:
            query = query.where(ScaleTemplate.is_active.is_(True))

        # Count total
        count_query = select(func.count(ScaleTemplate.id)).where(ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]))
        if not include_inactive:
            count_query = count_query.where(ScaleTemplate.is_active.is_(True))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(ScaleTemplate.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    async def update(
        self,
        template_id: str,
        data: ScaleTemplateUpdate,
        tenant_id: str,
    ) -> ScaleTemplate | None:
        """
        Atualiza um template.

        Args:
            template_id: ID do template
            data: Dados para atualização
            tenant_id: ID do tenant (validação)

        Returns:
            ScaleTemplate atualizado ou None
        """
        template = await self.get_by_id(template_id, tenant_id)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "template_data" and value:
                setattr(template, field, value.model_dump())
            else:
                setattr(template, field, value)

        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"ScaleTemplate atualizado: {template.id}")
        return template

    async def delete(self, template_id: str, tenant_id: str) -> bool:
        """
        Soft delete de template.

        Args:
            template_id: ID do template
            tenant_id: ID do tenant (validação)

        Returns:
            True se deletado
        """
        template = await self.get_by_id(template_id, tenant_id)
        if not template:
            return False

        template.is_active = False
        template.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"ScaleTemplate deletado (soft): {template.id}")
        return True

    async def increment_usage(self, template_id: str) -> ScaleTemplate | None:
        """
        Incrementa contador de uso do template.

        Args:
            template_id: ID do template

        Returns:
            ScaleTemplate atualizado ou None
        """
        template = await self.get_by_id(template_id)
        if not template:
            return None

        template.times_used += 1
        template.last_used = datetime.utcnow()
        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"ScaleTemplate uso incrementado: {template.id} ({template.times_used}x)")
        return template

    async def get_most_used(
        self,
        tenant_id: str,
        limit: int = 5,
    ) -> builtins.list[ScaleTemplate]:
        """
        Retorna templates mais usados.

        Args:
            tenant_id: ID do tenant
            limit: Limite de resultados

        Returns:
            Lista de templates
        """
        query = (
            select(ScaleTemplate)
            .where(
                ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]),
                ScaleTemplate.is_active.is_(True),
                ScaleTemplate.times_used > 0,
            )
            .order_by(ScaleTemplate.times_used.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recently_created(
        self,
        tenant_id: str,
        limit: int = 5,
    ) -> builtins.list[ScaleTemplate]:
        """
        Retorna templates criados recentemente.

        Args:
            tenant_id: ID do tenant
            limit: Limite de resultados

        Returns:
            Lista de templates
        """
        query = (
            select(ScaleTemplate)
            .where(
                ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]),
                ScaleTemplate.is_active.is_(True),
            )
            .order_by(ScaleTemplate.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_stats(self, tenant_id: str) -> dict:
        """
        Retorna estatísticas de templates.

        Args:
            tenant_id: ID do tenant

        Returns:
            Dict com estatísticas
        """
        # Total de templates ativos
        active_result = await self.db.execute(
            select(func.count(ScaleTemplate.id)).where(
                ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]),
                ScaleTemplate.is_active.is_(True),
            )
        )
        active = active_result.scalar() or 0

        # Total de templates inativos
        inactive_result = await self.db.execute(
            select(func.count(ScaleTemplate.id)).where(
                ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]),
                ScaleTemplate.is_active.is_(False),
            )
        )
        inactive = inactive_result.scalar() or 0

        # Média de uso
        avg_result = await self.db.execute(
            select(func.avg(ScaleTemplate.times_used)).where(
                ScaleTemplate.tenant_id.in_([tenant_id, "00000000-0000-0000-0000-000000000000"]),
                ScaleTemplate.is_active.is_(True),
            )
        )
        avg_usage = float(avg_result.scalar() or 0)

        return {
            "total": active + inactive,
            "active": active,
            "inactive": inactive,
            "avg_usage": avg_usage,
        }
