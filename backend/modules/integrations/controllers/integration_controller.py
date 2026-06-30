"""
Controller para o módulo de Integrações
Sprint 32: API Gateway / Integrações
"""
# pylint: disable=unused-argument,too-many-locals

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.integrations.models import (
    APIKeyStatus,
    EndpointStatus,
    ExternalSystem,
    LogLevel,
    LogStatus,
    LogType,
    SyncDirection,
    SyncEntityType,
    SyncPriority,
    SyncStatus,
    WebhookStatus,
)
from modules.integrations.schemas import (
    # API Endpoint
    APIEndpointCreate,
    APIEndpointList,
    APIEndpointResponse,
    APIEndpointUpdate,
    # API Key
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyList,
    APIKeyResponse,
    APIKeyRevokeRequest,
    APIKeyUpdate,
    # Dashboard
    IntegrationDashboard,
    IntegrationHealthCheck,
    IntegrationLogList,
    # Integration Log
    IntegrationLogResponse,
    SyncQueueBatchCreate,
    # Sync Queue
    SyncQueueCreate,
    SyncQueueList,
    SyncQueueResponse,
    SyncQueueStats,
    # Webhook
    WebhookConfigCreate,
    WebhookConfigList,
    WebhookConfigResponse,
    WebhookConfigUpdate,
    WebhookTestRequest,
    WebhookTestResponse,
)
from modules.integrations.services import IntegrationService, WebhookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrações"])


# ==================== Dependências ====================


async def get_integration_service(db: AsyncSession = Depends(get_db)) -> IntegrationService:
    """Obtém serviço de integrações."""
    return IntegrationService(db)


async def get_webhook_service(db: AsyncSession = Depends(get_db)) -> WebhookService:
    """Obtém serviço de webhooks."""
    return WebhookService(db)


# ==================== Dashboard ====================


@router.get("/dashboard", response_model=IntegrationDashboard, summary="Dashboard de integrações")
async def get_dashboard(
    service: IntegrationService = Depends(get_integration_service), current_user: dict = Depends(get_current_user)
) -> IntegrationDashboard:
    """Retorna dashboard completo de integrações."""
    return await service.get_dashboard()


@router.get("/health", response_model=IntegrationHealthCheck, summary="Health check de integrações")
async def health_check(service: IntegrationService = Depends(get_integration_service)) -> IntegrationHealthCheck:
    """Verifica saúde das integrações."""
    return await service.get_health_check()


# ==================== API Endpoints ====================


