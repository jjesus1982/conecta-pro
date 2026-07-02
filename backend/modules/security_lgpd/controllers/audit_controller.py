"""
Controller de Auditoria LGPD.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.auth.dependencies import get_current_user
from modules.security_lgpd.schemas.audit import AuditLogRequest
from modules.security_lgpd.schemas.common import StandardResponse
from modules.security_lgpd.services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audit", tags=["LGPD - Auditoria"])


@router.post(
    "/log",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra evento de auditoria",
    description="Registra evento na trilha de auditoria com hash chain.",
)
async def create_audit_log(
    request: AuditLogRequest, current_user: dict = Depends(get_current_user)
) -> StandardResponse:
    """
    Registra evento de auditoria.
    Args:
        request: Dados do evento.
    Returns:
        StandardResponse: Confirmacao do registro.
    """
    try:
        from modules.security_lgpd.services.audit_service import (
            AuditAction,
            AuditSeverity,
            ResourceType,
        )

        service = AuditService()
        service.set_context(user_id=request.user_id)
        try:
            action = (
                AuditAction(request.action)
                if request.action in [a.value for a in AuditAction]
                else AuditAction.READ
            )
            resource_type = (
                ResourceType(request.resource_type)
                if request.resource_type in [r.value for r in ResourceType]
                else ResourceType.DATA
            )
            severity = (
                AuditSeverity(request.severity)
                if request.severity in [s.value for s in AuditSeverity]
                else AuditSeverity.INFO
            )
            entry = await service.log(
                action=action,
                resource_type=resource_type,
                resource_id=request.resource_id,
                description=f"{request.action} em {request.resource_type}:{request.resource_id}",
                metadata=request.details or {},
                severity=severity,
            )
        finally:
            service.clear_context()

        result = {
            "log_id": str(entry.id),
            "action": request.action,
            "resource_type": request.resource_type,
            "timestamp": entry.timestamp.isoformat(),
            "hash": (entry.hash[:16] + "...") if entry.hash else None,
        }
        return StandardResponse(
            success=True,
            message="Evento registrado na trilha de auditoria (persistido)",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dados invalidos: {str(e)}",
        )
    except Exception as e:
        logger.error("Erro ao registrar auditoria: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao registrar evento",
        )


@router.get(
    "/logs",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista eventos de auditoria",
    description="Retorna eventos de auditoria com filtros.",
)
async def list_audit_logs(
    resource_type: str | None = Query(None, description="Tipo de recurso"),
    user_id: str | None = Query(None, description="ID do usuario"),
    start_date: datetime | None = Query(None, description="Data inicial"),
    end_date: datetime | None = Query(None, description="Data final"),
    limit: int = Query(100, ge=1, le=1000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginacao"),
    current_user: dict = Depends(get_current_user),
) -> StandardResponse:
    """
    Lista eventos de auditoria.
    Args:
        resource_type: Filtro por tipo de recurso.
        user_id: Filtro por usuario.
        start_date: Data inicial.
        end_date: Data final.
        limit: Limite de resultados.
        offset: Offset para paginacao.
    Returns:
        StandardResponse: Lista de eventos.
    """
    try:
        from modules.security_lgpd.services.audit_service import ResourceType as AuditResourceType

        service = AuditService()
        rt = (
            AuditResourceType(resource_type)
            if resource_type and resource_type in [r.value for r in AuditResourceType]
            else None
        )
        entries = await service.query(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            resource_type=rt,
            limit=limit,
            offset=offset,
        )
        result = {
            "logs": [e.to_dict() for e in entries],
            "total": len(entries),
            "limit": limit,
            "offset": offset,
        }
        return StandardResponse(
            success=True,
            message=f"Encontrados {result['total']} eventos",
            data=result,
        )
    except Exception as e:
        logger.error("Erro ao listar auditoria: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao listar eventos",
        )


@router.get("/actions", include_in_schema=False)
@router.get(
    "/actions/list",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista acoes de auditoria",
    description="Retorna acoes de auditoria disponiveis.",
)
async def list_actions(current_user: dict = Depends(get_current_user)) -> StandardResponse:
    """
    Lista acoes de auditoria disponiveis.
    Returns:
        StandardResponse: Lista de acoes.
    """
    service = AuditService()
    actions = service.get_actions()
    return StandardResponse(
        success=True,
        message="Acoes de auditoria disponiveis",
        data={"actions": actions},
    )


@router.get("/resource-types", include_in_schema=False)
@router.get(
    "/resource-types/list",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista tipos de recurso",
    description="Retorna tipos de recurso auditados.",
)
async def list_resource_types(current_user: dict = Depends(get_current_user)) -> StandardResponse:
    """
    Lista tipos de recurso auditados.
    Returns:
        StandardResponse: Lista de tipos de recurso.
    """
    service = AuditService()
    types = service.get_resource_types()
    return StandardResponse(
        success=True,
        message="Tipos de recurso disponiveis",
        data={"resource_types": types},
    )
