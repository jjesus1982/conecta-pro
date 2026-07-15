"""Controller para integração eSocial."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_permissions
from core.database import get_db
from modules.hr.payroll_integration.schemas import (
    ESocialExportRequest,
    ESocialTransmissionResponse,
    PayrollExportResponse,
    PayrollIntegrationResponse,
)
from modules.hr.payroll_integration.services import ESocialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/esocial", tags=["eSocial"])


def _uget(user, key, default=None):
    """Acessa campo do usuário seja ele objeto User (get_current_user) ou dict
    (require_permissions). Os endpoints misturavam current_user['x'] (crashava no
    objeto User: 'User' object is not subscriptable) com current_user.x."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


@router.get(
    "/integration",
    response_model=PayrollIntegrationResponse | None,
    summary="Configuração eSocial",
)
async def get_integration(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollIntegrationResponse | None:
    """Retorna configuração de integração eSocial."""
    try:
        service = ESocialService(db)
        integration = await service.get_integration(_uget(current_user, "condominio_id"))
        if not integration:
            return None
        return PayrollIntegrationResponse.model_validate(integration)
    except Exception as e:
        logger.error("Erro ao buscar integração eSocial: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar integração",
        )


@router.get(
    "/validate",
    response_model=dict,
    summary="Validar configuração",
)
async def validate_integration(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Valida configuração do eSocial."""
    try:
        service = ESocialService(db)
        result = await service.validate_integration(_uget(current_user, "condominio_id"))
        return result
    except Exception as e:
        logger.error("Erro ao validar integração eSocial: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao validar integração",
        )


@router.get(
    "/events",
    response_model=dict,
    summary="Eventos suportados",
)
async def get_supported_events(
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna lista de eventos eSocial suportados."""
    # pylint: disable=import-outside-toplevel
    from modules.hr.payroll_integration.services.esocial_service import ESOCIAL_EVENTS

    return {
        "events": [
            {
                "code": code,
                "name": info["name"],
                "description": info["description"],
                "periodic": info["periodic"],
            }
            for code, info in ESOCIAL_EVENTS.items()
        ],
        "total": len(ESOCIAL_EVENTS),
    }


@router.post(
    "/generate",
    response_model=PayrollExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento eSocial",
)
async def generate_event(
    request: ESocialExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permissions(["esocial:generate"])),
) -> PayrollExportResponse:
    """Gera XML de evento eSocial."""
    try:
        service = ESocialService(db)
        export = await service.generate_event(
            request=request,
            condominio_id=_uget(current_user, "condominio_id"),
            user_id=_uget(current_user, "id"),
        )
        logger.info(
            "Evento eSocial gerado: %s tipo %s por %s",
            export.export_code,
            request.event_type,
            _uget(current_user, "email"),
        )
        return PayrollExportResponse.model_validate(export)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao gerar evento eSocial: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao gerar evento",
        )


@router.post(
    "/transmit/{export_id}",
    response_model=ESocialTransmissionResponse,
    summary="Transmitir ao eSocial",
)
async def transmit_event(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permissions(["esocial:transmit"])),
) -> ESocialTransmissionResponse:
    """Transmite evento ao eSocial."""
    try:
        service = ESocialService(db)
        result = await service.transmit(
            export_id=export_id,
            condominio_id=_uget(current_user, "condominio_id"),
        )
        logger.info(
            "Evento transmitido: %s protocolo %s por %s",
            export_id,
            result.protocol,
            _uget(current_user, "email"),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao transmitir evento %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao transmitir evento",
        )