@router.post(
    "/endpoints",
    response_model=APIEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria endpoint de API",
)
async def create_endpoint(
    data: APIEndpointCreate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIEndpointResponse:
    """Registra um novo endpoint de API."""
    try:
        endpoint = await service.create_endpoint(data=data, user_id=getattr(current_user, "id", None))
        return APIEndpointResponse.model_validate(endpoint)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/endpoints", response_model=APIEndpointList, summary="Lista endpoints de API")
async def list_endpoints(
    endpoint_status: EndpointStatus | None = Query(None, alias="status"),
    category: str | None = None,
    version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIEndpointList:
    """Lista endpoints com filtros e paginação."""
    endpoints, total, pages = await service.list_endpoints(
        status=endpoint_status, category=category, version=version, page=page, page_size=page_size
    )

    return APIEndpointList(
        items=[APIEndpointResponse.model_validate(e) for e in endpoints],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/endpoints/{endpoint_id}", response_model=APIEndpointResponse, summary="Busca endpoint por ID")
async def get_endpoint(
    endpoint_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIEndpointResponse:
    """Retorna detalhes de um endpoint."""
    endpoint = await service.get_endpoint(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint não encontrado")
    return APIEndpointResponse.model_validate(endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=APIEndpointResponse, summary="Atualiza endpoint")
async def update_endpoint(
    endpoint_id: UUID,
    data: APIEndpointUpdate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIEndpointResponse:
    """Atualiza um endpoint existente."""
    try:
        endpoint = await service.update_endpoint(
            endpoint_id=endpoint_id, data=data, user_id=getattr(current_user, "id", None)
        )
        return APIEndpointResponse.model_validate(endpoint)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove endpoint")
async def delete_endpoint(
    endpoint_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Remove um endpoint."""
    deleted = await service.delete_endpoint(endpoint_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint não encontrado")


@router.post("/endpoints/{endpoint_id}/deprecate", response_model=APIEndpointResponse, summary="Deprecia endpoint")
async def deprecate_endpoint(
    endpoint_id: UUID,
    replacement_id: UUID | None = None,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIEndpointResponse:
    """Marca endpoint como depreciado."""
    try:
        endpoint = await service.deprecate_endpoint(endpoint_id=endpoint_id, replacement_id=replacement_id)
        return APIEndpointResponse.model_validate(endpoint)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ==================== API Keys ====================


@router.post(
    "/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED, summary="Cria chave de API"
)
async def create_api_key(
    data: APIKeyCreate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIKeyCreateResponse:
    """
    Cria uma nova chave de API.
    IMPORTANTE: A chave completa só é exibida uma vez nesta resposta.
    """
    api_key, raw_key = await service.create_api_key(data=data, user_id=getattr(current_user, "id", None))

    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        key_hint=api_key.key_hint,
        key_type=api_key.key_type,
        status=api_key.status,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=APIKeyList, summary="Lista chaves de API")
async def list_api_keys(
    client_id: UUID | None = None,
    user_id: UUID | None = None,
    key_status: APIKeyStatus | None = Query(None, alias="status"),
    key_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIKeyList:
    """Lista chaves de API com filtros."""
    keys, total, pages = await service.list_api_keys(
        client_id=client_id, user_id=user_id, status=key_status, key_type=key_type, page=page, page_size=page_size
    )

    return APIKeyList(
        items=[APIKeyResponse.model_validate(k) for k in keys], total=total, page=page, page_size=page_size, pages=pages
    )


@router.get("/api-keys/{key_id}", response_model=APIKeyResponse, summary="Busca chave de API por ID")
async def get_api_key(
    key_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIKeyResponse:
    """Retorna detalhes de uma chave de API."""
    api_key = await service.get_api_key(key_id)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key não encontrada")
    return APIKeyResponse.model_validate(api_key)


@router.patch("/api-keys/{key_id}", response_model=APIKeyResponse, summary="Atualiza chave de API")
async def update_api_key(
    key_id: UUID,
    data: APIKeyUpdate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIKeyResponse:
    """Atualiza uma chave de API."""
    try:
        api_key = await service.update_api_key(key_id=key_id, data=data, user_id=getattr(current_user, "id", None))
        return APIKeyResponse.model_validate(api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/api-keys/{key_id}/revoke", response_model=APIKeyResponse, summary="Revoga chave de API")
async def revoke_api_key(
    key_id: UUID,
    data: APIKeyRevokeRequest | None = None,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> APIKeyResponse:
    """Revoga uma chave de API."""
    try:
        api_key = await service.revoke_api_key(
            key_id=key_id, reason=data.reason if data else None, user_id=getattr(current_user, "id", None)
        )
        return APIKeyResponse.model_validate(api_key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/api-keys/verify", summary="Verifica chave de API")
async def verify_api_key(
    request: Request,
    api_key: str,
    required_scope: str | None = None,
    service: IntegrationService = Depends(get_integration_service),
) -> dict:
    """Verifica se uma chave de API é válida."""
    client_ip = request.client.host if request.client else None

    valid, key, message = await service.verify_api_key(key=api_key, required_scope=required_scope, client_ip=client_ip)

    return {
        "valid": valid,
        "message": message,
        "key_id": str(key.id) if key else None,
        "scopes": key.scopes if key else None,
    }


# ==================== Webhooks ====================


@router.post(
    "/webhooks", response_model=WebhookConfigResponse, status_code=status.HTTP_201_CREATED, summary="Cria webhook"
)
async def create_webhook(
    data: WebhookConfigCreate,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigResponse:
    """Cria um novo webhook."""
    webhook = await service.create_webhook(data=data, user_id=getattr(current_user, "id", None))
    return WebhookConfigResponse.model_validate(webhook)


@router.get("/webhooks", response_model=WebhookConfigList, summary="Lista webhooks")
async def list_webhooks(
    client_id: UUID | None = None,
    webhook_status: WebhookStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigList:
    """Lista webhooks com filtros."""
    webhooks, total, pages = await service.list_webhooks(
        client_id=client_id, status=webhook_status, page=page, page_size=page_size
    )

    return WebhookConfigList(
        items=[WebhookConfigResponse.model_validate(w) for w in webhooks],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/webhooks/{webhook_id}", response_model=WebhookConfigResponse, summary="Busca webhook por ID")
async def get_webhook(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigResponse:
    """Retorna detalhes de um webhook."""
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")
    return WebhookConfigResponse.model_validate(webhook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookConfigResponse, summary="Atualiza webhook")
async def update_webhook(
    webhook_id: UUID,
    data: WebhookConfigUpdate,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigResponse:
    """Atualiza um webhook."""
    try:
        webhook = await service.update_webhook(
            webhook_id=webhook_id, data=data, user_id=getattr(current_user, "id", None)
        )
        return WebhookConfigResponse.model_validate(webhook)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove webhook")
async def delete_webhook(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Remove um webhook."""
    deleted = await service.delete_webhook(webhook_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse, summary="Testa webhook")
async def test_webhook(
    webhook_id: UUID,
    data: WebhookTestRequest,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookTestResponse:
    """Testa entrega de um webhook."""
    try:
        return await service.test_webhook(webhook_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/webhooks/{webhook_id}/activate", response_model=WebhookConfigResponse, summary="Ativa webhook")
async def activate_webhook(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigResponse:
    """Ativa um webhook."""
    try:
        webhook = await service.activate_webhook(webhook_id)
        return WebhookConfigResponse.model_validate(webhook)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/webhooks/{webhook_id}/pause", response_model=WebhookConfigResponse, summary="Pausa webhook")
async def pause_webhook(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> WebhookConfigResponse:
    """Pausa um webhook."""
    try:
        webhook = await service.pause_webhook(webhook_id)
        return WebhookConfigResponse.model_validate(webhook)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/webhooks/{webhook_id}/regenerate-secret", summary="Regenera secret do webhook")
async def regenerate_webhook_secret(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Regenera o secret key do webhook."""
    try:
        new_secret = await service.regenerate_secret(webhook_id=webhook_id, user_id=getattr(current_user, "id", None))
        return {"secret_key": new_secret}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/webhooks/{webhook_id}/stats", summary="Estatísticas do webhook")
async def get_webhook_stats(
    webhook_id: UUID,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Retorna estatísticas de um webhook."""
    try:
        return await service.get_webhook_stats(webhook_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/webhooks/trigger", summary="Dispara evento para webhooks")
async def trigger_webhook_event(
    event: str,
    payload: dict,
    client_id: UUID | None = None,
    service: WebhookService = Depends(get_webhook_service),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Dispara um evento para todos os webhooks inscritos."""
    results = await service.trigger_event(event=event, payload=payload, client_id=client_id)

    return {"event": event, "webhooks_triggered": len(results), "results": results}


# ==================== Integration Logs ====================


@router.get("/logs", response_model=IntegrationLogList, summary="Lista logs de integração")
async def list_logs(
    log_type: LogType | None = None,
    level: LogLevel | None = None,
    log_status: LogStatus | None = Query(None, alias="status"),
    endpoint_id: UUID | None = None,
    api_key_id: UUID | None = None,
    webhook_id: UUID | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    client_id: UUID | None = None,
    user_id: UUID | None = None,
    error_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> IntegrationLogList:
    """Lista logs de integração com filtros."""
    skip = (page - 1) * page_size

    logs, total = await service.repository.list_logs(
        log_type=log_type,
        level=level,
        status=log_status,
        endpoint_id=endpoint_id,
        api_key_id=api_key_id,
        webhook_id=webhook_id,
        correlation_id=correlation_id,
        trace_id=trace_id,
        client_id=client_id,
        user_id=user_id,
        error_only=error_only,
        skip=skip,
        limit=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return IntegrationLogList(
        items=[IntegrationLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/logs/{log_id}", response_model=IntegrationLogResponse, summary="Busca log por ID")
async def get_log(
    log_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> IntegrationLogResponse:
    """Retorna detalhes de um log."""
    log = await service.repository.get_log_by_id(log_id)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log não encontrado")
    return IntegrationLogResponse.model_validate(log)


@router.get(
    "/logs/correlation/{correlation_id}",
    response_model=list[IntegrationLogResponse],
    summary="Busca logs por correlation ID",
)
async def get_logs_by_correlation(
    correlation_id: str,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> list[IntegrationLogResponse]:
    """Retorna todos os logs de uma correlação."""
    logs = await service.repository.get_logs_by_correlation_id(correlation_id)
    return [IntegrationLogResponse.model_validate(log) for log in logs]


# ==================== Sync Queue ====================


@router.post(
    "/sync",
    response_model=SyncQueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona item à fila de sync",
)
async def queue_sync(
    data: SyncQueueCreate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> SyncQueueResponse:
    """Adiciona um item à fila de sincronização."""
    item = await service.queue_sync(data=data, user_id=getattr(current_user, "id", None))
    return SyncQueueResponse.model_validate(item)


@router.post(
    "/sync/batch",
    response_model=list[SyncQueueResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona múltiplos itens à fila",
)
async def queue_sync_batch(
    data: SyncQueueBatchCreate,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> list[SyncQueueResponse]:
    """Adiciona múltiplos itens à fila de sincronização."""
    items = await service.queue_sync_batch(
        items_data=data.items, batch_id=data.batch_id, user_id=getattr(current_user, "id", None)
    )
    return [SyncQueueResponse.model_validate(item) for item in items]


@router.get("/sync", response_model=SyncQueueList, summary="Lista itens da fila de sync")
async def list_sync_items(
    sync_status: SyncStatus | None = Query(None, alias="status"),
    priority: SyncPriority | None = None,
    entity_type: SyncEntityType | None = None,
    external_system: ExternalSystem | None = None,
    direction: SyncDirection | None = None,
    batch_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> SyncQueueList:
    """Lista itens da fila de sincronização."""
    items, total, pages = await service.list_sync_items(
        status=sync_status,
        priority=priority,
        entity_type=entity_type,
        external_system=external_system,
        direction=direction,
        batch_id=batch_id,
        page=page,
        page_size=page_size,
    )

    return SyncQueueList(
        items=[SyncQueueResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/sync/stats", response_model=SyncQueueStats, summary="Estatísticas da fila de sync")
async def get_sync_stats(
    service: IntegrationService = Depends(get_integration_service), current_user: dict = Depends(get_current_user)
) -> SyncQueueStats:
    """Retorna estatísticas da fila de sincronização."""
    stats = await service.get_sync_stats()
    return SyncQueueStats(**stats)


@router.get("/sync/{item_id}", response_model=SyncQueueResponse, summary="Busca item da fila por ID")
async def get_sync_item(
    item_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> SyncQueueResponse:
    """Retorna detalhes de um item da fila."""
    item = await service.get_sync_item(item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")
    return SyncQueueResponse.model_validate(item)


@router.post("/sync/{item_id}/cancel", response_model=SyncQueueResponse, summary="Cancela item da fila")
async def cancel_sync_item(
    item_id: UUID,
    reason: str | None = None,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> SyncQueueResponse:
    """Cancela um item da fila de sincronização."""
    try:
        item = await service.cancel_sync_item(item_id, reason)
        return SyncQueueResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/sync/{item_id}/retry", response_model=SyncQueueResponse, summary="Reprocessa item da fila")
async def retry_sync_item(
    item_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
    current_user: dict = Depends(get_current_user),
) -> SyncQueueResponse:
    """Reseta um item para reprocessamento."""
    try:
        item = await service.retry_sync_item(item_id)
        return SyncQueueResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
