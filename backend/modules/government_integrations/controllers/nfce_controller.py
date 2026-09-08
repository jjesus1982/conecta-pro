"""
Controller para NFC-e (Nota Fiscal de Consumidor Eletronica).
Modelo 65 - Vendas ao consumidor final.

Endpoints:
- POST /nfce/emitir - Emite NFC-e
- GET /nfce/consultar/{chave} - Consulta NFC-e por chave
- POST /nfce/cancelar - Cancela NFC-e
- POST /nfce/inutilizar - Inutiliza numeracao
- GET /nfce/status - Status do servico
- POST /nfce/contingencia/transmitir - Transmite NFC-e em contingencia
- GET /nfce/danfe/{chave} - Gera DANFE NFC-e
- GET /nfce/xml/{chave} - Download XML autorizado
- GET /nfce/listar - Lista NFC-e emitidas

Author: Conecta PRO
Date: 2026-01-17
"""

import logging

from fastapi import APIRouter



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfce", tags=["NFC-e - Nota Fiscal Consumidor"])


