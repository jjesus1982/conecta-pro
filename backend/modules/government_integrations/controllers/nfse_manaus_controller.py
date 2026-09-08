"""
Controller para NFS-e Manaus.

Endpoints REST para emissão, consulta e cancelamento de NFS-e.
Prefeitura de Manaus - Padrão ABRASF 2.04
"""

import logging

from fastapi import APIRouter



logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfse-manaus", tags=["NFS-e Manaus"])


