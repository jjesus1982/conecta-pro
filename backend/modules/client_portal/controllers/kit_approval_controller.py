"""
Controller de Aprovação Digital de Kits do Portal.

Permite que clientes assinem digitalmente a aprovação dos kits mensais,
gerando um registro auditável com IP, timestamp e hash dos documentos.
"""

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kits", tags=["Portal - Aprovação de Kits"])


# ============================================================
# Schemas
# ============================================================


class KitApproveRequest(BaseModel):
    signatory_name: str = Field(..., min_length=3, max_length=200, description="Nome completo do signatário")
    declaration: str = Field(
        default="Declaro que revisei e aprovo todos os documentos deste kit mensal.",
        description="Declaração de aprovação",
    )


class KitApproveResponse(BaseModel):
    approved: bool
    approved_at: datetime
    signature_id: str
    kit_id: str
    message: str


class KitApprovalStatusResponse(BaseModel):
    status: str
    approved_at: datetime | None = None
    approved_by: str | None = None
    signature_id: str | None = None


# ============================================================
# Helpers
# ============================================================


async def _compute_kit_hash(db: AsyncSession, kit_id: str) -> str:
    """Gera hash SHA-256 dos caminhos dos documentos do kit no momento da aprovação."""
    try:
        result = await db.execute(
            text("SELECT COALESCE(file_path, '') FROM ged_kit_documents WHERE kit_id = :kit_id ORDER BY id"),
            {"kit_id": kit_id},
        )
        paths = [row[0] for row in result.fetchall()]
        combined = "|".join(paths)
        return hashlib.sha256(combined.encode()).hexdigest()
    except Exception as exc:
        logger.warning("Falha ao computar hash do kit %s: %s", kit_id, exc)
        return hashlib.sha256(kit_id.encode()).hexdigest()


async def _ensure_approval_table(db: AsyncSession) -> None:
    """Cria tabela de aprovações se não existir."""
    try:
        await db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS client_portal_kit_approvals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    kit_id UUID NOT NULL,
                    client_id TEXT NOT NULL,
                    signatory_name TEXT NOT NULL,
                    declaration TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    document_hash TEXT,
                    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        )
        await db.commit()
    except Exception as exc:
        logger.debug("Tabela kit_approvals já existe ou erro: %s", exc)


# ============================================================
# Endpoints
# ============================================================


@router.post("/{kit_id}/approve", response_model=KitApproveResponse)
async def approve_kit(
    kit_id: str,
    body: KitApproveRequest,
    request: Request,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra aprovação digital do kit mensal."""
    await _ensure_approval_table(db)

    # Verificar que o kit pertence ao cliente e está em status aprovável
    kit_row = await db.execute(
        text("SELECT id, status, reference_month FROM ged_document_kits WHERE id = :kid AND client_id = :cid LIMIT 1"),
        {"kid": kit_id, "cid": client_id},
    )
    kit = kit_row.fetchone()
    if not kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kit não encontrado")

    current_status = str(kit[1]) if kit[1] else ""
    if current_status.lower() == "aprovado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kit já aprovado anteriormente",
        )

    # Calcular hash dos documentos
    doc_hash = await _compute_kit_hash(db, kit_id)
    now = datetime.now(UTC)
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:500]
    sig_id = str(uuid4())

    # Registrar aprovação
    await db.execute(
        text(
            "INSERT INTO client_portal_kit_approvals "
            "(id, kit_id, client_id, signatory_name, declaration, ip_address, user_agent, "
            "approved_at, document_hash, is_valid, created_at) "
            "VALUES (:sig_id, :kid, :cid, :sname, :decl, :ip, :ua, :now, :hash, true, :now)"
        ),
        {
            "sig_id": sig_id,
            "kid": kit_id,
            "cid": client_id,
            "sname": body.signatory_name,
            "decl": body.declaration,
            "ip": ip,
            "ua": ua,
            "now": now,
            "hash": doc_hash,
        },
    )

    # Atualizar status do kit para aprovado
    try:
        await db.execute(
            text("UPDATE ged_document_kits SET status = 'aprovado', updated_at = :now WHERE id = :kid"),
            {"now": now, "kid": kit_id},
        )
    except Exception:
        # Tentar com enum
        try:
            await db.execute(
                text(
                    "UPDATE ged_document_kits SET status = 'APROVADO'::kit_status_enum, "
                    "updated_at = :now WHERE id = :kid"
                ),
                {"now": now, "kid": kit_id},
            )
        except Exception as exc2:
            logger.warning("Falha ao atualizar status do kit: %s", exc2)

    await db.commit()
    logger.info("Kit %s aprovado por %s (IP: %s)", kit_id, body.signatory_name, ip)

    return KitApproveResponse(
        approved=True,
        approved_at=now,
        signature_id=sig_id,
        kit_id=kit_id,
        message=f"Kit aprovado com sucesso por {body.signatory_name}.",
    )


@router.get("/{kit_id}/approval-status", response_model=KitApprovalStatusResponse)
async def get_approval_status(
    kit_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna status de aprovação do kit."""
    # Verificar ownership
    kit_row = await db.execute(
        text("SELECT status FROM ged_document_kits WHERE id = :kid AND client_id = :cid LIMIT 1"),
        {"kid": kit_id, "cid": client_id},
    )
    kit = kit_row.fetchone()
    if not kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kit não encontrado")

    # Buscar registro de aprovação
    try:
        approval = await db.execute(
            text(
                "SELECT id, approved_at, signatory_name FROM client_portal_kit_approvals "
                "WHERE kit_id = :kid AND is_valid = true ORDER BY approved_at DESC LIMIT 1"
            ),
            {"kid": kit_id},
        )
        row = approval.fetchone()
    except Exception:
        row = None

    if row:
        return KitApprovalStatusResponse(
            status="aprovado",
            approved_at=row[1],
            approved_by=row[2],
            signature_id=str(row[0]),
        )

    kit_status = str(kit[0]).lower() if kit[0] else "desconhecido"
    return KitApprovalStatusResponse(status=kit_status)
