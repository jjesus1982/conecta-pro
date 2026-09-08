"""
Controller para Conectores Externos
Sprint 33: Integration Framework

Gerencia contas de integração e execução de syncs com sistemas externos.
"""

import logging

from fastapi import APIRouter

from modules.integrations.schemas.connector_schemas import (
    IntegrationAccountResponse,
    SyncRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/connectors", tags=["Conectores Externos"])


# ==================== Endpoints - Conectores ====================


# ==================== Endpoints - Contas ====================


# ==================== Endpoints - Health Check ====================


# ==================== Endpoints - Sync ====================


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
