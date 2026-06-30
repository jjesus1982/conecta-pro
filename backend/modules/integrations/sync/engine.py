"""
SyncEngine - Orquestrador de sincronizações.
Sprint 33: Integration Framework
"""

import builtins
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.integrations.connectors.base.connector import BaseConnector
from modules.integrations.connectors.base.exceptions import ConnectorError
from modules.integrations.models.integration_account import AccountStatus, IntegrationAccount
from modules.integrations.models.sync_run import SyncRun, SyncRunMode, SyncRunStatus, SyncRunTrigger
from modules.integrations.models.sync_state import SyncState
from modules.integrations.sync.jobs.base import SyncJob

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """
    Registry de conectores disponíveis.
    """

    _connectors: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_class: type[BaseConnector]) -> type[BaseConnector]:
        """
        Registra um conector.
        Pode ser usado como decorator.
        """
        cls._connectors[connector_class.NAME] = connector_class
        logger.info(f"Conector registrado: {connector_class.NAME}")
        return connector_class

    @classmethod
    def get(cls, name: str) -> type[BaseConnector] | None:
        """Retorna classe do conector pelo nome."""
        return cls._connectors.get(name)

    @classmethod
    def list(cls) -> list[str]:
        """Lista conectores disponíveis."""
        return list(cls._connectors.keys())

    @classmethod
    def list_connectors(cls) -> dict:
        """Dict {nome: classe} dos conectores registrados (usado por service/controller)."""
        return dict(cls._connectors)

    @classmethod
    def get_info(cls) -> builtins.list[dict[str, Any]]:
        """Retorna informações de todos os conectores."""
        result = []
        for name, connector_class in cls._connectors.items():
            # Criar instância temporária para pegar capabilities
            caps = connector_class.capabilities.fget(None) if hasattr(connector_class, "capabilities") else None
            result.append(
                {
                    "name": name,
                    "version": connector_class.VERSION,
                    "capabilities": {
                        "entities": caps.supported_entities if caps else [],
                        "webhooks": caps.supports_webhooks if caps else False,
                        "write": caps.supports_write if caps else False,
                    }
                    if caps
                    else {},
                }
            )
        return result


class SyncJobRegistry:
    """
    Registry de sync jobs por conector e entidade.
    """

    _jobs: dict[str, dict[str, type[SyncJob]]] = {}

    @classmethod
    def register(cls, connector_name: str, entity_type: str, job_class: type[SyncJob]) -> None:
        """Registra um sync job."""
        if connector_name not in cls._jobs:
            cls._jobs[connector_name] = {}
        cls._jobs[connector_name][entity_type] = job_class
        logger.debug(f"SyncJob registrado: {connector_name}/{entity_type}")

    @classmethod
    def get(cls, connector_name: str, entity_type: str) -> type[SyncJob] | None:
        """Retorna classe do sync job."""
        return cls._jobs.get(connector_name, {}).get(entity_type)

    @classmethod
    def list_entities(cls, connector_name: str) -> list[str]:
        """Lista entidades disponíveis para um conector."""
        return list(cls._jobs.get(connector_name, {}).keys())


