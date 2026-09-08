"""Enrichment endpoints (CNPJ, CEP, Taxas) via BrasilAPI proxy."""

import time

from fastapi import APIRouter, HTTPException, Response
from loguru import logger

from core.auth.dependencies import CurrentActiveUser
from modules.integrations.brasilapi.client import BrasilAPIClient
from modules.integrations.brasilapi.exceptions import (
    BrasilAPIInvalidFormatError,
    BrasilAPINotFoundError,
    BrasilAPIUnavailableError,
)

from ..schemas.enrichment import (
    CEPEnrichment,
    CNPJEnrichment,
)

router = APIRouter(prefix="/enrichment", tags=["CRM - Enrichment"])
_client = BrasilAPIClient()


@router.get("/cnpj/{cnpj}", response_model=CNPJEnrichment)
async def enrich_cnpj(
    cnpj: str,
    response: Response,
    current_user: CurrentActiveUser,
):
    t0 = time.monotonic()
    try:
        data, cache_hit = await _client.get_cnpj(cnpj)
    except BrasilAPIInvalidFormatError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BrasilAPINotFoundError:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado na Receita Federal")
    except BrasilAPIUnavailableError:
        raise HTTPException(status_code=503, detail="Serviço temporariamente indisponível")

    latency_ms = (time.monotonic() - t0) * 1000
    logger.info(f"enrichment cnpj={cnpj} cache_hit={cache_hit} latency_ms={latency_ms:.0f}")
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"

    cnae_principal = None
    if data.cnae_fiscal and data.cnae_fiscal_descricao:
        cnae_principal = f"{data.cnae_fiscal} - {data.cnae_fiscal_descricao}"

    cnaes_sec = []
    for s in data.cnae_fiscal_secundario or []:
        codigo = s.get("codigo") or s.get("cnae")
        descricao = s.get("descricao")
        if codigo and descricao:
            cnaes_sec.append(f"{codigo} - {descricao}")

    return CNPJEnrichment(
        cnpj=data.cnpj,
        razao_social=data.razao_social,
        nome_fantasia=data.nome_fantasia,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_sec,
        qsa=[m.model_dump() for m in data.qsa],
        capital_social=data.capital_social,
        situacao=str(data.descricao_situacao_cadastral or data.situacao_cadastral)
        if (data.descricao_situacao_cadastral or data.situacao_cadastral) is not None
        else None,
        endereco={
            "logradouro": data.logradouro,
            "numero": data.numero,
            "complemento": data.complemento,
            "bairro": data.bairro,
            "municipio": data.municipio,
            "uf": data.uf,
            "cep": data.cep,
        },
        telefone=data.ddd_telefone_1,
        porte=data.porte,
        data_abertura=data.data_inicio_atividade,
        simples_nacional=data.opcao_pelo_simples,
        cache_hit=cache_hit,
    )


@router.get("/cep/{cep}", response_model=CEPEnrichment)
async def enrich_cep(
    cep: str,
    response: Response,
    current_user: CurrentActiveUser,
):
    t0 = time.monotonic()
    try:
        data, cache_hit = await _client.get_cep(cep)
    except BrasilAPIInvalidFormatError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BrasilAPINotFoundError:
        raise HTTPException(status_code=404, detail="CEP não encontrado")
    except BrasilAPIUnavailableError:
        raise HTTPException(status_code=503, detail="Serviço temporariamente indisponível")

    latency_ms = (time.monotonic() - t0) * 1000
    logger.info(f"enrichment cep={cep} cache_hit={cache_hit} latency_ms={latency_ms:.0f}")
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"

    coordenadas = None
    if data.location and data.location.coordinates:
        coordenadas = {
            "latitude": data.location.coordinates.latitude,
            "longitude": data.location.coordinates.longitude,
        }

    return CEPEnrichment(
        cep=data.cep,
        logradouro=data.street,
        bairro=data.neighborhood,
        cidade=data.city,
        uf=data.state,
        coordenadas=coordenadas,
        cache_hit=cache_hit,
    )


