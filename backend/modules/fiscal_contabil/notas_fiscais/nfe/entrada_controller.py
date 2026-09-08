"""
NF-e Entrada Controller
Upload e consulta de NF-e recebidas (compras) + estoque virtual.

Endpoints:
  POST /nfe-entrada/upload-xml   — faz upload de XML e atualiza estoque
  GET  /nfe-entrada/listar       — lista NF-e de compra recebidas
  GET  /nfe-entrada/estoque      — exibe estoque virtual de compras
  POST /nfe-entrada/sync-sefaz   — consulta SEFAZ e importa novas NF-e
"""

import logging
import os

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/nfe-entrada", tags=["NF-e Entrada/Compras"])

logger = logging.getLogger(__name__)

CNPJ_EMPRESA = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")


def _get_conn():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    return psycopg2.connect(url)


# --------------------------------------------------------------------------- #
#  POST /nfe-entrada/upload-xml                                                #
# --------------------------------------------------------------------------- #


@router.post("/upload-xml", summary="Upload XML de NF-e de compra — atualiza estoque")
async def upload_xml_nfe(arquivo: UploadFile = File(...)):
    """
    Recebe XML de NF-e de compra emitida por fornecedor.
    Salva em disco e atualiza o estoque virtual automaticamente.
    """
    from modules.government_integrations.services.nfe_entrada_sync_service import (
        NFEEntradaSyncService,
    )

    if not (arquivo.filename or "").endswith(".xml"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser XML")

    conteudo = await arquivo.read()
    xml_str = conteudo.decode("utf-8", errors="ignore")

    # Salvar XML em disco
    pasta = os.getenv("NFE_UPLOADS_DIR", "/tmp/nfe/entrada")  # nosec B108
    os.makedirs(pasta, exist_ok=True)
    xml_path = f"{pasta}/{arquivo.filename}"
    with open(xml_path, "wb") as f:
        f.write(conteudo)

    svc = NFEEntradaSyncService()
    conn = _get_conn()
    try:
        resultado = svc.processar_xml_nfe(xml_str, conn)
    except Exception as exc:
        logger.error("Erro ao processar XML NF-e: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()

    if "erro" in resultado:
        raise HTTPException(status_code=422, detail=resultado.get("erro", "Erro desconhecido"))

    return {"arquivo_salvo": xml_path, "processamento": resultado}


# --------------------------------------------------------------------------- #
#  GET /nfe-entrada/listar                                                     #
# --------------------------------------------------------------------------- #


@router.post("/sync-sefaz", summary="Sincronizar NF-e entrada via SEFAZ")
async def sync_sefaz_entrada(ultimo_nsu: str = "0"):
    """Consulta NF-e distribuição no SEFAZ-AM."""
    from modules.government_integrations.services.nfe_entrada_sync_service import (
        NFEEntradaSyncService,
    )

    svc = NFEEntradaSyncService()
    resultado = svc.buscar_nfe_recebidas(ultimo_nsu)
    return resultado
