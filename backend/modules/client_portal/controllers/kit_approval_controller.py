"""
Controller de Aprovação Digital de Kits do Portal.

Permite que clientes assinem digitalmente a aprovação dos kits mensais,
gerando um registro auditável com IP, timestamp e hash dos documentos.
"""

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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


