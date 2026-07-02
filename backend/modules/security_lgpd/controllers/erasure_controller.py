"""
Controller de Exclusao de Dados (Direito ao Esquecimento) LGPD.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_sync_db_dependency
from modules.security_lgpd.repositories.erasure_repository import ErasureRepository
from modules.security_lgpd.schemas.common import StandardResponse
from modules.security_lgpd.schemas.erasure import ErasureRequestSchema
from modules.security_lgpd.services.erasure_service import ErasureError, ErasureService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/erasure", tags=["LGPD - Direito ao Esquecimento"])


def get_erasure_service(db: Session = Depends(get_sync_db_dependency)) -> ErasureService:
    """Injeta um ErasureService com repository ligado a sessao de banco."""
    return ErasureService(repository=ErasureRepository(db))


@router.post(
    "/request",
    response_model=StandardResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicita exclusao de dados (Art. 18 LGPD)",
    description="Inicia processo de exclusao de dados do titular.",
)
async def request_erasure(
    current_user: CurrentActiveUser,
    request: ErasureRequestSchema,
    service: ErasureService = Depends(get_erasure_service),
) -> StandardResponse:
    """
    Solicita exclusao de dados (direito ao esquecimento).

    Args:
        request: Dados da solicitacao.

    Returns:
        StandardResponse: Confirmacao da solicitacao.
    """
    try:
        result = service.create_request(
            titular_id=str(request.titular_id),
            titular_email=request.titular_email,
            reason=request.reason,
            scope=request.scope,
        )

        logger.info(
            "Solicitacao de exclusao criada: titular=%s, escopo=%s",
            request.titular_id,
            request.scope,
        )

        return StandardResponse(
            success=True,
            message="Solicitacao de exclusao registrada. Processamento em ate 15 dias.",
            data=result,
        )

    except Exception as e:
        logger.error("Erro ao criar solicitacao de exclusao: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar solicitacao",
        )


@router.get(
    "/{request_id}/status",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta status de exclusao",
    description="Verifica status de uma solicitacao de exclusao.",
)
async def get_erasure_status(
    current_user: CurrentActiveUser,
    request_id: str = Path(..., description="ID da solicitacao"),
    service: ErasureService = Depends(get_erasure_service),
) -> StandardResponse:
    """
    Consulta status de solicitacao de exclusao.

    Args:
        request_id: ID da solicitacao.

    Returns:
        StandardResponse: Status atual.
    """
    try:
        status_info = service.get_status(request_id)

        return StandardResponse(
            success=True,
            message="Status da solicitacao recuperado",
            data=status_info,
        )

    except (ValueError, ErasureError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitacao nao encontrada",
        )
    except Exception as e:
        logger.error("Erro ao consultar status: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar status",
        )


@router.post(
    "/{request_id}/processar",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Processa solicitacao de exclusao (Art. 18 LGPD)",
    description=(
        "Processa uma solicitacao. Sem 'confirmar' (padrao SEGURO): marca EM PROCESSAMENTO "
        "(nao apaga nada). Com 'confirmar=true': EXECUTA a anonimizacao real da PII do titular "
        "(employees/clients/users) e conclui, retornando o total de registros afetados. "
        "A execucao com confirmar=true e destrutiva e deve passar por autorizacao/auditoria."
    ),
)
async def processar_erasure(
    current_user: CurrentActiveUser,
    request_id: str = Path(..., description="ID da solicitacao"),
    confirmar: bool = False,
    service: ErasureService = Depends(get_erasure_service),
) -> StandardResponse:
    """Marca em processamento (confirmar=False) ou executa a anonimizacao real (confirmar=True)."""
    try:
        result = service.process_request(
            request_id=request_id,
            processor_id=str(getattr(current_user, "id", "sistema")),
            confirmar=confirmar,
        )
        msg = (
            "Anonimizacao executada e solicitacao concluida."
            if confirmar
            else "Solicitacao em processamento (execucao real requer confirmar=true)."
        )
        logger.info("Erasure processar: request=%s confirmar=%s", request_id, confirmar)
        return StandardResponse(success=True, message=msg, data=result)
    except (ValueError, ErasureError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitacao nao encontrada")
    except Exception as e:  # noqa: BLE001
        logger.error("Erro ao processar exclusao: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar exclusao",
        )