class SyncEngine:
    """
    Orquestrador de sincronizações.
    Gerencia execução de syncs e mantém estado.
    """

    def __init__(self, db: AsyncSession):
        """
        Inicializa o engine.

        Args:
            db: Sessão do banco de dados
        """
        self.db = db

    async def get_account(self, account_id: UUID) -> IntegrationAccount | None:
        """Busca conta de integração."""
        result = await self.db.execute(
            select(IntegrationAccount).where(IntegrationAccount.id == account_id, IntegrationAccount.ativo.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_or_create_sync_state(
        self, account_id: UUID, tenant_id: UUID, connector_type: str, entity_type: str
    ) -> SyncState:
        """Busca ou cria estado de sync."""
        result = await self.db.execute(
            select(SyncState).where(
                SyncState.tenant_id == tenant_id,
                SyncState.account_id == account_id,
                SyncState.entity_type == entity_type,
                SyncState.ativo.is_(True),
            )
        )
        state = result.scalar_one_or_none()

        if not state:
            state = SyncState(
                tenant_id=tenant_id, account_id=account_id, connector_type=connector_type, entity_type=entity_type
            )
            self.db.add(state)
            await self.db.flush()

        return state

    async def create_sync_run(
        self,
        account: IntegrationAccount,
        entities: list[str],
        mode: SyncRunMode = SyncRunMode.INCREMENTAL,
        trigger: SyncRunTrigger = SyncRunTrigger.MANUAL,
        triggered_by: UUID | None = None,
    ) -> SyncRun:
        """Cria registro de execução de sync."""
        run = SyncRun(
            tenant_id=account.tenant_id,
            account_id=account.id,
            connector_type=account.connector_type.value,
            mode=mode,
            trigger=trigger,
            triggered_by=triggered_by,
            entities=entities,
            status=SyncRunStatus.PENDING,
            correlation_id=f"sync-{uuid4().hex[:8]}",
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def run_sync(
        self,
        account_id: UUID,
        entities: list[str] | None = None,
        mode: SyncRunMode = SyncRunMode.INCREMENTAL,
        trigger: SyncRunTrigger = SyncRunTrigger.MANUAL,
        triggered_by: UUID | None = None,
        credentials_decrypted: dict[str, Any] | None = None,
    ) -> SyncRun:
        """
        Executa sincronização.

        Args:
            account_id: ID da conta de integração
            entities: Lista de entidades para sincronizar (None = todas)
            mode: Modo de sync (incremental/full)
            trigger: O que disparou o sync
            triggered_by: ID do usuário que disparou (se manual)
            credentials_decrypted: Credenciais já decriptografadas

        Returns:
            SyncRun com resultado

        Raises:
            ConnectorError: Em caso de falha
        """
        # Buscar conta
        account = await self.get_account(account_id)
        if not account:
            raise ConnectorError("Conta de integração não encontrada", error_code="ACCOUNT_NOT_FOUND")

        if account.status != AccountStatus.ACTIVE:
            raise ConnectorError(
                f"Conta não está ativa (status={account.status.value})", error_code="ACCOUNT_NOT_ACTIVE"
            )

        # Buscar classe do conector
        connector_class = ConnectorRegistry.get(account.connector_type.value)
        if not connector_class:
            raise ConnectorError(
                f"Conector não encontrado: {account.connector_type.value}", error_code="CONNECTOR_NOT_FOUND"
            )

        # Determinar entidades
        available_entities = SyncJobRegistry.list_entities(account.connector_type.value)
        if entities:
            # Validar entidades solicitadas
            invalid = set(entities) - set(available_entities)
            if invalid:
                raise ConnectorError(f"Entidades não suportadas: {invalid}", error_code="INVALID_ENTITIES")
            sync_entities = entities
        else:
            sync_entities = available_entities

        if not sync_entities:
            raise ConnectorError("Nenhuma entidade para sincronizar", error_code="NO_ENTITIES")

        # Criar sync run
        sync_run = await self.create_sync_run(
            account=account, entities=sync_entities, mode=mode, trigger=trigger, triggered_by=triggered_by
        )

        logger.info(
            f"[{sync_run.correlation_id}] Iniciando sync: "
            f"connector={account.connector_type.value}, "
            f"entities={sync_entities}, mode={mode.value}"
        )

        # Iniciar execução
        sync_run.start(worker_id=f"engine-{uuid4().hex[:8]}", worker_host="localhost")
        await self.db.commit()

        try:
            # Criar instância do conector
            async with connector_class(
                account_id=account.id,
                tenant_id=account.tenant_id,
                credentials=credentials_decrypted or {},
                config=account.extra_config,
            ) as connector:
                # Health check
                health = await connector.health_check()
                if not health.healthy:
                    raise ConnectorError(f"Health check falhou: {health.message}", connector=connector.NAME)

                # Executar sync para cada entidade
                for entity_type in sync_entities:
                    job_class = SyncJobRegistry.get(account.connector_type.value, entity_type)

                    if not job_class:
                        logger.warning(f"[{sync_run.correlation_id}] Job não encontrado para {entity_type}")
                        continue

                    # Buscar estado
                    sync_state = await self.get_or_create_sync_state(
                        account_id=account.id,
                        tenant_id=account.tenant_id,
                        connector_type=account.connector_type.value,
                        entity_type=entity_type,
                    )

                    # Criar e executar job
                    job = job_class(
                        connector=connector,
                        db=self.db,
                        tenant_id=account.tenant_id,
                        account_id=account.id,
                        correlation_id=sync_run.correlation_id,
                    )

                    full_sync = mode == SyncRunMode.FULL or sync_state.needs_full_sync
                    result = await job.run(sync_state=sync_state if not full_sync else None, full_sync=full_sync)

                    # Atualizar estatísticas do run
                    sync_run.increment_items(
                        processed=result.items_processed,
                        created=result.items_created,
                        updated=result.items_updated,
                        skipped=result.items_skipped,
                        failed=result.items_failed,
                    )
                    sync_run.items_total += result.items_total

                    # Atualizar estado
                    if result.success:
                        if full_sync:
                            sync_state.complete_full_sync(
                                items_synced=result.items_processed, duration_ms=result.duration_ms
                            )
                        else:
                            sync_state.complete_sync(
                                items_synced=result.items_processed,
                                duration_ms=result.duration_ms,
                                cursor=result.last_cursor,
                            )
                    else:
                        sync_state.mark_failure(
                            result.errors[0].get("error", "Unknown error") if result.errors else "Unknown error"
                        )

                    # Adicionar erros ao run
                    for error in result.errors:
                        sync_run.add_error({"entity": entity_type, **error})

                # Finalizar run
                if sync_run.items_failed == 0:
                    sync_run.complete_success(
                        summary={
                            "entities_synced": sync_entities,
                        }
                    )
                else:
                    sync_run.complete_partial(
                        summary={"entities_synced": sync_entities}, warnings=[f"{sync_run.items_failed} itens falharam"]
                    )

                # Atualizar account
                account.mark_sync_completed()

        except Exception as e:
            logger.error(f"[{sync_run.correlation_id}] Erro no sync: {e}")
            sync_run.complete_failed(error_code="SYNC_ERROR", error_message=str(e))
            account.mark_error(str(e))

        await self.db.commit()

        logger.info(
            f"[{sync_run.correlation_id}] Sync finalizado: "
            f"status={sync_run.status.value}, "
            f"total={sync_run.items_total}, "
            f"criados={sync_run.items_created}, "
            f"atualizados={sync_run.items_updated}, "
            f"falhas={sync_run.items_failed}"
        )

        return sync_run

    async def cancel_sync(self, sync_run_id: UUID, reason: str = "Cancelado pelo usuário") -> bool:
        """Cancela uma execução de sync em andamento."""
        result = await self.db.execute(
            select(SyncRun).where(SyncRun.id == sync_run_id, SyncRun.status == SyncRunStatus.RUNNING)
        )
        run = result.scalar_one_or_none()

        if not run:
            return False

        run.cancel(reason)
        await self.db.commit()

        logger.info(f"Sync {sync_run_id} cancelado: {reason}")
        return True

    async def get_sync_runs(
        self,
        account_id: UUID | None = None,
        tenant_id: UUID | None = None,
        status: SyncRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SyncRun]:
        """Lista execuções de sync com filtros."""
        query = select(SyncRun).where(SyncRun.ativo.is_(True))

        if account_id:
            query = query.where(SyncRun.account_id == account_id)
        if tenant_id:
            query = query.where(SyncRun.tenant_id == tenant_id)
        if status:
            query = query.where(SyncRun.status == status)

        query = query.order_by(SyncRun.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_sync_run(self, sync_run_id: UUID) -> SyncRun | None:
        """Busca uma execução específica."""
        result = await self.db.execute(select(SyncRun).where(SyncRun.id == sync_run_id))
        return result.scalar_one_or_none()
