"""
Controller de Documentos — Departamento Pessoal.

Endpoint de listagem de documentos de funcionários.

FONTE-DA-VERDADE UNIFICADA (2026-07-10):
A tela dp/documentos fazia UPLOAD em ``ged_documents`` (via /ged/documents/upload)
mas LIA de ``hr_employee_documents`` — fontes divergentes, então o que era enviado
nunca aparecia na lista. Decisão: unificar a LEITURA como UNION das duas tabelas,
preservando as 15 linhas legadas de hr_employee_documents E todo upload novo em
ged_documents. Não movemos o upload (endpoint GED compartilhado) — só ampliamos a
leitura. O lado ged_documents é escopado à pasta "Funcionários", a docs vinculados
a employee_id, ou à categoria RH, ignorando soft-deletados.
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
    """Lista documentos de funcionários (UNION hr_employee_documents + ged_documents)."""
    try:
        from sqlalchemy import text

        # Pasta "Funcionários" do GED — destino dos uploads da tela dp/documentos.
        ged_funcionarios_folder = "abcbebd2-88af-419e-8907-43b11f38f90b"

        # Subquery unificada: docs do DP (hr_employee_documents) + docs do GED
        # escopados a funcionários (pasta Funcionários OU employee_id OU categoria rh),
        # sem soft-deletados. valid_until exposto p/ a data de validade.
        union_sql = (
            "SELECT d.id::text AS id, d.title, d.document_type, d.category, d.status, "
            "d.file_name, d.file_size, d.valid_until, d.created_at, d.employee_id, 'dp' AS source "
            "FROM hr_employee_documents d "
            "UNION ALL "
            "SELECT g.id::text AS id, g.title, g.document_type, g.category, g.status, "
            "g.file_name, g.file_size_bytes AS file_size, g.valid_until, g.created_at, g.employee_id, 'ged' AS source "
            "FROM ged_documents g "
            "WHERE g.deleted_at IS NULL "
            "AND (g.folder_id = :ged_folder OR g.employee_id IS NOT NULL OR lower(g.category) = 'rh')"
        )

        total = (
            await db.execute(
                text(f"SELECT count(*) FROM ({union_sql}) u"),
                {"ged_folder": ged_funcionarios_folder},
            )
        ).scalar() or 0

        rows = (
            (
                await db.execute(
                    text(
                        f"SELECT u.*, e.nome AS employee_name "
                        f"FROM ({union_sql}) u "
                        "LEFT JOIN employees e ON u.employee_id = e.id "
                        "ORDER BY u.created_at DESC NULLS LAST LIMIT :limit OFFSET :offset"
                    ),
                    {
                        "ged_folder": ged_funcionarios_folder,
                        "limit": page_size,
                        "offset": (page - 1) * page_size,
                    },
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
                    "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
                    "employee_name": r["employee_name"],
                    "source": r["source"],
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
        logger.exception("Erro ao listar documentos DP (union hr+ged)")
        return {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 1}
