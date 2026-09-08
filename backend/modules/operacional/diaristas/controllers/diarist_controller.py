"""Controller para endpoints de Diaristas."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.operacional.diaristas.services.diarist_ai_service import DiaristAIService
from modules.operacional.diaristas.services.diarist_service import DiaristService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diaristas", tags=["Diaristas"])


def get_diarist_service(db: Session = Depends(get_db)) -> DiaristService:
    """Dependency para DiaristService."""
    return DiaristService(db)


def get_ai_service(db: Session = Depends(get_db)) -> DiaristAIService:
    """Dependency para DiaristAIService."""
    return DiaristAIService(db)


# ==================== CONSULTA CPF ====================


@router.get("/consulta-cpf/{cpf}")
async def consulta_cpf(
    cpf: str,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Consulta dados pelo CPF: primeiro na base interna, depois API externa."""
    import httpx
    from sqlalchemy import text

    cpf_limpo = cpf.replace(".", "").replace("-", "").replace(" ", "")

    if len(cpf_limpo) != 11 or not cpf_limpo.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CPF invalido",
        )

    # 1. Buscar na base interna (employees)
    try:
        result = await db.execute(
            text("SELECT nome, email, telefone, data_nascimento FROM employees WHERE cpf = :cpf LIMIT 1"),
            {"cpf": cpf_limpo},
        )
        row = result.fetchone()
        if row:
            return {
                "found": True,
                "source": "interno",
                "nome": row[0] or "",
                "email": row[1] or "",
                "telefone": row[2] or "",
                "data_nascimento": str(row[3]) if row[3] else "",
            }
    except Exception as e:
        logger.warning(f"Erro ao buscar employee por CPF: {e}")

    # 2. Buscar na base interna (diarists - evitar duplicata)
    try:
        result = await db.execute(
            text("SELECT nome, email, telefone FROM diarists WHERE cpf = :cpf LIMIT 1"),
            {"cpf": cpf_limpo},
        )
        row = result.fetchone()
        if row:
            return {
                "found": True,
                "source": "diarista_existente",
                "nome": row[0] or "",
                "email": row[1] or "",
                "telefone": row[2] or "",
                "data_nascimento": "",
                "aviso": "CPF ja cadastrado como diarista",
            }
    except Exception as e:
        logger.warning(f"Erro ao buscar diarist por CPF: {e}")

    # 3. Tentar API externa (BrasilAPI)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://brasilapi.com.br/api/cpf/v1/{cpf_limpo}")
            if response.status_code == 200 and (response.json() or {}).get("nome"):  # a BrasilAPI só valida formato: sem nome não é achado (08/09/2026)
                data = response.json()
                return {
                    "found": True,
                    "source": "receita",
                    "nome": data.get("nome", ""),
                    "data_nascimento": data.get("data_nascimento", ""),
                    "situacao": data.get("situacao", ""),
                }
    except Exception as e:
        logger.warning(f"Erro ao consultar API externa: {e}")

    return {"found": False, "nome": "", "message": "CPF nao encontrado"}


# ==================== DIARIST ENDPOINTS (rotas literais primeiro) ====================


# ==================== ASSIGNMENT ENDPOINTS ====================


# ==================== SCHEDULE ENDPOINTS ====================


# ==================== PAYMENT ENDPOINTS ====================


# ==================== EVALUATION ENDPOINTS ====================


# ==================== AI ENDPOINTS ====================


# ==================== STATISTICS ENDPOINTS ====================


# ==================== DIARIST BY ID ENDPOINTS (devem ficar por ultimo) ====================
# IMPORTANTE: Rotas com /{diarist_id} capturam qualquer path.
# Todas as rotas literais (/available, /schedules, /payments, etc.)
# DEVEM ser declaradas ANTES deste bloco.


