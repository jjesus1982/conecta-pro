"""Controllers para o módulo de Estoque."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["Estoque"])


# =============================================================================
# Warehouse Endpoints
# =============================================================================


# =============================================================================
# StockItem Endpoints
# =============================================================================


# =============================================================================
# StockMovement Endpoints
# =============================================================================


# =============================================================================
# StockInventory Endpoints
# =============================================================================


# =============================================================================
# StockReservation Endpoints
# =============================================================================


# =============================================================================
# Estoque REAL (NF-e de entrada → nfe_compras_estoque) + Saída com COGS
# =============================================================================
from pydantic import BaseModel  # noqa: E402

from modules.financial.services.estoque_real_service import EstoqueRealService  # noqa: E402

_estoque_real = EstoqueRealService()


class SaidaEstoquePayload(BaseModel):
    item_code: str
    quantidade: float
    servico_ref: str | None = None
    motivo: str | None = None
    nfse_id: str | None = None


@router.get("/real/itens")
async def estoque_real_itens(
    busca: str | None = Query(None, description="Busca por descrição ou código"),
    _current_user: dict = Depends(get_current_user),
) -> list:
    """Estoque REAL a partir das NF-e de entrada (nfe_compras_estoque)."""
    return _estoque_real.listar_itens(busca)


@router.get("/real/resumo")
async def estoque_real_resumo(_current_user: dict = Depends(get_current_user)) -> dict:
    """Totais do estoque real: itens, valor, unidades, saídas do mês."""
    return _estoque_real.resumo()


@router.get("/real/movimentos")
async def estoque_real_movimentos(
    limite: int = Query(100, ge=1, le=500),
    _current_user: dict = Depends(get_current_user),
) -> list:
    """Histórico de movimentos (saídas com vínculo a serviço)."""
    return _estoque_real.listar_movimentos(limite)


@router.post("/real/saida")
async def estoque_real_saida(
    payload: SaidaEstoquePayload,
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Baixa de material vinculada a serviço/NFS-e: reduz saldo + posta COGS no razão."""
    try:
        return _estoque_real.registrar_saida(
            item_code=payload.item_code,
            quantidade=payload.quantidade,
            servico_ref=payload.servico_ref,
            motivo=payload.motivo,
            nfse_id=payload.nfse_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
