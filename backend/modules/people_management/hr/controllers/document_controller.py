"""
Controller de Documentos — Departamento Pessoal.

Endpoint de listagem de documentos de funcionários.
Proxy para o módulo GED quando disponível.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["DP - Documentos"])


@router.get(
    "",
    summary="Listar Documentos de Funcionários",
    description="Retorna lista paginada de documentos de funcionários armazenados no GED.",
)
async def list_documents(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """Lista documentos de funcionários."""
    try:
        from sqlalchemy import text

        # Tabela real: hr_employee_documents (o import antigo apontava p/ ged.models.Document inexistente)
        total = (await db.execute(text("SELECT count(*) FROM hr_employee_documents"))).scalar() or 0
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT d.id::text AS id, d.title, d.document_type, d.category, d.status, "
                        "d.file_name, d.file_size, d.created_at, e.nome AS employee_name "
                        "FROM hr_employee_documents d LEFT JOIN employees e ON d.employee_id = e.id "
                        "ORDER BY d.created_at DESC NULLS LAST LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": page_size, "offset": (page - 1) * page_size},
                )
            )
            .mappings()
            .all()
        )
        return {
            "items": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "type": r["document_type"],
                    "category": r["category"],
                    "status": r["status"],
                    "file_name": r["file_name"],
                    "file_size": r["file_size"],
                    "employee_name": r["employee_name"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception:
        return {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 1}
