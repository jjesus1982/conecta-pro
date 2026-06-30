"""
Repositories para Comunicacao Operacional.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

from __future__ import annotations

import builtins
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.communication.models.alert import Alert
from modules.operacional.communication.models.announcement import (
    Announcement,
    AnnouncementStatus,
)
from modules.operacional.communication.models.announcement_read import AnnouncementRead
from modules.operacional.communication.models.notification import Notification
from modules.operacional.communication.schemas.communication_schemas import (
    AlertCreate,
    AlertFilter,
    AnnouncementCreate,
    AnnouncementFilter,
    AnnouncementUpdate,
    NotificationCreate,
    NotificationFilter,
)

logger = logging.getLogger(__name__)


class AnnouncementRepository:
    """
    Repository para operacoes CRUD de Comunicados.

    Fornece metodos para criar, listar, atualizar e gerenciar comunicados,
    incluindo publicacao, agendamento e controle de leituras.

    Attributes:
        db: Sessao assincrona do banco de dados

    Example:
        >>> repo = AnnouncementRepository(db)
        >>> announcement = await repo.create(data, tenant_id, created_by)
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao assincrona do banco de dados
        """
        self.db = db

    async def create(
        self,
        data: AnnouncementCreate,
        tenant_id: str,
        created_by: str,
    ) -> Announcement:
        """
        Cria um novo comunicado.

        Args:
            data: Dados do comunicado
            tenant_id: ID do tenant
            created_by: ID do usuario criador

        Returns:
            Comunicado criado
        """
        attachments = None
        if data.attachments:
            attachments = [a.model_dump() for a in data.attachments]

        # Determina status inicial
        status = AnnouncementStatus.DRAFT.value
        if data.publish_at:
            status = AnnouncementStatus.SCHEDULED.value

        announcement = Announcement(
            id=str(uuid4()),
            tenant_id=tenant_id,
            destinatarios_tipo=data.target_type.value if hasattr(data.target_type, "value") else str(data.target_type),
            destinatarios_funcionarios=data.target_ids,
            titulo=data.title,
            conteudo=data.content,
            prioridade=data.priority.value if hasattr(data.priority, "value") else str(data.priority),
            tipo=data.category.value if hasattr(data.category, "value") else str(data.category),
            data_publicacao=data.publish_at,
            data_expiracao=data.expires_at,
            requer_confirmacao=data.requires_acknowledgment,
            anexos=attachments,
            status=status,
            created_by=created_by,
            extra_data={"target_roles": data.target_roles} if data.target_roles else None,
        )

        self.db.add(announcement)
        await self.db.commit()
        await self.db.refresh(announcement)

        logger.info(f"Comunicado criado: {announcement.id}")
        return announcement

    async def get_by_id(
        self,
        announcement_id: str,
        tenant_id: str | None = None,
    ) -> Announcement | None:
        """
        Busca comunicado por ID.

        Args:
            announcement_id: ID do comunicado
            tenant_id: ID do tenant (opcional, para validacao)

        Returns:
            Comunicado ou None
        """
        query = select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.is_active.is_(True),
        )

        if tenant_id:
            query = query.where(Announcement.tenant_id == tenant_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: str,
        filters: AnnouncementFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[builtins.list[Announcement], int]:
        """
        Lista comunicados com filtros e paginacao.

        Args:
            tenant_id: ID do tenant
            filters: Filtros de busca
            page: Pagina atual
            page_size: Itens por pagina

        Returns:
            Tupla (comunicados, total)
        """
        query = select(Announcement).where(
            Announcement.tenant_id == tenant_id,
            Announcement.is_active.is_(True),
        )

        # Aplica filtros
        if filters:
            query = self._apply_announcement_filters(query, filters)

        # Count total
        count_query = select(func.count(Announcement.id)).where(
            Announcement.tenant_id == tenant_id,
            Announcement.is_active.is_(True),
        )
        if filters:
            count_query = self._apply_announcement_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenacao e paginacao
        query = query.order_by(Announcement.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        announcements = list(result.scalars().all())

        return announcements, total

    def _apply_announcement_filters(self, query, filters: AnnouncementFilter):
        """Aplica filtros a query de comunicados."""
        if filters.status:
            query = query.where(Announcement.status == filters.status.value)

        if filters.priority:
            # prioridade é a coluna real; priority é @property alias
            query = query.where(Announcement.prioridade == filters.priority.value)

        if filters.category:
            # tipo é a coluna real; category é @property alias
            query = query.where(Announcement.tipo == filters.category.value)

        if filters.target_type:
            # destinatarios_tipo é a coluna real; target_type é @property alias
            query = query.where(Announcement.destinatarios_tipo == filters.target_type.value)

        if filters.requires_acknowledgment is not None:
            # requer_confirmacao é a coluna real; requires_acknowledgment é @property alias
            query = query.where(Announcement.requer_confirmacao == filters.requires_acknowledgment)

        if filters.is_active is not None:
            query = query.where(Announcement.is_active == filters.is_active)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    # titulo/conteudo são as colunas reais; title/content são @property aliases
                    Announcement.titulo.ilike(search_term),
                    Announcement.conteudo.ilike(search_term),
                )
            )

        if filters.created_after:
            query = query.where(Announcement.created_at >= filters.created_after)

        if filters.created_before:
            query = query.where(Announcement.created_at <= filters.created_before)

        return query

    async def update(
        self,
        announcement_id: str,
        data: AnnouncementUpdate,
        tenant_id: str,
    ) -> Announcement | None:
        """
        Atualiza um comunicado.

        Args:
            announcement_id: ID do comunicado
            data: Dados para atualizacao
            tenant_id: ID do tenant

        Returns:
            Comunicado atualizado ou None
        """
        announcement = await self.get_by_id(announcement_id, tenant_id)
        if not announcement:
            return None

        # Nao permite editar comunicados publicados
        if announcement.status == AnnouncementStatus.PUBLISHED.value:
            logger.warning(f"Tentativa de editar comunicado publicado: {announcement_id}")
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "attachments" and value:
                value = [a.model_dump() if hasattr(a, "model_dump") else a for a in value]
            if hasattr(value, "value"):  # Enum
                value = value.value
            setattr(announcement, field, value)

        announcement.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(announcement)

        logger.info(f"Comunicado atualizado: {announcement_id}")
        return announcement

    async def delete(
        self,
        announcement_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Soft delete de comunicado.

        Args:
            announcement_id: ID do comunicado
            tenant_id: ID do tenant

        Returns:
            True se deletado
        """
        announcement = await self.get_by_id(announcement_id, tenant_id)
        if not announcement:
            return False

        announcement.is_active = False
        announcement.status = AnnouncementStatus.CANCELLED.value
        announcement.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Comunicado deletado (soft): {announcement_id}")
        return True

    async def publish(
        self,
        announcement_id: str,
        tenant_id: str,
        published_by: str,
        schedule_at: datetime | None = None,
    ) -> Announcement | None:
        """
        Publica um comunicado.

        Args:
            announcement_id: ID do comunicado
            tenant_id: ID do tenant
            published_by: ID do usuario que publica
            schedule_at: Data/hora para agendamento (None = publicar agora)

        Returns:
            Comunicado publicado ou None
        """
        announcement = await self.get_by_id(announcement_id, tenant_id)
        if not announcement:
            return None

        if not announcement.can_be_published():
            logger.warning(f"Comunicado nao pode ser publicado: {announcement_id}")
            return None

        if schedule_at:
            announcement.status = AnnouncementStatus.SCHEDULED.value
            announcement.publish_at = schedule_at
        else:
            announcement.status = AnnouncementStatus.PUBLISHED.value
            announcement.published_at = datetime.utcnow()
            announcement.published_by = published_by

        announcement.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(announcement)

        logger.info(f"Comunicado {'agendado' if schedule_at else 'publicado'}: {announcement_id}")
        return announcement

    async def get_for_user(
        self,
        tenant_id: str,
        user_id: str,
        user_roles: builtins.list[str],
        department_id: str | None = None,
        post_id: str | None = None,
        only_unread: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[builtins.list[Announcement], int]:
        """
        Busca comunicados relevantes para um usuario.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuario
            user_roles: Roles do usuario
            department_id: ID do departamento (opcional)
            post_id: ID do posto (opcional)
            only_unread: Se deve retornar apenas nao lidos
            page: Pagina atual
            page_size: Itens por pagina

        Returns:
            Tupla (comunicados, total)
        """
        # Comunicados publicados e nao expirados
        # Nota: usar data_expiracao (coluna real) em vez de expires_at (@property)
        query = select(Announcement).where(
            Announcement.tenant_id == tenant_id,
            Announcement.is_active.is_(True),
            Announcement.status == AnnouncementStatus.PUBLISHED.value,
            or_(
                Announcement.data_expiracao.is_(None),
                Announcement.data_expiracao > datetime.utcnow(),
            ),
        )

        # Filtro por destinatario
        # FIX: usar colunas reais do DB em vez das @property Python que nao
        # sao atributos SQLAlchemy e causavam AttributeError → 500.
        # target_type/@property → destinatarios_tipo (coluna real)
        # target_ids/@property  → destinatarios_funcionarios / destinatarios_postos
        # target_roles/@property → sem coluna no DB, removido
        target_conditions = [
            or_(
                Announcement.destinatarios_tipo == "todos",
                Announcement.destinatarios_tipo == "all",
            ),
            Announcement.destinatarios_funcionarios.contains([user_id]),
            Announcement.destinatarios_postos.contains([user_id]),
        ]

        query = query.where(or_(*target_conditions))

        # Filtro por nao lidos
        if only_unread:
            subquery = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user_id)
            query = query.where(Announcement.id.notin_(subquery))

        # Count
        count_query = query.with_only_columns(func.count(Announcement.id))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenacao e paginacao
        # FIX: usar coluna real 'prioridade' em vez da @property 'priority'
        query = query.order_by(
            Announcement.prioridade.desc(),
            Announcement.created_at.desc(),
        )
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        announcements = list(result.scalars().all())

        return announcements, total

    async def mark_as_read(
        self,
        announcement_id: str,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AnnouncementRead | None:
        """
        Marca comunicado como lido.

        Args:
            announcement_id: ID do comunicado
            user_id: ID do usuario
            ip_address: IP do usuario
            user_agent: User-Agent

        Returns:
            Registro de leitura ou None
        """
        # Verifica se ja leu
        existing = await self.db.execute(
            select(AnnouncementRead).where(
                AnnouncementRead.announcement_id == announcement_id,
                AnnouncementRead.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none():
            return None

        read = AnnouncementRead.create_read(
            announcement_id=announcement_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(read)
        await self.db.commit()
        await self.db.refresh(read)

        logger.info(f"Leitura registrada: {announcement_id} por {user_id}")
        return read

    async def acknowledge(
        self,
        announcement_id: str,
        user_id: str,
    ) -> AnnouncementRead | None:
        """
        Confirma leitura de comunicado.

        Args:
            announcement_id: ID do comunicado
            user_id: ID do usuario

        Returns:
            Registro de leitura atualizado ou None
        """
        result = await self.db.execute(
            select(AnnouncementRead).where(
                AnnouncementRead.announcement_id == announcement_id,
                AnnouncementRead.user_id == user_id,
            )
        )
        read = result.scalar_one_or_none()

        if not read:
            return None

        read.acknowledge()
        await self.db.commit()
        await self.db.refresh(read)

        logger.info(f"Confirmacao registrada: {announcement_id} por {user_id}")
        return read

    async def get_read_stats(
        self,
        announcement_id: str,
        tenant_id: str,
    ) -> dict:
        """
        Obtem estatisticas de leitura de um comunicado.

        Args:
            announcement_id: ID do comunicado
            tenant_id: ID do tenant

        Returns:
            Dicionario com estatisticas
        """
        announcement = await self.get_by_id(announcement_id, tenant_id)
        if not announcement:
            return {}

        result = await self.db.execute(
            select(AnnouncementRead).where(AnnouncementRead.announcement_id == announcement_id)
        )
        reads = list(result.scalars().all())

        total_reads = len(reads)
        total_acknowledgments = len([r for r in reads if r.is_acknowledged])

        return {
            "total_recipients": announcement._get_total_targets(),
            "total_reads": total_reads,
            "total_acknowledgments": total_acknowledgments,
            "read_percentage": announcement.read_percentage,
            "acknowledgment_percentage": ((total_acknowledgments / total_reads * 100) if total_reads > 0 else 0),
            "reads": reads,
        }

    async def process_scheduled(self) -> int:
        """
        Processa comunicados agendados para publicacao.

        Returns:
            Quantidade de comunicados publicados
        """
        result = await self.db.execute(
            select(Announcement).where(
                Announcement.status == AnnouncementStatus.SCHEDULED.value,
                Announcement.data_publicacao <= datetime.utcnow(),  # coluna real; publish_at é @property
                Announcement.is_active.is_(True),
            )
        )
        scheduled = list(result.scalars().all())

        count = 0
        for announcement in scheduled:
            announcement.status = AnnouncementStatus.PUBLISHED.value
            announcement.data_publicacao = datetime.utcnow()  # coluna real; published_at é @property sem setter
            announcement.updated_at = datetime.utcnow()
            count += 1

        if count > 0:
            await self.db.commit()
            logger.info(f"Comunicados agendados publicados: {count}")

        return count

    async def process_expired(self) -> int:
        """
        Processa comunicados expirados.

        Returns:
            Quantidade de comunicados expirados
        """
        result = await self.db.execute(
            select(Announcement).where(
                Announcement.status == AnnouncementStatus.PUBLISHED.value,
                Announcement.data_expiracao <= datetime.utcnow(),  # coluna real, nao @property
                Announcement.is_active.is_(True),
            )
        )
        expired = list(result.scalars().all())

        count = 0
        for announcement in expired:
            announcement.status = AnnouncementStatus.EXPIRED.value
            announcement.updated_at = datetime.utcnow()
            count += 1

        if count > 0:
            await self.db.commit()
            logger.info(f"Comunicados expirados: {count}")

        return count


class NotificationRepository:
    """
    Repository para operacoes CRUD de Notificacoes.

    Fornece metodos para criar, listar e gerenciar notificacoes,
    incluindo marcacao de leitura e envio em massa.

    Attributes:
        db: Sessao assincrona do banco de dados
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao assincrona do banco de dados
        """
        self.db = db

    async def create(
        self,
        data: NotificationCreate,
        tenant_id: str,
    ) -> Notification:
        """
        Cria uma nova notificacao.

        Args:
            data: Dados da notificacao
            tenant_id: ID do tenant

        Returns:
            Notificacao criada
        """

        notification = Notification(
            id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=data.user_id,
            title=data.title,
            body=data.body,
            type=data.type.value,
            channels=[c.value for c in data.channels],
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            action_url=data.action_url,
            metadata=data.metadata or {},
        )

        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        logger.info(f"Notificacao criada: {notification.id}")
        return notification

    async def create_bulk(
        self,
        notifications: list[NotificationCreate],
        tenant_id: str,
    ) -> list[Notification]:
        """
        Cria multiplas notificacoes.

        Args:
            notifications: Lista de dados de notificacao
            tenant_id: ID do tenant

        Returns:
            Lista de notificacoes criadas
        """
        created = []
        for data in notifications:
            notification = await self.create(data, tenant_id)
            created.append(notification)

        logger.info(f"Notificacoes criadas em massa: {len(created)}")
        return created

    async def get_by_id(
        self,
        notification_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> Notification | None:
        """
        Busca notificacao por ID.

        Args:
            notification_id: ID da notificacao
            tenant_id: ID do tenant (opcional)
            user_id: ID do usuario (opcional)

        Returns:
            Notificacao ou None
        """
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.is_active.is_(True),
        )

        if tenant_id:
            query = query.where(Notification.tenant_id == tenant_id)
        if user_id:
            query = query.where(Notification.user_id == user_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        tenant_id: str,
        user_id: str,
        filters: NotificationFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        """
        Lista notificacoes de um usuario.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuario
            filters: Filtros de busca
            page: Pagina atual
            page_size: Itens por pagina

        Returns:
            Tupla (notificacoes, total)
        """
        query = select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.is_active.is_(True),
        )

        if filters:
            query = self._apply_notification_filters(query, filters)

        # Count
        count_query = select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.is_active.is_(True),
        )
        if filters:
            count_query = self._apply_notification_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenacao e paginacao
        query = query.order_by(Notification.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        notifications = list(result.scalars().all())

        return notifications, total

    def _apply_notification_filters(self, query, filters: NotificationFilter):
        """Aplica filtros a query de notificacoes."""
        if filters.type:
            query = query.where(Notification.type == filters.type.value)

        if filters.is_read is not None:
            if filters.is_read:
                query = query.where(Notification.read_at.isnot(None))
            else:
                query = query.where(Notification.read_at.is_(None))

        if filters.is_sent is not None:
            if filters.is_sent:
                query = query.where(Notification.sent_at.isnot(None))
            else:
                query = query.where(Notification.sent_at.is_(None))

        if filters.reference_type:
            query = query.where(Notification.reference_type == filters.reference_type)

        if filters.created_after:
            query = query.where(Notification.created_at >= filters.created_after)

        if filters.created_before:
            query = query.where(Notification.created_at <= filters.created_before)

        return query

    async def mark_as_read(
        self,
        notification_id: str,
        user_id: str,
    ) -> Notification | None:
        """
        Marca notificacao como lida.

        Args:
            notification_id: ID da notificacao
            user_id: ID do usuario

        Returns:
            Notificacao atualizada ou None
        """
        notification = await self.get_by_id(notification_id, user_id=user_id)
        if not notification:
            return None

        notification.mark_as_read()
        await self.db.commit()
        await self.db.refresh(notification)

        logger.info(f"Notificacao marcada como lida: {notification_id}")
        return notification

    async def mark_all_as_read(
        self,
        tenant_id: str,
        user_id: str,
        notification_ids: list[str] | None = None,
    ) -> int:
        """
        Marca todas notificacoes como lidas.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuario
            notification_ids: IDs especificos (opcional)

        Returns:
            Quantidade de notificacoes atualizadas
        """
        query = (
            update(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
                Notification.is_active.is_(True),
            )
            .values(read_at=datetime.utcnow())
        )

        if notification_ids:
            query = query.where(Notification.id.in_(notification_ids))

        result = await self.db.execute(query)
        await self.db.commit()

        count = result.rowcount
        logger.info(f"Notificacoes marcadas como lidas: {count}")
        return count

    async def get_unread_count(
        self,
        tenant_id: str,
        user_id: str,
    ) -> dict:
        """
        Obtem contagem de notificacoes nao lidas.

        Args:
            tenant_id: ID do tenant
            user_id: ID do usuario

        Returns:
            Dicionario com total e por tipo
        """
        result = await self.db.execute(
            select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
                Notification.is_active.is_(True),
            )
        )
        unread = list(result.scalars().all())

        by_type: dict = {}
        for notification in unread:
            by_type[notification.type] = by_type.get(notification.type, 0) + 1

        return {
            "total": len(unread),
            "by_type": by_type,
        }

    async def delete(
        self,
        notification_id: str,
        user_id: str,
    ) -> bool:
        """
        Soft delete de notificacao.

        Args:
            notification_id: ID da notificacao
            user_id: ID do usuario

        Returns:
            True se deletada
        """
        notification = await self.get_by_id(notification_id, user_id=user_id)
        if not notification:
            return False

        notification.is_active = False
        await self.db.commit()

        logger.info(f"Notificacao deletada (soft): {notification_id}")
        return True

    async def cleanup_old(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> int:
        """
        Remove notificacoes antigas.

        Args:
            tenant_id: ID do tenant
            days: Dias de retencao

        Returns:
            Quantidade removida
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.created_at < cutoff,
                Notification.is_active.is_(True),
            )
            .values(is_active=False)
        )
        await self.db.commit()

        count = result.rowcount
        logger.info(f"Notificacoes antigas removidas: {count}")
        return count


class AlertRepository:
    """
    Repository para operacoes CRUD de Alertas.

    Fornece metodos para criar, listar e gerenciar alertas em tempo real.

    Attributes:
        db: Sessao assincrona do banco de dados
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Inicializa o repository.

        Args:
            db: Sessao assincrona do banco de dados
        """
        self.db = db

    async def create(
        self,
        data: AlertCreate,
        tenant_id: str,
    ) -> Alert:
        """
        Cria um novo alerta.

        Args:
            data: Dados do alerta
            tenant_id: ID do tenant

        Returns:
            Alerta criado
        """
        from datetime import timedelta

        alert = Alert(
            id=str(uuid4()),
            tenant_id=tenant_id,
            alert_type=data.alert_type.value,
            severity=data.severity.value,
            title=data.title,
            message=data.message,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            target_users=data.target_users or [],
            target_roles=data.target_roles or [],
            expires_at=datetime.utcnow() + timedelta(minutes=data.expires_in_minutes),
        )

        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)

        logger.info(f"Alerta criado: {alert.id} [{alert.severity}]")
        return alert

    async def get_by_id(
        self,
        alert_id: str,
        tenant_id: str | None = None,
    ) -> Alert | None:
        """
        Busca alerta por ID.

        Args:
            alert_id: ID do alerta
            tenant_id: ID do tenant (opcional)

        Returns:
            Alerta ou None
        """
        query = select(Alert).where(
            Alert.id == alert_id,
            Alert.is_active.is_(True),
        )

        if tenant_id:
            query = query.where(Alert.tenant_id == tenant_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_active(
        self,
        tenant_id: str,
        filters: AlertFilter | None = None,
        user_id: str | None = None,
        user_roles: list[str] | None = None,
    ) -> list[Alert]:
        """
        Lista alertas ativos.

        Args:
            tenant_id: ID do tenant
            filters: Filtros de busca
            user_id: ID do usuario (para filtrar por destinatario)
            user_roles: Roles do usuario (para filtrar por destinatario)

        Returns:
            Lista de alertas ativos
        """
        query = select(Alert).where(
            Alert.tenant_id == tenant_id,
            Alert.is_active.is_(True),
            or_(
                Alert.expires_at.is_(None),
                Alert.expires_at > datetime.utcnow(),
            ),
        )

        if filters:
            query = self._apply_alert_filters(query, filters)

        # Filtro por destinatario
        if user_id or user_roles:
            target_conditions = [
                and_(
                    Alert.target_users == [],
                    Alert.target_roles == [],
                ),
            ]
            if user_id:
                target_conditions.append(Alert.target_users.contains([user_id]))
            if user_roles:
                for role in user_roles:
                    target_conditions.append(Alert.target_roles.contains([role]))

            query = query.where(or_(*target_conditions))

        query = query.order_by(
            Alert.severity.desc(),
            Alert.created_at.desc(),
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _apply_alert_filters(self, query, filters: AlertFilter):
        """Aplica filtros a query de alertas."""
        if filters.alert_type:
            query = query.where(Alert.alert_type == filters.alert_type.value)

        if filters.severity:
            query = query.where(Alert.severity == filters.severity.value)

        if filters.is_active is not None:
            query = query.where(Alert.is_active == filters.is_active)

        if filters.reference_type:
            query = query.where(Alert.reference_type == filters.reference_type)

        if filters.created_after:
            query = query.where(Alert.created_at >= filters.created_after)

        return query

    async def acknowledge(
        self,
        alert_id: str,
        user_id: str,
        tenant_id: str,
    ) -> Alert | None:
        """
        Confirma alerta.

        Args:
            alert_id: ID do alerta
            user_id: ID do usuario
            tenant_id: ID do tenant

        Returns:
            Alerta atualizado ou None
        """
        alert = await self.get_by_id(alert_id, tenant_id)
        if not alert:
            return None

        if alert.acknowledge(user_id):
            await self.db.commit()
            await self.db.refresh(alert)
            logger.info(f"Alerta confirmado: {alert_id} por {user_id}")

        return alert

    async def deactivate(
        self,
        alert_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Desativa um alerta.

        Args:
            alert_id: ID do alerta
            tenant_id: ID do tenant

        Returns:
            True se desativado
        """
        alert = await self.get_by_id(alert_id, tenant_id)
        if not alert:
            return False

        alert.is_active = False
        await self.db.commit()

        logger.info(f"Alerta desativado: {alert_id}")
        return True

    async def process_expired(self) -> int:
        """
        Processa alertas expirados.

        Returns:
            Quantidade de alertas desativados
        """
        result = await self.db.execute(
            update(Alert)
            .where(
                Alert.is_active.is_(True),
                Alert.expires_at <= datetime.utcnow(),
            )
            .values(is_active=False)
        )
        await self.db.commit()

        count = result.rowcount
        if count > 0:
            logger.info(f"Alertas expirados desativados: {count}")

        return count
