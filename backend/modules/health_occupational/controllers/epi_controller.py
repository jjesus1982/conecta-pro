"""
Controller EPI (NR-6) - Equipamentos de Protecao Individual
============================================================

Endpoints REST para gestao de EPIs.
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_sync_db_dependency
from modules.health_occupational.publishers import publish_epi_entregue
from modules.health_occupational.schemas.common import StandardResponse
from modules.health_occupational.schemas.epi import (
    EPICreateRequest,
    EPIDeliveryRequest,
    EPIDeliveryResponse,
    EPIDeliveryUpdateRequest,
    EPIInventoryResponse,
    EPIInventoryUpdateRequest,
    EPIResponse,
    EPIUpdateRequest,
)
from modules.health_occupational.services.epi_service import EPIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/epi", tags=["EPI - Equipamentos de Protecao (NR-6)"])


# Dependency para obter o service com DB session
def get_epi_service(db: Session = Depends(get_sync_db_dependency)) -> EPIService:
    """Retorna instancia do EPIService com DB session."""
    return EPIService(db=db)


# ==============================================================================
# EPI Catalog Endpoints
# ==============================================================================


@router.post(
    "/cadastrar",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra novo EPI",
    description="Cadastra novo modelo de EPI no sistema.",
)
async def create_epi(
    request: EPICreateRequest,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """
    Cadastra novo modelo de EPI.

    Args:
        request: Dados do EPI.
        service: Service de EPI.

    Returns:
        StandardResponse: EPI cadastrado.

    Raises:
        HTTPException: Se falhar o cadastro.
    """
    try:
        epi = service.create_epi(request)

        logger.info(
            "EPI cadastrado: nome=%s, CA=%s",
            request.nome,
            request.ca_number,
        )

        return StandardResponse(
            success=True,
            message="EPI cadastrado com sucesso",
            data={
                "epi_id": str(epi.id),
                "nome": request.nome,
                "categoria": request.categoria,
                "ca_number": request.ca_number,
                "fabricante": request.fabricante,
                "validade_dias": request.validade_dias,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro de validacao: {str(e)}",
        )
    except Exception as e:
        logger.error("Erro ao cadastrar EPI: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao cadastrar EPI",
        )


@router.get(
    "",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista EPIs cadastrados",
)
async def list_epis(
    current_user: CurrentActiveUser,
    categoria: str | None = Query(None, description="Filtrar por categoria"),
    ativo: bool | None = Query(True, description="Filtrar por status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Lista EPIs cadastrados."""
    try:
        result = service.list_epis(
            categoria=categoria,
            ativo=ativo,
            page=page,
            size=size,
        )

        return StandardResponse(
            success=True,
            message=f"Encontrados {result['total']} EPIs",
            data={
                # A tabela real (health_epi_catalog) usa ca_numero/validade_meses e não tem
                # especificacoes/riscos_protegidos. EPIResponse.model_validate quebrava (4 campos).
                # Devolvemos os dados reais + aliases p/ o schema, sem validação estrita.
                "epis": [
                    {
                        **e,
                        "ca_number": e.get("ca_numero"),
                        "validade_dias": e.get("validade_meses"),
                        "especificacoes": e.get("especificacoes") or {},
                        "riscos_protegidos": e.get("riscos_protegidos") or [],
                    }
                    for e in result["items"]
                ],
                "total": result["total"],
                "page": result["page"],
                "size": result["size"],
            },
        )

    except Exception as e:
        logger.error("Erro ao listar EPIs: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


# ==============================================================================
# Reference Data Endpoints
# ==============================================================================


@router.get(
    "/categorias",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista categorias de EPI",
    description="Retorna categorias de EPI conforme NR-6.",
)
async def list_epi_categories(
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Lista categorias de EPI."""
    data = service.get_epi_categories()

    return StandardResponse(
        success=True,
        message="Categorias de EPI conforme NR-6",
        data=data,
    )


# ==============================================================================
# Statistics Endpoint
# ==============================================================================


@router.get(
    "/estatisticas",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Estatisticas de EPI",
)
async def get_statistics(
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Retorna estatisticas de EPI."""
    try:
        stats = service.get_statistics()

        return StandardResponse(
            success=True,
            message="Estatisticas de EPI",
            data=stats,
        )

    except Exception as e:
        logger.error("Erro ao obter estatisticas: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


# ==============================================================================
# Inventory Endpoints
# ==============================================================================


@router.get(
    "/estoque",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta estoque de EPIs",
    description="Retorna estoque atual de todos os EPIs.",
)
async def get_epi_inventory(
    current_user: CurrentActiveUser,
    categoria: str | None = Query(None, description="Filtrar por categoria"),
    baixo_estoque: bool = Query(False, description="Apenas com estoque baixo"),
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Consulta estoque de EPIs."""
    try:
        inventory = service.list_inventory(
            categoria=categoria,
            low_stock_only=baixo_estoque,
        )

        return StandardResponse(
            success=True,
            message="Estoque de EPIs",
            data={
                "itens": inventory,
                "total_itens": len(inventory),
                "filtros": {
                    "categoria": categoria,
                    "baixo_estoque": baixo_estoque,
                },
            },
        )

    except Exception as e:
        logger.error("Erro ao consultar estoque: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar estoque",
        )


@router.get(
    "/ficha/{funcionario_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta ficha de EPI do funcionario",
    description="Retorna historico de EPIs entregues ao funcionario.",
)
async def get_epi_record(
    current_user: CurrentActiveUser,
    funcionario_id: UUID = Path(..., description="UUID do funcionario"),
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Consulta ficha de EPI do funcionario."""
    try:
        record = service.get_employee_record(funcionario_id)

        return StandardResponse(
            success=True,
            message="Ficha de EPI do funcionario",
            data={
                "funcionario_id": str(funcionario_id),
                # [Veracidade] entregas ja vem display-ready de gp_epi_deliveries (schema EPIDeliveryResponse
                # era do health_ e nao casa: gp_ usa id int, epi_nome/epi_ca, sem epi_id UUID).
                "entregas": record["entregas"],
                "total_entregas": record["total_entregas"],
                "epis_ativos": len(record["epis_ativos"]),
                "epis_vencidos": len(record["epis_vencidos"]),
                "epis_devolvidos": len(record["epis_devolvidos"]),
            },
        )

    except Exception as e:
        logger.error("Erro ao consultar ficha: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar ficha",
        )


# ==============================================================================
# EPI Delivery Endpoints
# ==============================================================================


@router.post(
    "/entregar",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra entrega de EPI",
    description="Registra entrega de EPI para funcionario (Ficha de EPI).",
)
async def deliver_epi(
    request: EPIDeliveryRequest,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """
    Registra entrega de EPI para funcionario.

    Args:
        request: Dados da entrega.
        service: Service de EPI.

    Returns:
        StandardResponse: Entrega registrada.

    Raises:
        HTTPException: Se falhar o registro.
    """
    try:
        delivery = service.register_delivery(request)

        logger.info(
            "Entrega de EPI registrada: funcionario=%s, epi=%s",
            request.funcionario_id,
            request.epi_id,
        )

        asyncio.create_task(
            publish_epi_entregue(
                entrega_id=str(delivery.id),
                funcionario_id=str(request.funcionario_id),
                funcionario_nome=str(getattr(delivery, "funcionario_nome", "")),
                epi_nome=str(getattr(delivery, "epi_nome", str(request.epi_id))),
                quantidade=request.quantidade,
                data_entrega=delivery.data_entrega,
                extra={"motivo": request.motivo, "ca_number": request.ca_number},
            )
        )

        return StandardResponse(
            success=True,
            message="Entrega de EPI registrada com sucesso",
            data={
                "delivery_id": str(delivery.id),
                "funcionario_id": str(request.funcionario_id),
                "epi_id": str(request.epi_id),
                "quantidade": request.quantidade,
                "motivo": request.motivo,
                "ca_number": request.ca_number,
                "data_entrega": delivery.data_entrega.isoformat(),
                "data_validade": delivery.data_validade.isoformat() if delivery.data_validade else None,
                "assinatura_pendente": not delivery.assinatura_funcionario,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro de validacao: {str(e)}",
        )
    except Exception as e:
        logger.error("Erro ao registrar entrega: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao registrar entrega",
        )


@router.get(
    "/entrega/{delivery_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Busca entrega por ID",
)
async def get_delivery(
    delivery_id: UUID,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Busca entrega por ID."""
    try:
        delivery = service.get_delivery(delivery_id)
        if not delivery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrega nao encontrada",
            )

        return StandardResponse(
            success=True,
            message="Entrega encontrada",
            data=EPIDeliveryResponse.model_validate(delivery).model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao buscar entrega: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.post(
    "/entrega/{delivery_id}/devolver",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Registra devolucao de EPI",
)
async def return_epi(
    delivery_id: UUID,
    current_user: CurrentActiveUser,
    motivo: str = Query(..., description="Motivo da devolucao"),
    condicao: str = Query(..., description="Condicao do EPI (bom, danificado, etc)"),
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Registra devolucao de EPI."""
    try:
        delivery = service.register_return(delivery_id, motivo, condicao)
        if not delivery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrega nao encontrada",
            )

        return StandardResponse(
            success=True,
            message="Devolucao registrada",
            data={
                "delivery_id": str(delivery.id),
                "devolvido": delivery.devolvido,
                "data_devolucao": delivery.data_devolucao.isoformat() if delivery.data_devolucao else None,
                "condicao": delivery.condicao_devolucao,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao registrar devolucao: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.post(
    "/entrega/{delivery_id}/assinar",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Registra assinatura do funcionario",
)
async def sign_delivery(
    delivery_id: UUID,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Registra assinatura do funcionario na entrega."""
    try:
        delivery = service.update_delivery(
            delivery_id,
            EPIDeliveryUpdateRequest(assinatura_funcionario=True),
        )
        if not delivery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrega nao encontrada",
            )

        return StandardResponse(
            success=True,
            message="Assinatura registrada",
            data={
                "delivery_id": str(delivery.id),
                "assinatura_funcionario": delivery.assinatura_funcionario,
                "data_assinatura": delivery.data_assinatura.isoformat() if delivery.data_assinatura else None,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao registrar assinatura: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.patch(
    "/estoque/{epi_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza estoque de EPI",
)
async def update_inventory(
    epi_id: UUID,
    request: EPIInventoryUpdateRequest,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Atualiza estoque de EPI."""
    try:
        inventory = service.update_inventory(epi_id, request)
        if not inventory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estoque nao encontrado",
            )

        return StandardResponse(
            success=True,
            message="Estoque atualizado",
            data=EPIInventoryResponse.model_validate(inventory).model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao atualizar estoque: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.post(
    "/estoque/{epi_id}/entrada",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Registra entrada de estoque",
)
async def add_to_inventory(
    epi_id: UUID,
    current_user: CurrentActiveUser,
    quantidade: int = Query(..., ge=1, description="Quantidade a adicionar"),
    lote: str | None = Query(None, description="Numero do lote"),
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Registra entrada de itens no estoque."""
    try:
        inventory = service.add_to_inventory(epi_id, quantidade, lote)

        return StandardResponse(
            success=True,
            message=f"Adicionados {quantidade} itens ao estoque",
            data={
                "epi_id": str(epi_id),
                "quantidade_atual": inventory.quantidade_atual,
                "lote": inventory.lote_atual,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro ao adicionar estoque: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


# ==============================================================================
# Parametric {epi_id} Endpoints (MUST be last to avoid capturing specific paths)
# ==============================================================================


@router.get(
    "/{epi_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Busca EPI por ID",
)
async def get_epi(
    epi_id: UUID,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Busca EPI por ID."""
    try:
        epi = service.get_epi(epi_id)
        if not epi:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="EPI nao encontrado",
            )

        return StandardResponse(
            success=True,
            message="EPI encontrado",
            data=EPIResponse.model_validate(epi).model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao buscar EPI: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.patch(
    "/{epi_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza EPI",
)
async def update_epi(
    epi_id: UUID,
    request: EPIUpdateRequest,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Atualiza dados de EPI."""
    try:
        epi = service.update_epi(epi_id, request)
        if not epi:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="EPI nao encontrado",
            )

        return StandardResponse(
            success=True,
            message="EPI atualizado",
            data={"epi_id": str(epi.id)},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao atualizar EPI: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )


@router.delete(
    "/{epi_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Desativa EPI",
)
async def deactivate_epi(
    epi_id: UUID,
    current_user: CurrentActiveUser,
    service: EPIService = Depends(get_epi_service),
) -> StandardResponse:
    """Desativa EPI (soft delete)."""
    try:
        epi = service.deactivate_epi(epi_id)
        if not epi:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="EPI nao encontrado",
            )

        return StandardResponse(
            success=True,
            message="EPI desativado",
            data={"epi_id": str(epi.id)},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao desativar EPI: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno",
        )
