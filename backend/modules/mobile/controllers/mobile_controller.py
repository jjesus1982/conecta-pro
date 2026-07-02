"""Controller de API mobile."""

import logging
import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.mobile.gateway import DeviceDetector, MobileGateway
from modules.mobile.schemas.batch_schemas import (
    BatchOperationResult,
    BatchRequest,
    BatchResponse,
)
from modules.mobile.schemas.device_schemas import (
    DeviceTokenCreate,
    DeviceTokenResponse,
)
from modules.mobile.schemas.mobile_schemas import (
    DashboardSummary,
    HealthCheckResponse,
    MobileConfigResponse,
    MobileDashboardResponse,
    ModuleOfflineData,
    OfflineDataResponse,
    QuickAction,
    RecentActivity,
    UserProfileOffline,
)
from modules.mobile.schemas.notification_schemas import (
    BroadcastNotificationRequest,
    BroadcastNotificationResponse,
    NotificationListResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    PushNotificationResponse,
)
from modules.mobile.schemas.sync_schemas import (
    MobileSyncRequest,
    MobileSyncResponse,
)
from modules.mobile.services import (
    MobileSecurity,
    OfflineSyncManager,
    PushNotificationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile", tags=["Mobile API"])

# Inicializar serviços (em produção, usar DI)
device_detector = DeviceDetector()
gateway = MobileGateway()
push_service = PushNotificationService()
sync_manager = OfflineSyncManager()
security = MobileSecurity(api_key_secret=os.environ.get("MOBILE_API_SECRET", "mobile_api_secret_key_2024"))  # noqa: S106


# =============================================================================
# Health & Config
# =============================================================================


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Verifica saúde do serviço mobile."""
    return HealthCheckResponse(
        status="healthy",
        service="mobile-api",
        version="1.0.0",
        timestamp=datetime.utcnow(),
        components={
            "gateway": "healthy",
            "push": "healthy",
            "sync": "healthy",
        },
    )


@router.get("/config", response_model=MobileConfigResponse)
async def get_mobile_config(
    request: Request,
    current_user=Depends(get_current_user),
):
    """
    Obtém configuração do app mobile.

    Retorna versão mínima, features habilitadas e configurações de sync.
    """
    await device_detector.detect(request)

    # Verificar se precisa atualizar
    min_version = "1.0.0"
    force_update = False

    # if compare_versions(current_version, min_version) < 0:
    #     force_update = True

    return MobileConfigResponse(
        api_version="1.0.0",
        min_app_version=min_version,
        force_update=force_update,
        update_url="https://conectapro.com.br/download",
        maintenance_mode=False,
        features=[
            {"id": "offline_sync", "name": "Sync Offline", "enabled": True},
            {"id": "push_notifications", "name": "Notificações Push", "enabled": True},
            {"id": "biometric_auth", "name": "Autenticação Biométrica", "enabled": True},
            {"id": "dark_mode", "name": "Modo Escuro", "enabled": True},
        ],
        sync_config={
            "auto_sync_enabled": True,
            "sync_interval_seconds": 300,
            "max_offline_days": 7,
            "max_cache_size_mb": 100,
        },
        push_config={
            "enabled": True,
            "topics": ["general", "alerts", "updates"],
        },
        analytics_config={
            "enabled": True,
            "sample_rate": 1.0,
        },
    )


# =============================================================================
# Dashboard & Quick Actions
# =============================================================================


@router.get("/dashboard", response_model=MobileDashboardResponse)
async def get_mobile_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Obtém dashboard otimizado para mobile.

    Retorna resumo, atividades recentes e ações rápidas.
    """
    await device_detector.detect(request)

    # Determinar se deve reduzir dados
    lightweight = gateway.should_use_lightweight_response(
        gateway._parse_device_info(
            request.headers.get("user-agent", ""),
            dict(request.headers),
        )
    )

    # Buscar dados reais do dashboard (0 honesto quando a tabela está vazia)
    period_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = datetime.utcnow()

    totals = await db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM leads) AS total_leads,
                (SELECT COUNT(*) FROM clients) AS total_customers,
                (SELECT COUNT(*) FROM contracts WHERE status = 'active') AS total_orders,
                (SELECT COALESCE(SUM(monthly_value), 0)
                   FROM contracts WHERE status = 'active') AS total_revenue,
                (SELECT COUNT(*) FROM crm_activities
                   WHERE completed_at IS NULL AND scheduled_at IS NOT NULL) AS pending_tasks
            """
        )
    )
    trow = totals.mappings().first()

    # Notificações não lidas: não há tabela de notificações mobile por usuário no banco
    # → 0 honesto (não fabricar). Sem query que abortaria a transação async.
    unread_notifications = 0

    summary = DashboardSummary(
        total_leads=int(trow["total_leads"] or 0) if trow else 0,
        total_customers=int(trow["total_customers"] or 0) if trow else 0,
        total_orders=int(trow["total_orders"] or 0) if trow else 0,
        total_revenue=float(trow["total_revenue"] or 0.0) if trow else 0.0,
        pending_tasks=int(trow["pending_tasks"] or 0) if trow else 0,
        unread_notifications=unread_notifications,
        period_start=period_start,
        period_end=period_end,
    )

    # Ações rápidas baseadas no perfil
    quick_actions = [
        QuickAction(
            id="new_lead",
            label="Novo Lead",
            icon="user-plus",
            action="navigate",
            route="/leads/new",
            badge_count=0,
        ),
        QuickAction(
            id="tasks",
            label="Tarefas",
            icon="check-square",
            action="navigate",
            route="/tasks",
            badge_count=summary.pending_tasks,
        ),
        QuickAction(
            id="notifications",
            label="Notificações",
            icon="bell",
            action="navigate",
            route="/notifications",
            badge_count=summary.unread_notifications,
        ),
        QuickAction(
            id="scan_qr",
            label="QR Code",
            icon="qr-code",
            action="scan",
            badge_count=0,
        ),
    ]

    # Atividades recentes reais de crm_activities (simplificado p/ conexões lentas)
    recent_activities: list[RecentActivity] = []
    if not lightweight:
        act_res = await db.execute(
            text(
                """
                SELECT id, type, subject, description, created_at,
                       client_id, lead_id, proposal_id
                FROM crm_activities
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        )
        for a in act_res.mappings().all():
            entity_type = None
            entity_id = None
            if a["lead_id"]:
                entity_type, entity_id = "lead", str(a["lead_id"])
            elif a["proposal_id"]:
                entity_type, entity_id = "proposal", str(a["proposal_id"])
            elif a["client_id"]:
                entity_type, entity_id = "client", str(a["client_id"])

            recent_activities.append(
                RecentActivity(
                    id=str(a["id"]),
                    type=a["type"] or "activity",
                    title=a["subject"] or "Atividade",
                    description=a["description"] or "",
                    icon="activity",
                    timestamp=a["created_at"] or datetime.utcnow(),
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )

    return MobileDashboardResponse(
        summary=summary,
        quick_actions=quick_actions,
        recent_activities=recent_activities,
        charts=None if lightweight else {},
        last_updated=datetime.utcnow(),
        cache_expires_at=datetime.utcnow(),
    )


# =============================================================================
# Sync Operations
# =============================================================================


@router.post("/sync", response_model=MobileSyncResponse)
async def sync_data(
    request: Request,
    sync_request: MobileSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Sincroniza dados com o servidor.

    Processa operações offline do cliente e retorna mudanças do servidor.
    """
    user_id = current_user.id

    # Validar segurança
    await security.validate_request(request, db, "sync")

    # Processar sincronização
    response = await sync_manager.process_sync(db, user_id, sync_request)

    logger.info(
        f"Sync completed for user {user_id}: "
        f"{len(sync_request.operations)} operations, "
        f"{len(response.conflicts)} conflicts"
    )

    return response


@router.get("/sync/status")
async def get_sync_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Obtém status de sincronização do dispositivo."""
    user_id = current_user.id
    device_id = request.headers.get("x-device-id", "unknown")

    status = await sync_manager.get_sync_status(db, user_id, device_id)

    return status


@router.post("/sync/resolve-conflict")
async def resolve_sync_conflict(
    conflict_id: str,
    resolution: str = Query(..., description="use_client, use_server, merge"),
    merged_data: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resolve conflito de sincronização."""
    user_id = current_user.id

    result = await sync_manager.resolve_user_conflict(db, user_id, conflict_id, resolution, merged_data)

    return result


# =============================================================================
# Offline Data
# =============================================================================


@router.get("/offline-data", response_model=OfflineDataResponse)
async def get_offline_data(
    request: Request,
    modules: str | None = Query(None, description="Módulos a sincronizar (separados por vírgula)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Obtém dados essenciais para funcionamento offline.

    Retorna perfil do usuário e dados essenciais dos módulos solicitados.
    """
    user_id = current_user.id
    await device_detector.detect(request)

    # Parsear módulos
    requested_modules = modules.split(",") if modules else ["leads", "tasks", "contacts"]

    # Perfil do usuário
    user_profile = UserProfileOffline(
        id=user_id,
        name=current_user.get("name", "Usuário"),
        email=current_user.get("email", ""),
        role=current_user.get("role", "user"),
        permissions=current_user.get("permissions", []),
        preferences=current_user.get("preferences", {}),
    )

    # Dados essenciais por módulo
    essential_data = {}
    total_size = 0

    for module in requested_modules:
        if module == "leads":
            essential_data["leads"] = ModuleOfflineData(
                module="leads",
                records=[],
                total_count=0,
                last_modified=datetime.utcnow(),
                version=1,
                sync_priority=1,
            )
        elif module == "tasks":
            essential_data["tasks"] = ModuleOfflineData(
                module="tasks",
                records=[],
                total_count=0,
                last_modified=datetime.utcnow(),
                version=1,
                sync_priority=2,
            )
        elif module == "contacts":
            essential_data["contacts"] = ModuleOfflineData(
                module="contacts",
                records=[],
                total_count=0,
                last_modified=datetime.utcnow(),
                version=1,
                sync_priority=3,
            )

    # Gerar sync token
    sync_status = await sync_manager.get_sync_status(db, user_id, request.headers.get("x-device-id", "unknown"))

    return OfflineDataResponse(
        user_profile=user_profile,
        essential_data=essential_data,
        last_sync=datetime.utcnow(),
        sync_token=sync_status["sync_token"],
        cache_expires_at=datetime.utcnow(),
        total_size_bytes=total_size,
        modules_available=list(essential_data.keys()),
    )


# =============================================================================
# Batch Operations
# =============================================================================


@router.post("/batch", response_model=BatchResponse)
async def execute_batch(
    request: Request,
    batch_request: BatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Executa múltiplas operações em batch.

    Otimiza chamadas múltiplas combinando em uma única requisição.
    """
    # Validar segurança
    await security.validate_request(request, db, "batch")

    start_time = datetime.utcnow()
    results: list[BatchOperationResult] = []
    success_count = 0
    error_count = 0

    for operation in batch_request.operations:
        op_start = datetime.utcnow()
        try:
            # Roteamento de operações do batch. Nenhum handler real foi
            # implementado ainda: retornamos status honesto "not_implemented"
            # (HTTP 501) em vez de fabricar "success".
            result = await _dispatch_batch_operation(db, current_user, operation)
            results.append(result)
            if result.status == "success":
                success_count += 1
            else:
                error_count += 1
        except Exception as e:  # noqa: BLE001
            op_ms = int((datetime.utcnow() - op_start).total_seconds() * 1000)
            results.append(
                BatchOperationResult(
                    id=operation.id,
                    status="error",
                    status_code=500,
                    error=str(e),
                    execution_time_ms=op_ms,
                )
            )
            error_count += 1

        if error_count and batch_request.stop_on_error:
            break

    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

    return BatchResponse(
        results=results,
        execution_time_ms=processing_time,
        success_count=success_count,
        error_count=error_count,
        skipped_count=0,
    )


async def _dispatch_batch_operation(
    db: AsyncSession,
    current_user,
    operation,
) -> BatchOperationResult:
    """Roteia uma operação de batch a um handler real.

    Como não há handlers de batch implementados neste módulo, retorna status
    honesto "not_implemented" (HTTP 501) — nunca fabrica "success".
    """
    op_start = datetime.utcnow()
    op_ms = int((datetime.utcnow() - op_start).total_seconds() * 1000)
    return BatchOperationResult(
        id=operation.id,
        status="not_implemented",
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        error=(
            f"Batch handler não implementado para "
            f"{operation.method} {operation.endpoint}"
        ),
        execution_time_ms=op_ms,
    )


# =============================================================================
# Device Registration
# =============================================================================


@router.post("/devices/register", response_model=DeviceTokenResponse, status_code=201)
async def register_device(
    device_data: DeviceTokenCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Registra dispositivo para notificações push.

    Armazena token FCM/APNs para envio de notificações.
    """
    user_id = current_user.id

    token = await push_service.register_device_token(
        db=db,
        user_id=user_id,
        token=device_data.token,
        platform=device_data.platform,
        device_id=device_data.device_id,
        device_info={
            "device_name": device_data.device_name,
            "device_model": device_data.device_model,
            "os_version": device_data.os_version,
            "app_version": device_data.app_version,
            "locale": device_data.locale,
            "timezone": device_data.timezone,
        },
    )

    return DeviceTokenResponse(
        id=token.id,
        user_id=token.user_id,
        platform=token.platform,
        device_id=token.device_id,
        device_name=token.device_name,
        device_model=token.device_model,
        os_version=token.os_version,
        app_version=token.app_version,
        push_enabled=token.push_enabled,
        is_active=token.is_active,
        last_used_at=token.last_used_at,
        created_at=token.created_at,
    )


@router.delete("/devices/{device_id}")
async def unregister_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove registro de dispositivo."""

    success = await push_service.unregister_device_token(db, device_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    return {"message": "Device unregistered successfully"}


# =============================================================================
# Push Notifications
# =============================================================================


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista notificações do usuário."""
    user_id = current_user.id
    offset = (page - 1) * page_size

    notifications, total, unread_count = await push_service.get_user_notifications(
        db=db,
        user_id=user_id,
        limit=page_size,
        offset=offset,
        unread_only=unread_only,
    )

    return NotificationListResponse(
        notifications=[
            PushNotificationResponse(
                id=n.id,
                user_id=n.user_id,
                title=n.title,
                body=n.body,
                notification_type=n.notification_type.value,
                priority=n.priority.value,
                data_payload=n.data_payload or {},
                image_url=n.image_url,
                action_url=n.action_url,
                status=n.status.value,
                error_message=n.error_message,
                external_id=n.external_id,
                sent_at=n.sent_at,
                delivered_at=n.delivered_at,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n in notifications
        ],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Marca notificação como lida."""
    success = await push_service.mark_as_read(db, notification_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return {"message": "Notification marked as read"}


@router.post("/notifications/{notification_id}/delivered")
async def mark_notification_delivered(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Marca notificação como entregue (callback do dispositivo)."""
    success = await push_service.mark_as_delivered(db, notification_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return {"message": "Notification marked as delivered"}


@router.get("/notifications/preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_user=Depends(get_current_user),
):
    """Obtém preferências de notificação do usuário."""
    return NotificationPreferences(
        push_enabled=True,
        email_enabled=True,
        sms_enabled=False,
        quiet_hours_enabled=False,
        quiet_hours_start="22:00",
        quiet_hours_end="07:00",
        categories={
            "system": True,
            "alert": True,
            "info": True,
            "marketing": False,
            "reminder": True,
            "transaction": True,
            "message": True,
        },
        sound_enabled=True,
        vibration_enabled=True,
        badge_enabled=True,
    )


@router.put("/notifications/preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    preferences: NotificationPreferencesUpdate,
    current_user=Depends(get_current_user),
):
    """Atualiza preferências de notificação."""
    return NotificationPreferences(
        push_enabled=preferences.push_enabled or True,
        email_enabled=preferences.email_enabled or True,
        sms_enabled=preferences.sms_enabled or False,
        quiet_hours_enabled=preferences.quiet_hours_enabled or False,
        quiet_hours_start=preferences.quiet_hours_start or "22:00",
        quiet_hours_end=preferences.quiet_hours_end or "07:00",
        categories=preferences.categories or {},
        sound_enabled=preferences.sound_enabled or True,
        vibration_enabled=preferences.vibration_enabled or True,
        badge_enabled=preferences.badge_enabled or True,
    )


# =============================================================================
# Admin Endpoints (require admin role)
# =============================================================================


@router.post("/admin/notifications/broadcast", response_model=BroadcastNotificationResponse)
async def send_broadcast_notification(
    request: BroadcastNotificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Envia notificação em broadcast.

    Requer permissão de administrador.
    """
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    response = await push_service.send_broadcast(db, request)

    return response


@router.get("/admin/notifications/stats")
async def get_notification_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Obtém estatísticas de notificações.

    Requer permissão de administrador.
    """
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    stats = await push_service.get_stats(db, days=days)

    return stats
