"""
GED Certidões Controller.

Endpoints:
- GET    /certidoes          → listar certidões da empresa com status calculado
- POST   /certidoes          → adicionar nova certidão
- GET    /certidoes/tipos    → listar tipos de CND disponíveis para sync
- POST   /certidoes/sync     → disparar sync de todas as CNDs
- POST   /certidoes/sync/{param} → sync por tipo ou CNPJ
- PUT    /certidoes/{id}     → renovar/atualizar certidão
- DELETE /certidoes/{id}     → remover certidão
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GED - Certidões"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CertidaoCreate(BaseModel):
    name: str
    document_type: str
    issuing_body: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    file_path: str | None = None
    file_url: str | None = None
    notes: str | None = None
    alerta_ativo: bool = False


class CertidaoUpdate(BaseModel):
    name: str | None = None
    document_type: str | None = None
    issuing_body: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    file_path: str | None = None
    file_url: str | None = None
    notes: str | None = None
    observacao: str | None = None  # alias de notes (compatibilidade com prompt)
    alerta_ativo: bool | None = None


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _calcular_status(expiry_date: date | None) -> str:
    if expiry_date is None:
        return "sem_vencimento"
    hoje = date.today()
    if expiry_date < hoje:
        return "vencida"
    if expiry_date < hoje + timedelta(days=30):
        return "a_vencer"
    return "valida"


def _row_to_dict(row: Any) -> dict:
    expiry = row["expiry_date"]
    issue = row["issue_date"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "document_type": row["document_type"],
        "issuing_body": row["issuing_body"],
        "issue_date": issue.isoformat() if issue else None,
        "expiry_date": expiry.isoformat() if expiry else None,
        "status": _calcular_status(expiry),
        "file_path": row["file_path"],
        "file_url": row["file_url"],
        "notes": row["notes"],
        "alerta_ativo": bool(row["alerta_ativo"]) if row["alerta_ativo"] is not None else False,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/certidoes")
async def listar_certidoes(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista todas as certidões da empresa com status calculado automaticamente."""
    result = await db.execute(
        text("""
        SELECT id, name, document_type, issuing_body,
               issue_date, expiry_date, file_path, file_url, notes,
               alerta_ativo, created_at, updated_at
        FROM ged_certidoes
        ORDER BY expiry_date ASC NULLS LAST
        """)
    )
    rows = result.mappings().all()
    certidoes = [_row_to_dict(r) for r in rows]

    validas = sum(1 for c in certidoes if c["status"] == "valida")
    vencidas = sum(1 for c in certidoes if c["status"] == "vencida")
    a_vencer = sum(1 for c in certidoes if c["status"] == "a_vencer")

    return {
        "certidoes": certidoes,
        "total": len(certidoes),
        "resumo": {
            "validas": validas,
            "vencidas": vencidas,
            "a_vencer_30d": a_vencer,
        },
        "gerado_em": datetime.now().isoformat(),
    }


@router.post("/certidoes", status_code=201)
async def criar_certidao(
    payload: CertidaoCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adiciona nova certidão."""
    new_id = uuid4()
    await db.execute(
        text("""
        INSERT INTO ged_certidoes
          (id, name, document_type, issuing_body, issue_date, expiry_date,
           file_path, file_url, notes, alerta_ativo, created_at, updated_at)
        VALUES
          (:id, :name, :document_type, :issuing_body, :issue_date, :expiry_date,
           :file_path, :file_url, :notes, :alerta_ativo, NOW(), NOW())
        """),
        {
            "id": str(new_id),
            "name": payload.name,
            "document_type": payload.document_type,
            "issuing_body": payload.issuing_body,
            "issue_date": payload.issue_date,
            "expiry_date": payload.expiry_date,
            "file_path": payload.file_path,
            "file_url": payload.file_url,
            "notes": payload.notes,
            "alerta_ativo": payload.alerta_ativo,
        },
    )
    await db.commit()
    return {"id": str(new_id), "message": "Certidão criada com sucesso."}


# IMPORTANTE: rotas específicas (/tipos, /sync, /sync/{param}) DEVEM vir
# antes de /{certidao_id} para evitar que FastAPI capture o path como ID.


@router.options("/certidoes/{certidao_id}", include_in_schema=False)
async def options_certidao(certidao_id: str):
    """Retorna métodos permitidos para /{certidao_id}."""
    from starlette.responses import Response

    return Response(status_code=200, headers={"Allow": "DELETE, GET, OPTIONS, PUT"})


@router.get("/certidoes/{certidao_id}")
async def obter_certidao(
    certidao_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna uma certidão pelo ID."""
    result = await db.execute(
        text("""
        SELECT id, name, document_type, issuing_body,
               issue_date, expiry_date, file_path, file_url, notes,
               alerta_ativo, created_at, updated_at
        FROM ged_certidoes
        WHERE id = :id
        """),
        {"id": certidao_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": "CERTIDAO_NOT_FOUND", "message": f"Certidão '{certidao_id}' não encontrada."},
        )
    return _row_to_dict(row)


@router.put("/certidoes/{certidao_id}")
async def atualizar_certidao(
    certidao_id: str,
    payload: CertidaoUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Renova ou atualiza uma certidão existente."""
    # Verificar existência
    check = await db.execute(
        text("SELECT id FROM ged_certidoes WHERE id = :id"),
        {"id": certidao_id},
    )
    if not check.fetchone():
        raise HTTPException(
            status_code=404,
            detail={"code": "CERTIDAO_NOT_FOUND", "message": f"Certidão '{certidao_id}' não encontrada."},
        )

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    # observacao é alias de notes — mapear antes de montar SQL
    if "observacao" in updates:
        if "notes" not in updates:
            updates["notes"] = updates.pop("observacao")
        else:
            updates.pop("observacao")
    if not updates:
        raise HTTPException(status_code=422, detail={"code": "NO_FIELDS", "message": "Nenhum campo para atualizar."})

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["certidao_id"] = certidao_id
    await db.execute(
        text(f"UPDATE ged_certidoes SET {set_clause}, updated_at = NOW() WHERE id = :certidao_id"),
        updates,
    )
    await db.commit()
    return {"id": certidao_id, "message": "Certidão atualizada com sucesso."}


@router.delete("/certidoes/{certidao_id}", status_code=200)
async def remover_certidao(
    certidao_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Remove uma certidão."""
    check = await db.execute(
        text("SELECT id FROM ged_certidoes WHERE id = :id"),
        {"id": certidao_id},
    )
    if not check.fetchone():
        raise HTTPException(
            status_code=404,
            detail={"code": "CERTIDAO_NOT_FOUND", "message": f"Certidão '{certidao_id}' não encontrada."},
        )

    await db.execute(
        text("DELETE FROM ged_certidoes WHERE id = :id"),
        {"id": certidao_id},
    )
    await db.commit()
    return {"message": "Certidão removida com sucesso."}
