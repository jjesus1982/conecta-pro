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


