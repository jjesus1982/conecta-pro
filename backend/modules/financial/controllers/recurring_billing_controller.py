"""
Recurring Billing Controller — Cobrança PIX Recorrente Mensal
Endpoints para geração e consulta de cobranças PIX (cobv) para clientes Conecta Mais.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.auth.dependencies import get_current_user
from starlette.concurrency import run_in_threadpool

# 07/09/2026: as duas rotas passam a emitir NA conta a receber que o gerador do dia 1 já
# cria (Eletrônica → Inter boleto+PIX, Patrimonial → Cora). `gerar_cobrancas_mensais`
# criava contas paralelas a partir de clients.mrr e emitia PIX cobv — nunca foi usada em
# produção (zero contas com cobrança emitida até hoje). Caminhos mantidos; fluxo, um só.
from modules.financial.services.cobranca_recebivel_service import emitir_pendentes_mes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Financial - Cobrança Recorrente PIX"])


@router.get("/cobrar-recorrente/{mes}/{ano}/preview")
async def preview_cobranca_recorrente(
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
):
    """
    Pré-visualiza cobranças do mês/ano sem gerar PIX nem inserir registros.
    Retorna lista de clientes, valores e datas de vencimento.
    """
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mês inválido (1-12)")
    if ano < 2020 or ano > 2100:
        raise HTTPException(status_code=400, detail="Ano inválido")

    try:
        return await run_in_threadpool(emitir_pendentes_mes, ano, mes, True)
    except Exception as exc:
        logger.error("Erro preview cobrança recorrente %02d/%d: %s", mes, ano, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cobrar-recorrente/{mes}/{ano}")
async def cobrar_recorrente(
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
):
    """
    Executa cobrança PIX recorrente para todos os clientes com MRR no mês/ano.
    - Gera PIX cobv (com vencimento) via Banco Inter
    - Insere registros em receivable_accounts
    - Idempotente: clientes já cobrados no período são ignorados
    """
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mês inválido (1-12)")
    if ano < 2020 or ano > 2100:
        raise HTTPException(status_code=400, detail="Ano inválido")

    try:
        return await run_in_threadpool(emitir_pendentes_mes, ano, mes, False)
    except Exception as exc:
        logger.error("Erro cobrança recorrente %02d/%d: %s", mes, ano, exc)
        raise HTTPException(status_code=500, detail=str(exc))
