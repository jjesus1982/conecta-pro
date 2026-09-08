"""
Serviço de Medidas Disciplinares — Departamento Pessoal.

Re-exporta funcionalidades do módulo operacional de disciplinares
e adiciona métodos DP: histórico por funcionário e criação a partir
de ocorrência.
"""

import contextlib
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Re-export do serviço existente
try:
    from modules.operacional.disciplinary.services import (
        DisciplinaryService as OperacionalDisciplinaryService,
    )
except ImportError:
    OperacionalDisciplinaryService = None  # type: ignore[assignment, misc]

try:
    from modules.operacional.disciplinary.models import DisciplinaryAction
except ImportError:
    DisciplinaryAction = None  # type: ignore[assignment, misc]


class DisciplineService:
    """Serviço de Medidas Disciplinares — visão DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._operacional_service = None
        if OperacionalDisciplinaryService:
            with contextlib.suppress(Exception):
                self._operacional_service = OperacionalDisciplinaryService(db)

    async def get_employee_history(
        self,
        employee_id: str | UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Retorna histórico disciplinar completo de um funcionário.

        Args:
            employee_id: ID do funcionário.
            page: Página atual.
            page_size: Itens por página.

        Returns:
            Dicionário com items, total, page, page_size, total_pages.
        """
        if not DisciplinaryAction:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 1,
                "message": "Módulo disciplinar não disponível",
            }

        from sqlalchemy import func

        query = select(DisciplinaryAction).where(DisciplinaryAction.employee_id == str(employee_id))
        count_query = (
            select(func.count())
            .select_from(DisciplinaryAction)
            .where(DisciplinaryAction.employee_id == str(employee_id))
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        query = query.order_by(DisciplinaryAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": list(items),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

