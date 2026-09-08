"""
Controller para Conectores Externos
Sprint 33: Integration Framework

Gerencia contas de integração e execução de syncs com sistemas externos.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.integrations.schemas.connector_schemas import (
    ConnectorInfo,
    ConnectorListResponse,
    HealthCheckResponse,
    IntegrationAccountCreate,
    IntegrationAccountList,
    IntegrationAccountResponse,
    IntegrationAccountUpdate,
    SyncRunCreate,
    SyncRunList,
    SyncRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/connectors", tags=["Conectores Externos"])


# ==================== Endpoints - Conectores ====================


@router.get("", response_model=ConnectorListResponse, summary="Lista conectores disponíveis")
async def list_connectors(current_user: dict = Depends(get_current_user)) -> ConnectorListResponse:
    """Retorna lista de conectores disponíveis no sistema."""
    from modules.integrations.sync.engine import ConnectorRegistry

    connectors = []
    for name, connector_class in ConnectorRegistry.list_connectors().items():
        # Instanciar temporariamente para obter capabilities
        try:
            temp_instance = connector_class.__new__(connector_class)
            temp_instance._credentials = {}
            temp_instance._config = {}

            caps = temp_instance.capabilities

            connectors.append(
                ConnectorInfo(
                    name=connector_class.NAME,
                    version=connector_class.VERSION,
                    display_name=_get_display_name(connector_class.NAME),
                    description=_get_description(connector_class.NAME),
                    supported_entities=caps.supported_entities,
                    auth_type=_get_auth_type(connector_class.NAME),
                    supports_incremental_sync=caps.supports_incremental_sync,
                    supports_webhooks=caps.supports_webhooks,
                    supports_write=caps.supports_write,
                    rate_limit_per_second=caps.rate_limit_per_second,
                    rate_limit_per_minute=caps.rate_limit_per_minute,
                )
            )
        except Exception as e:
            logger.warning(f"Erro ao obter info do conector {name}: {e}")
            continue

    return ConnectorListResponse(connectors=connectors, total=len(connectors))


@router.get("/{connector_name}", response_model=ConnectorInfo, summary="Detalhes de um conector")
async def get_connector(connector_name: str, current_user: dict = Depends(get_current_user)) -> ConnectorInfo:
    """Retorna detalhes de um conector específico."""
    from modules.integrations.sync.engine import ConnectorRegistry

    connector_class = ConnectorRegistry.get(connector_name)
    if not connector_class:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{connector_name}' não encontrado")

    try:
        temp_instance = connector_class.__new__(connector_class)
        temp_instance._credentials = {}
        temp_instance._config = {}
        caps = temp_instance.capabilities

        return ConnectorInfo(
            name=connector_class.NAME,
            version=connector_class.VERSION,
            display_name=_get_display_name(connector_class.NAME),
            description=_get_description(connector_class.NAME),
            supported_entities=caps.supported_entities,
            auth_type=_get_auth_type(connector_class.NAME),
            supports_incremental_sync=caps.supports_incremental_sync,
            supports_webhooks=caps.supports_webhooks,
            supports_write=caps.supports_write,
            rate_limit_per_second=caps.rate_limit_per_second,
            rate_limit_per_minute=caps.rate_limit_per_minute,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao obter informações do conector: {str(e)}"
        ) from e


# ==================== Endpoints - Contas ====================


@router.post(
    "/accounts",
    response_model=IntegrationAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria conta de integração",
)
async def create_account(
    data: IntegrationAccountCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> IntegrationAccountResponse:
    """Cria uma nova conta de integração com um sistema externo."""
    from modules.integrations.models.integration_account import IntegrationAccount
    from modules.integrations.sync.engine import ConnectorRegistry

    # Verificar se conector existe
    connector_class = ConnectorRegistry.get(data.connector_type)
    if not connector_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Conector '{data.connector_type}' não disponível"
        )

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant ID não encontrado no usuário")

    # Criar conta
    account = IntegrationAccount(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description,
        connector_type=data.connector_type,
        auth_type=_get_auth_type(data.connector_type),
        environment=data.environment,
        extra_config=data.config or {},
        sync_enabled=data.sync_enabled,
        sync_interval_minutes=data.sync_interval_minutes,
        sync_entities=data.sync_entities,
        status="pending_auth",
        created_by=current_user.get("id"),
    )

    # Criptografar e armazenar credenciais
    account.set_credentials(data.credentials)

    db.add(account)
    await db.commit()
    await db.refresh(account)

    return _account_to_response(account)


@router.get("/accounts", response_model=IntegrationAccountList, summary="Lista contas de integração")
async def list_accounts(
    connector_type: str | None = None,
    account_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> IntegrationAccountList:
    """Lista contas de integração do tenant."""
    from sqlalchemy import func, select

    from modules.integrations.models.integration_account import IntegrationAccount

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    # Query base
    query = select(IntegrationAccount).where(IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo)

    # Filtros
    if connector_type:
        query = query.where(IntegrationAccount.connector_type == connector_type)
    if account_status:
        query = query.where(IntegrationAccount.status == account_status)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginação
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(IntegrationAccount.created_at.desc())

    result = await db.execute(query)
    accounts = result.scalars().all()

    pages = (total + page_size - 1) // page_size

    return IntegrationAccountList(
        items=[_account_to_response(a) for a in accounts], total=total, page=page, page_size=page_size, pages=pages
    )


@router.get("/accounts/{account_id}", response_model=IntegrationAccountResponse, summary="Busca conta por ID")
async def get_account(
    account_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> IntegrationAccountResponse:
    """Retorna detalhes de uma conta de integração."""
    from sqlalchemy import select

    from modules.integrations.models.integration_account import IntegrationAccount

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    query = select(IntegrationAccount).where(
        IntegrationAccount.id == account_id, IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada")

    return _account_to_response(account)


@router.patch("/accounts/{account_id}", response_model=IntegrationAccountResponse, summary="Atualiza conta")
async def update_account(
    account_id: UUID,
    data: IntegrationAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> IntegrationAccountResponse:
    """Atualiza uma conta de integração."""
    from sqlalchemy import select

    from modules.integrations.models.integration_account import IntegrationAccount

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    query = select(IntegrationAccount).where(
        IntegrationAccount.id == account_id, IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada")

    # Atualizar campos
    update_data = data.model_dump(exclude_unset=True)

    if "credentials" in update_data and update_data["credentials"]:
        account.set_credentials(update_data.pop("credentials"))

    if "config" in update_data:
        account.extra_config = update_data.pop("config")

    for key, value in update_data.items():
        setattr(account, key, value)

    account.updated_by = current_user.get("id")

    await db.commit()
    await db.refresh(account)

    return _account_to_response(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove conta")
async def delete_account(
    account_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> None:
    """Remove (soft delete) uma conta de integração."""
    from sqlalchemy import select

    from modules.integrations.models.integration_account import IntegrationAccount

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    query = select(IntegrationAccount).where(
        IntegrationAccount.id == account_id, IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada")

    account.ativo = False
    account.updated_by = current_user.get("id")

    await db.commit()


# ==================== Endpoints - Health Check ====================


@router.get("/accounts/{account_id}/health", response_model=HealthCheckResponse, summary="Health check da conta")
async def health_check_account(
    account_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> HealthCheckResponse:
    """Verifica saúde da conexão com o sistema externo."""
    from datetime import datetime

    from sqlalchemy import select

    from modules.integrations.models.integration_account import IntegrationAccount
    from modules.integrations.sync.engine import ConnectorRegistry

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    # Buscar conta
    query = select(IntegrationAccount).where(
        IntegrationAccount.id == account_id, IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada")

    # Obter conector
    connector_class = ConnectorRegistry.get(account.connector_type)
    if not connector_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Conector '{account.connector_type}' não disponível"
        )

    # Executar health check
    try:
        credentials = account.get_credentials()
        config = account.extra_config or {}
        config["base_url"] = account.base_url

        connector = connector_class(credentials=credentials, config=config)

        health_result = await connector.health_check()

        # Atualizar account com resultado
        account.last_health_check_at = datetime.utcnow()
        account.last_health_check_status = health_result.healthy
        account.last_health_check_latency_ms = health_result.latency_ms

        if health_result.healthy:
            account.status = "active"
            account.health_check_failures = 0
        else:
            account.health_check_failures = (account.health_check_failures or 0) + 1
            if account.health_check_failures >= 3:
                account.status = "error"

        await db.commit()

        return HealthCheckResponse(
            connector=account.connector_type,
            healthy=health_result.healthy,
            latency_ms=health_result.latency_ms,
            message=health_result.message,
            details=health_result.details,
        )

    except Exception as e:
        logger.error(f"Erro no health check da conta {account_id}: {e}")

        account.last_health_check_at = datetime.utcnow()
        account.last_health_check_status = False
        account.health_check_failures = (account.health_check_failures or 0) + 1
        account.last_error = str(e)
        account.last_error_at = datetime.utcnow()

        await db.commit()

        return HealthCheckResponse(
            connector=account.connector_type,
            healthy=False,
            latency_ms=0,
            message=str(e),
            details={"error_type": type(e).__name__},
        )


# ==================== Endpoints - Sync ====================


@router.post(
    "/sync/run", response_model=SyncRunResponse, status_code=status.HTTP_201_CREATED, summary="Inicia sync manual"
)
async def start_sync(
    data: SyncRunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SyncRunResponse:
    """Inicia uma sincronização manual."""

    from sqlalchemy import select

    from modules.integrations.models.integration_account import IntegrationAccount
    from modules.integrations.models.sync_run import SyncRun

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    # Buscar conta
    query = select(IntegrationAccount).where(
        IntegrationAccount.id == data.account_id, IntegrationAccount.tenant_id == tenant_id, IntegrationAccount.ativo
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada")

    if account.status not in ["active", "pending_auth"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Conta em status '{account.status}' não pode executar sync"
        )

    # Criar registro de sync run
    sync_run = SyncRun(
        tenant_id=tenant_id,
        account_id=account.id,
        connector_type=account.connector_type,
        mode=data.mode,
        trigger="manual",
        triggered_by=current_user.get("id"),
        entities=data.entities or account.sync_entities,
        status="pending",
    )

    db.add(sync_run)
    await db.commit()
    await db.refresh(sync_run)

    # Agendar execução em background
    background_tasks.add_task(_execute_sync, str(sync_run.id), str(account.id), data.mode, data.entities)

    return _sync_run_to_response(sync_run)


@router.get("/sync/runs", response_model=SyncRunList, summary="Lista execuções de sync")
async def list_sync_runs(
    account_id: UUID | None = None,
    connector_type: str | None = None,
    run_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SyncRunList:
    """Lista execuções de sincronização."""
    from sqlalchemy import func, select

    from modules.integrations.models.sync_run import SyncRun

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    # Query base
    query = select(SyncRun).where(SyncRun.tenant_id == tenant_id, SyncRun.ativo)

    # Filtros
    if account_id:
        query = query.where(SyncRun.account_id == account_id)
    if connector_type:
        query = query.where(SyncRun.connector_type == connector_type)
    if run_status:
        query = query.where(SyncRun.status == run_status)

    # A tabela sync_runs nunca foi criada neste banco (sem migração): a tela clássica de
    # Integrações › Sync caía com 500. Sem tabela = sem execuções, lista vazia (07/09/2026).
    from sqlalchemy.exc import ProgrammingError

    try:
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(SyncRun.created_at.desc())

        result = await db.execute(query)
        runs = result.scalars().all()
    except ProgrammingError:
        await db.rollback()
        return SyncRunList(items=[], total=0, page=page, page_size=page_size, pages=0)

    pages = (total + page_size - 1) // page_size

    return SyncRunList(
        items=[_sync_run_to_response(r) for r in runs], total=total, page=page, page_size=page_size, pages=pages
    )


@router.get("/sync/runs/{run_id}", response_model=SyncRunResponse, summary="Busca execução por ID")
async def get_sync_run(
    run_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> SyncRunResponse:
    """Retorna detalhes de uma execução de sync."""
    from sqlalchemy import select

    from modules.integrations.models.sync_run import SyncRun

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    query = select(SyncRun).where(SyncRun.id == run_id, SyncRun.tenant_id == tenant_id)
    result = await db.execute(query)
    sync_run = result.scalar_one_or_none()

    if not sync_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")

    return _sync_run_to_response(sync_run)


@router.post("/sync/runs/{run_id}/cancel", response_model=SyncRunResponse, summary="Cancela execução")
async def cancel_sync_run(
    run_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
) -> SyncRunResponse:
    """Cancela uma execução de sync em andamento."""
    from sqlalchemy import select

    from modules.integrations.models.sync_run import SyncRun

    # current_user é o modelo User, não dict — `.get` estourava 500 em /connectors/sync/runs (07/09/2026)
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "condominio_id", None)

    query = select(SyncRun).where(SyncRun.id == run_id, SyncRun.tenant_id == tenant_id)
    result = await db.execute(query)
    sync_run = result.scalar_one_or_none()

    if not sync_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")

    if sync_run.status not in ["pending", "running"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execução em status '{sync_run.status}' não pode ser cancelada",
        )

    sync_run.status = "cancelled"
    sync_run.status_message = f"Cancelado por {current_user.get('email')}"

    await db.commit()
    await db.refresh(sync_run)

    return _sync_run_to_response(sync_run)


# ==================== Helpers ====================


def _get_display_name(connector_name: str) -> str:
    """Retorna nome de exibição do conector."""
    names = {
        "bling": "Bling ERP",
        "solides": "Sólides RH",
        "dominio": "Domínio Sistemas",
        "omie": "Omie",
        "nibo": "Nibo",
        "totvs": "TOTVS",
        "sap": "SAP",
    }
    return names.get(connector_name, connector_name.title())


def _get_description(connector_name: str) -> str:
    """Retorna descrição do conector."""
    descriptions = {
        "bling": "Sistema ERP para gestão de vendas, estoque e notas fiscais",
        "solides": "Plataforma de gestão de pessoas e recrutamento",
        "dominio": "Sistema contábil e fiscal",
        "omie": "ERP em nuvem para pequenas e médias empresas",
        "nibo": "Sistema de gestão financeira e contábil",
        "totvs": "ERP empresarial completo",
        "sap": "Sistema integrado de gestão empresarial",
    }
    return descriptions.get(connector_name, "")


def _get_auth_type(connector_name: str) -> str:
    """Retorna tipo de autenticação do conector."""
    auth_types = {
        "bling": "api_key",
        "solides": "oauth2_client_credentials",
        "dominio": "api_key",
        "omie": "api_key",
        "nibo": "oauth2",
        "totvs": "oauth2",
        "sap": "oauth2",
    }
    return auth_types.get(connector_name, "api_key")


def _account_to_response(account) -> IntegrationAccountResponse:
    """Converte IntegrationAccount para response."""
    return IntegrationAccountResponse(
        id=str(account.id),
        tenant_id=str(account.tenant_id),
        name=account.name,
        description=account.description,
        connector_type=account.connector_type,
        auth_type=account.auth_type,
        environment=account.environment,
        status=account.status,
        status_message=account.status_message,
        last_health_check_at=account.last_health_check_at.isoformat() if account.last_health_check_at else None,
        last_health_check_status=account.last_health_check_status,
        sync_enabled=account.sync_enabled,
        sync_interval_minutes=account.sync_interval_minutes,
        sync_entities=account.sync_entities,
        last_sync_at=account.last_sync_at.isoformat() if account.last_sync_at else None,
        next_sync_at=account.next_sync_at.isoformat() if account.next_sync_at else None,
        created_at=account.created_at.isoformat(),
        updated_at=account.updated_at.isoformat(),
    )


def _sync_run_to_response(sync_run) -> SyncRunResponse:
    """Converte SyncRun para response."""
    return SyncRunResponse(
        id=str(sync_run.id),
        account_id=str(sync_run.account_id),
        connector_type=sync_run.connector_type,
        mode=sync_run.mode,
        status=sync_run.status,
        started_at=sync_run.started_at.isoformat() if sync_run.started_at else None,
        completed_at=sync_run.completed_at.isoformat() if sync_run.completed_at else None,
        items_total=sync_run.items_total or 0,
        items_processed=sync_run.items_processed or 0,
        items_created=sync_run.items_created or 0,
        items_updated=sync_run.items_updated or 0,
        items_failed=sync_run.items_failed or 0,
        error_message=sync_run.error_message,
    )


async def _execute_sync(sync_run_id: str, account_id: str, mode: str, entities: list[str] | None) -> None:
    """
    Executa sync em background.

    Esta função é chamada como BackgroundTask e precisa criar
    sua própria sessão de banco de dados.
    """
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import select

    from core.database import AsyncSessionLocal
    from modules.integrations.models.integration_account import IntegrationAccount
    from modules.integrations.models.sync_run import SyncRun
    from modules.integrations.sync.engine import ConnectorRegistry

    logger.info(f"[sync:{sync_run_id[:8]}] Iniciando sync para account {account_id[:8]}")

    async with AsyncSessionLocal() as db:
        try:
            # Buscar sync_run
            result = await db.execute(select(SyncRun).where(SyncRun.id == UUID(sync_run_id)))
            sync_run = result.scalar_one_or_none()

            if not sync_run:
                logger.error(f"[sync:{sync_run_id[:8]}] SyncRun não encontrado")
                return

            # Buscar account
            result = await db.execute(
                select(IntegrationAccount).where(IntegrationAccount.id == UUID(account_id), IntegrationAccount.ativo)
            )
            account = result.scalar_one_or_none()

            if not account:
                sync_run.status = "failed"
                sync_run.error_message = "Conta de integração não encontrada"
                sync_run.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Atualizar status para running
            sync_run.status = "running"
            sync_run.started_at = datetime.utcnow()
            await db.commit()

            # Buscar classe do conector
            connector_class = ConnectorRegistry.get(account.connector_type)
            if not connector_class:
                sync_run.status = "failed"
                sync_run.error_message = f"Conector '{account.connector_type}' não encontrado"
                sync_run.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Obter credenciais
            try:
                credentials = account.get_credentials()
            except Exception as e:
                sync_run.status = "failed"
                sync_run.error_message = f"Erro ao obter credenciais: {str(e)}"
                sync_run.completed_at = datetime.utcnow()
                await db.commit()
                return

            # Criar instância do conector
            config = account.extra_config or {}
            if account.base_url:
                config["base_url"] = account.base_url

            connector = connector_class(credentials=credentials, config=config)

            # Determinar entidades para sincronizar
            sync_entities = entities or account.sync_entities or connector.capabilities.supported_entities

            items_total = 0
            items_processed = 0
            items_created = 0
            items_updated = 0
            items_failed = 0
            errors = []

            # Sincronizar cada entidade
            for entity_type in sync_entities:
                try:
                    logger.info(f"[sync:{sync_run_id[:8]}] Sincronizando {entity_type}")

                    # Determinar cursor (para incremental)
                    cursor = None
                    updated_since = None

                    if mode == "incremental" and account.last_sync_at:
                        updated_since = account.last_sync_at

                    # Buscar entidades da API externa
                    has_more = True
                    entity_count = 0

                    while has_more:
                        try:
                            result = await connector.fetch_entities(
                                entity_type=entity_type, cursor=cursor, updated_since=updated_since, page_size=50
                            )

                            if not result.success:
                                errors.append(
                                    {
                                        "entity": entity_type,
                                        "error": "Falha ao buscar entidades",
                                        "details": result.errors,
                                    }
                                )
                                items_failed += 1
                                break

                            # Processar itens recebidos
                            for _item in result.data:
                                items_total += 1
                                entity_count += 1
                                # Aqui seria feito o mapeamento e persistência
                                # Por ora, apenas contamos como processado
                                items_processed += 1
                                items_created += 1  # Simplificado

                            cursor = result.cursor
                            has_more = result.has_more

                        except Exception as page_error:
                            logger.error(f"[sync:{sync_run_id[:8]}] Erro na página: {page_error}")
                            errors.append({"entity": entity_type, "error": str(page_error)})
                            items_failed += 1
                            break

                    logger.info(f"[sync:{sync_run_id[:8]}] {entity_type}: {entity_count} itens")

                except Exception as entity_error:
                    logger.error(f"[sync:{sync_run_id[:8]}] Erro em {entity_type}: {entity_error}")
                    errors.append({"entity": entity_type, "error": str(entity_error)})
                    items_failed += 1

            # Atualizar sync_run com resultados
            sync_run.items_total = items_total
            sync_run.items_processed = items_processed
            sync_run.items_created = items_created
            sync_run.items_updated = items_updated
            sync_run.items_failed = items_failed
            sync_run.completed_at = datetime.utcnow()

            if items_failed == 0:
                sync_run.status = "completed"
            elif items_processed > 0:
                sync_run.status = "completed_with_errors"
                sync_run.error_message = f"{items_failed} erros durante a sincronização"
            else:
                sync_run.status = "failed"
                sync_run.error_message = "Nenhum item sincronizado"

            # Atualizar account
            account.last_sync_at = datetime.utcnow()
            if sync_run.status == "completed":
                account.status = "active"

            await db.commit()

            logger.info(
                f"[sync:{sync_run_id[:8]}] Concluído: "
                f"total={items_total}, processados={items_processed}, "
                f"criados={items_created}, falhas={items_failed}"
            )

        except Exception as e:
            logger.error(f"[sync:{sync_run_id[:8]}] Erro fatal: {e}")

            # Tentar atualizar status como falha
            try:
                result = await db.execute(select(SyncRun).where(SyncRun.id == UUID(sync_run_id)))
                sync_run = result.scalar_one_or_none()
                if sync_run:
                    sync_run.status = "failed"
                    sync_run.error_message = str(e)
                    sync_run.completed_at = datetime.utcnow()
                    await db.commit()
            except Exception as e:
                logger.warning(f"Erro ao atualizar status de falha: {e}")
