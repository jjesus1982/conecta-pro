"""Push Notification Service - Serviço de Notificações Push.

Sprint: Módulo Operacional - Sistema de Notificações Push
"""

import logging
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from modules.notifications.models import (
    LogEventType,
    NotificationLog,
    NotificationPreference,
    NotificationQueue,
    QueuePriority,
    QueueStatus,
)

logger = logging.getLogger(__name__)


class PushNotificationService:
    """Serviço para gerenciamento de notificações push."""

    def __init__(self, db: Session, tenant_id: UUID):
        """Inicializa o serviço.

        Args:
            db: Sessão do banco de dados (sync ou async — detectado automaticamente)
            tenant_id: ID do tenant
        """
        # Se receber AsyncSession, trocar por sessão síncrona transparentemente
        try:
            from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

            if isinstance(db, _AsyncSession):
                from core.database.session import SyncSessionLocal

                self.db = SyncSessionLocal()
                self._owns_session = True
            else:
                self.db = db
                self._owns_session = False
        except Exception:
            self.db = db
            self._owns_session = False
        self.tenant_id = tenant_id

    def __del__(self):
        """Fecha sessão própria ao ser destruído."""
        if getattr(self, "_owns_session", False):
            try:
                self.db.close()
            except Exception:
                pass

    def subscribe_device(
        self,
        user_id: UUID,
        device_token: str,
        platform: str,
        device_info: dict | None = None,
    ) -> dict:
        """Registra dispositivo para receber notificações push.

        Args:
            user_id: ID do usuário
            device_token: Token do dispositivo (FCM, APNS, etc)
            platform: Plataforma (web, ios, android)
            device_info: Informações do dispositivo

        Returns:
            Dicionário com resultado da operação
        """
        try:
            preference = (
                self.db.query(NotificationPreference)
                .filter(
                    NotificationPreference.tenant_id == self.tenant_id,
                    NotificationPreference.user_id == user_id,
                )
                .first()
            )

            if not preference:
                preference = NotificationPreference(
                    tenant_id=self.tenant_id,
                    user_id=user_id,
                    push_enabled=True,
                )
                self.db.add(preference)

            # Atualiza tokens de dispositivo
            device_tokens = preference.user_device_tokens or []

            # Remove token duplicado se existir
            device_tokens = [t for t in device_tokens if t.get("token") != device_token]

            # Adiciona novo token
            device_tokens.append(
                {
                    "token": device_token,
                    "platform": platform,
                    "device_info": device_info or {},
                    "subscribed_at": datetime.utcnow().isoformat(),
                }
            )

            preference.user_device_tokens = device_tokens
            preference.push_enabled = True

            self.db.commit()
            self.db.refresh(preference)

            logger.info(f"Dispositivo registrado para push: user={user_id}, platform={platform}")

            return {
                "success": True,
                "message": "Dispositivo registrado com sucesso",
                "device_count": len(device_tokens),
            }

        except Exception as e:
            logger.error(f"Erro ao registrar dispositivo: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": f"Erro ao registrar dispositivo: {str(e)}",
            }

    def unsubscribe_device(
        self,
        user_id: UUID,
        device_token: str,
    ) -> dict:
        """Remove registro de dispositivo.

        Args:
            user_id: ID do usuário
            device_token: Token do dispositivo

        Returns:
            Dicionário com resultado da operação
        """
        try:
            preference = (
                self.db.query(NotificationPreference)
                .filter(
                    NotificationPreference.tenant_id == self.tenant_id,
                    NotificationPreference.user_id == user_id,
                )
                .first()
            )

            if not preference:
                return {
                    "success": False,
                    "message": "Preferência não encontrada",
                }

            device_tokens = preference.user_device_tokens or []
            device_tokens = [t for t in device_tokens if t.get("token") != device_token]

            preference.user_device_tokens = device_tokens

            self.db.commit()

            logger.info(f"Dispositivo removido: user={user_id}")

            return {
                "success": True,
                "message": "Dispositivo removido com sucesso",
            }

        except Exception as e:
            logger.error(f"Erro ao remover dispositivo: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": f"Erro ao remover dispositivo: {str(e)}",
            }

    def send_push_notification(
        self,
        user_id: UUID,
        title: str,
        body: str,
        data: dict | None = None,
        priority: QueuePriority = QueuePriority.NORMAL,
        action_url: str | None = None,
    ) -> dict:
        """Envia notificação push para usuário.

        Args:
            user_id: ID do usuário
            title: Título da notificação
            body: Corpo da mensagem
            data: Dados adicionais
            priority: Prioridade da notificação
            action_url: URL de ação ao clicar

        Returns:
            Dicionário com resultado da operação
        """
        try:
            # Verifica preferências do usuário
            preference = (
                self.db.query(NotificationPreference)
                .filter(
                    NotificationPreference.tenant_id == self.tenant_id,
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.push_enabled,
                    NotificationPreference.active,
                )
                .first()
            )

            if not preference:
                logger.warning(f"Push desabilitado ou preferência não encontrada: user={user_id}")
                return {
                    "success": False,
                    "message": "Notificações push desabilitadas para este usuário",
                }

            device_tokens = preference.user_device_tokens or []
            if not device_tokens:
                logger.warning(f"Nenhum dispositivo registrado: user={user_id}")
                return {
                    "success": False,
                    "message": "Nenhum dispositivo registrado",
                }

            # Cria item na fila de notificações
            queue_item = NotificationQueue(
                tenant_id=self.tenant_id,
                notification_id=f"push-{uuid4().hex[:20]}",
                user_id=user_id,
                channel_type="push",
                priority=priority,
                status=QueueStatus.PENDING,
                recipient_address="push",  # Push não usa endereço real
                subject=title,
                body=body,
                content_data={
                    "action_url": action_url,
                    "custom_data": data or {},
                    "device_tokens": device_tokens,
                },
            )

            self.db.add(queue_item)
            self.db.commit()
            self.db.refresh(queue_item)

            # Log
            log_entry = NotificationLog(
                tenant_id=self.tenant_id,
                queue_id=queue_item.id,
                notification_id=str(queue_item.id),
                channel_type="push",
                user_id=user_id,
                event_type=LogEventType.QUEUED,
                message=f"Notificação push enfileirada: {title}",
                details={
                    "title": title,
                    "body": body,
                    "device_count": len(device_tokens),
                },
            )
            self.db.add(log_entry)
            self.db.commit()

            logger.info(f"Push notification enfileirada: user={user_id}, queue_id={queue_item.id}")

            return {
                "success": True,
                "message": "Notificação enfileirada com sucesso",
                "queue_id": str(queue_item.id),
                "device_count": len(device_tokens),
            }

        except Exception as e:
            logger.error(f"Erro ao enviar push notification: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": f"Erro ao enviar notificação: {str(e)}",
            }

    def get_user_notifications(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Lista notificações do usuário.

        Args:
            user_id: ID do usuário
            unread_only: Filtrar apenas não lidas
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de notificações
        """
        try:
            query = self.db.query(NotificationQueue).filter(
                NotificationQueue.tenant_id == self.tenant_id,
                NotificationQueue.user_id == user_id,
                NotificationQueue.channel_type == "push",
            )

            if unread_only:
                query = query.filter(NotificationQueue.opened.is_(False))

            notifications = query.order_by(NotificationQueue.created_at.desc()).offset(offset).limit(limit).all()

            return [
                {
                    "id": str(n.id),
                    "title": n.subject,
                    "body": n.body,
                    "data": n.content_data,
                    "read": n.opened or False,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "opened_at": n.opened_at.isoformat() if n.opened_at else None,
                    "action_url": n.content_data.get("action_url") if n.content_data else None,
                }
                for n in notifications
            ]

        except Exception as e:
            logger.error(f"Erro ao listar notificações: {e}")
            return []

    def mark_as_read(
        self,
        notification_id: UUID,
        user_id: UUID,
    ) -> dict:
        """Marca notificação como lida.

        Args:
            notification_id: ID da notificação
            user_id: ID do usuário

        Returns:
            Dicionário com resultado da operação
        """
        try:
            notification = (
                self.db.query(NotificationQueue)
                .filter(
                    NotificationQueue.tenant_id == self.tenant_id,
                    NotificationQueue.id == notification_id,
                    NotificationQueue.user_id == user_id,
                )
                .first()
            )

            if not notification:
                return {
                    "success": False,
                    "message": "Notificação não encontrada",
                }

            notification.opened = True
            notification.opened_at = notification.opened_at or datetime.utcnow()
            notification.opened_count = (notification.opened_count or 0) + 1

            self.db.commit()

            logger.info(f"Notificação marcada como lida: {notification_id}")

            return {
                "success": True,
                "message": "Notificação marcada como lida",
            }

        except Exception as e:
            logger.error(f"Erro ao marcar notificação como lida: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": f"Erro ao marcar notificação: {str(e)}",
            }

    def mark_all_as_read(self, user_id: UUID) -> dict:
        """Marca todas as notificações como lidas.

        Args:
            user_id: ID do usuário

        Returns:
            Dicionário com resultado da operação
        """
        try:
            updated = (
                self.db.query(NotificationQueue)
                .filter(
                    NotificationQueue.tenant_id == self.tenant_id,
                    NotificationQueue.user_id == user_id,
                    NotificationQueue.channel_type == "push",
                    NotificationQueue.opened.is_(False),
                )
                .update(
                    {
                        "opened": True,
                        "opened_at": datetime.utcnow(),
                    }
                )
            )

            self.db.commit()

            logger.info(f"Notificações marcadas como lidas: {updated} notificações")

            return {
                "success": True,
                "message": f"{updated} notificações marcadas como lidas",
                "count": updated,
            }

        except Exception as e:
            logger.error(f"Erro ao marcar todas como lidas: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": f"Erro ao marcar notificações: {str(e)}",
            }

    def get_unread_count(self, user_id: UUID) -> int:
        """Retorna quantidade de notificações não lidas.

        Args:
            user_id: ID do usuário

        Returns:
            Quantidade de notificações não lidas
        """
        try:
            count = (
                self.db.query(NotificationQueue)
                .filter(
                    NotificationQueue.tenant_id == self.tenant_id,
                    NotificationQueue.user_id == user_id,
                    NotificationQueue.channel_type == "push",
                    NotificationQueue.opened.is_(False),
                )
                .count()
            )
            return count

        except Exception as e:
            logger.error(f"Erro ao contar notificações não lidas: {e}")
            return 0
