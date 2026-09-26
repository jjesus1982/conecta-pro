"""Rota da EFD Contribuições (SPED PIS/COFINS)."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core.auth.dependencies import CurrentActiveUser

from ..services.sped_contribuicoes_service import (
    DispensadaDaEFDError,
    RegimeNaoDeclaradoError,
    SPEDContribuicoesService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sped-contribuicoes", tags=["SPED EFD Contribuições"])


class GerarContribuicoesRequest(BaseModel):
    periodo_inicio: date = Field(..., description="Primeiro dia da competência")
    periodo_fim: date = Field(..., description="Último dia da competência")
    empresa_slug: str | None = Field(None, description="Qual CNPJ escriturar")


@router.get("/status", summary="Regime de PIS/COFINS e o que o gerador sabe escriturar")
async def status_contribuicoes(current_user: CurrentActiveUser, empresa_slug: str | None = None):
    try:
        s = SPEDContribuicoesService(empresa_slug=empresa_slug)
    except DispensadaDaEFDError as e:
        return {"pronto": False, "dispensada": True, "motivo": str(e)}
    except RegimeNaoDeclaradoError as e:
        return {"pronto": False, "dispensada": False, "motivo": str(e)}
    return {
        "pronto": True,
        "cnpj": s.cnpj,
        "empresa": s.razao_social,
        "regime": s.regime,
        "fonte_do_regime": s.regime_fonte,
        "aliquotas": {"pis": 0.65, "cofins": 3.00},
        "observacao": (
            "Lucro Real NÃO implica não-cumulativo: vigilância e transporte de valores "
            "ficam no cumulativo pelo art. 10 da Lei 10.833/2003."
        ),
    }


@router.post(
    "/gerar",
    summary="Gera a EFD Contribuições (PIS/COFINS) do período",
    description=(
        "Escritura as NFS-e REAIS e autorizadas do CNPJ no período, no regime declarado "
        "para ele. Nota cancelada entra no arquivo com COD_SIT 02 e **fica fora da base** "
        "— somar cancelada é recolher sobre faturamento que não houve.\n\n"
        "Mês sem nota gera arquivo sem documento, que é a verdade.\n\n"
        "O arquivo NÃO vem assinado nem transmitido, e o registro 0100 (contabilista) sai "
        "ausente enquanto não houver CRC cadastrado."
    ),
)
async def gerar_contribuicoes(
    payload: GerarContribuicoesRequest,
    current_user: CurrentActiveUser,
    formato: str = Query("json", pattern="^(json|txt)$"),
):
    if payload.periodo_fim < payload.periodo_inicio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="período invertido: o fim é anterior ao início",
        )
    try:
        # Instância por requisição: o manager acumula documentos, e reaproveitá-lo somaria
        # o período de uma geração na seguinte.
        service = SPEDContribuicoesService(empresa_slug=payload.empresa_slug)
        resultado = service.gerar_arquivo(payload.periodo_inicio, payload.periodo_fim)
    except (DispensadaDaEFDError, RegimeNaoDeclaradoError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("Erro ao gerar EFD Contribuições: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar EFD Contribuições: {e}",
        ) from e

    if formato == "txt":
        nome = f"EFD-Contribuicoes-{service.cnpj}-{payload.periodo_inicio:%Y%m}.txt"
        return PlainTextResponse(
            resultado["conteudo"],
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    return resultado