@router.get(
    "/receipt/{export_id}",
    response_model=dict,
    summary="Consultar recibo",
)
async def check_receipt(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Consulta recibo de transmissão no eSocial."""
    try:
        service = ESocialService(db)
        result = await service.check_receipt(
            export_id=export_id,
            condominio_id=_uget(current_user, "condominio_id"),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao consultar recibo %s: %s", export_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar recibo",
        )


@router.post(
    "/batch/generate",
    response_model=dict,
    summary="Gerar lote eSocial",
)
async def generate_batch(
    period_id: UUID = Query(..., description="ID do período"),
    event_types: list = Query(
        default=["S-1200", "S-1210"],
        description="Tipos de eventos a gerar",
    ),
    test_mode: bool = Query(False, description="Modo de teste"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permissions(["esocial:generate"])),
) -> dict:
    """Gera lote de eventos eSocial para um período."""
    try:
        service = ESocialService(db)
        results = {
            "generated": [],
            "failed": [],
            "total": 0,
        }

        for event_type in event_types:
            try:
                request = ESocialExportRequest(
                    period_id=period_id,
                    event_type=event_type,
                    test_mode=test_mode,
                )
                export = await service.generate_event(
                    request=request,
                    condominio_id=_uget(current_user, "condominio_id"),
                    user_id=_uget(current_user, "id"),
                )
                results["generated"].append(
                    {
                        "event_type": event_type,
                        "export_id": str(export.id),
                        "export_code": export.export_code,
                    }
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                results["failed"].append(
                    {
                        "event_type": event_type,
                        "error": str(e),
                    }
                )

        results["total"] = len(results["generated"]) + len(results["failed"])

        logger.info(
            "Lote eSocial: %d gerados, %d falhas por %s",
            len(results["generated"]),
            len(results["failed"]),
            _uget(current_user, "email"),
        )
        return results
    except Exception as e:
        logger.error("Erro ao gerar lote eSocial: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao gerar lote",
        )


@router.post(
    "/batch/transmit",
    response_model=dict,
    summary="Transmitir lote",
)
async def transmit_batch(
    export_ids: list = Query(..., description="IDs das exportações"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permissions(["esocial:transmit"])),
) -> dict:
    """Transmite lote de eventos ao eSocial."""
    try:
        service = ESocialService(db)
        results = {
            "transmitted": [],
            "failed": [],
            "total": 0,
        }

        for export_id in export_ids:
            try:
                result = await service.transmit(
                    export_id=UUID(export_id),
                    condominio_id=_uget(current_user, "condominio_id"),
                )
                results["transmitted"].append(
                    {
                        "export_id": export_id,
                        "protocol": result.protocol,
                        "receipt": result.receipt,
                        "status": result.status,
                    }
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                results["failed"].append(
                    {
                        "export_id": export_id,
                        "error": str(e),
                    }
                )

        results["total"] = len(results["transmitted"]) + len(results["failed"])

        logger.info(
            "Transmissão lote: %d enviados, %d falhas por %s",
            len(results["transmitted"]),
            len(results["failed"]),
            _uget(current_user, "email"),
        )
        return results
    except Exception as e:
        logger.error("Erro ao transmitir lote: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao transmitir lote",
        )


@router.get(
    "/rubrica-mapping",
    response_model=dict,
    summary="Mapeamento de rubricas",
)
async def get_rubrica_mapping(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Retorna mapeamento de rubricas para eSocial."""
    try:
        service = ESocialService(db)
        integration = await service.get_integration(_uget(current_user, "condominio_id"))
        if not integration:
            return {"mapping": {}, "total": 0}

        return {
            "mapping": integration.rubrica_mapping or {},
            "total": len(integration.rubrica_mapping or {}),
        }
    except Exception as e:
        logger.error("Erro ao buscar mapeamento: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar mapeamento",
        )


@router.get(
    "/status",
    response_model=dict,
    summary="Status do eSocial",
)
async def get_esocial_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Retorna status geral da integração eSocial."""
    try:
        service = ESocialService(db)
        integration = await service.get_integration(_uget(current_user, "condominio_id"))
        validation = await service.validate_integration(_uget(current_user, "condominio_id"))

        return {
            "configured": integration is not None,
            "valid": validation["valid"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "last_sync": (integration.last_sync_at.isoformat() if integration and integration.last_sync_at else None),
            "sync_status": integration.sync_status if integration else None,
            "ambiente": (integration.esocial_config or {}).get("ambiente") if integration else None,
        }
    except Exception as e:
        logger.error("Erro ao buscar status eSocial: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar status",
        )
