"""
Controller WebSocket para Comunicacao em Tempo Real.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.websockets import WebSocketState

from modules.operacional.communication.models.alert import Alert
from modules.operacional.communication.schemas.communication_schemas import (
    WebSocketConnectionInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operacional - WebSocket"])


class ConnectionManager:
    """
    Gerenciador de conexoes WebSocket.

    Mantem registro de conexoes ativas e fornece metodos para
    broadcast de mensagens para usuarios/roles especificos.

    Attributes:
        active_connections: Conexoes ativas por ID
        user_connections: Mapeamento de usuario para conexoes
        role_connections: Mapeamento de role para conexoes
        tenant_connections: Mapeamento de tenant para conexoes

    Example:
        >>> manager = ConnectionManager()
        >>> await manager.connect(websocket, user_id, tenant_id, roles)
        >>> await manager.broadcast_to_user(user_id, message)
    """

    def __init__(self) -> None:
        """Inicializa o gerenciador."""
        # connection_id -> (websocket, info)
        self.active_connections: dict[str, tuple[WebSocket, WebSocketConnectionInfo]] = {}

        # user_id -> set of connection_ids
        self.user_connections: dict[str, set[str]] = {}

        # role -> set of connection_ids
        self.role_connections: dict[str, set[str]] = {}

        # tenant_id -> set of connection_ids
        self.tenant_connections: dict[str, set[str]] = {}

        # Lock para operacoes thread-safe
        self._lock = asyncio.Lock()

        # Intervalo de heartbeat (segundos)
        self.heartbeat_interval = 30

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        tenant_id: str,
        roles: list[str],
    ) -> str:
        """
        Registra uma nova conexao WebSocket.

        Args:
            websocket: Conexao WebSocket
            user_id: ID do usuario
            tenant_id: ID do tenant
            roles: Roles do usuario

        Returns:
            ID da conexao
        """
        await websocket.accept()
        connection_id = str(uuid4())

        info = WebSocketConnectionInfo(
            connection_id=connection_id,
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles,
        )

        async with self._lock:
            # Registra conexao
            self.active_connections[connection_id] = (websocket, info)

            # Indexa por usuario
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)

            # Indexa por roles
            for role in roles:
                if role not in self.role_connections:
                    self.role_connections[role] = set()
                self.role_connections[role].add(connection_id)

            # Indexa por tenant
            if tenant_id not in self.tenant_connections:
                self.tenant_connections[tenant_id] = set()
            self.tenant_connections[tenant_id].add(connection_id)

        logger.info(f"WebSocket conectado: {connection_id} (user={user_id}, tenant={tenant_id})")

        # Envia mensagem de boas-vindas
        await self._send_to_connection(
            connection_id,
            {
                "type": "connected",
                "data": {
                    "connection_id": connection_id,
                    "message": "Conexao estabelecida",
                },
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """
        Remove uma conexao WebSocket.

        Args:
            connection_id: ID da conexao
        """
        async with self._lock:
            if connection_id not in self.active_connections:
                return

            _, info = self.active_connections[connection_id]

            # Remove dos indices
            if info.user_id in self.user_connections:
                self.user_connections[info.user_id].discard(connection_id)
                if not self.user_connections[info.user_id]:
                    del self.user_connections[info.user_id]

            for role in info.roles:
                if role in self.role_connections:
                    self.role_connections[role].discard(connection_id)
                    if not self.role_connections[role]:
                        del self.role_connections[role]

            if info.tenant_id in self.tenant_connections:
                self.tenant_connections[info.tenant_id].discard(connection_id)
                if not self.tenant_connections[info.tenant_id]:
                    del self.tenant_connections[info.tenant_id]

            # Remove conexao
            del self.active_connections[connection_id]

        # logging padrão não aceita kwargs (era loguru): estourava TypeError em TODA desconexão —
        # 298 tracebacks em 12 min (medido 07/09/2026 na varredura do clássico).
        logger.info("WebSocket desconectado: %s", connection_id)

    async def _send_to_connection(
        self,
        connection_id: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Envia mensagem para uma conexao especifica.

        Args:
            connection_id: ID da conexao
            message: Mensagem a enviar

        Returns:
            True se enviada com sucesso
        """
        if connection_id not in self.active_connections:
            return False

        websocket, _ = self.active_connections[connection_id]

        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(message)
                return True
        except Exception as e:
            logger.error(f"Erro ao enviar para {connection_id}: {e}")
            # Marca para remocao
            await self.disconnect(connection_id)

        return False

    async def broadcast_to_user(
        self,
        user_id: str,
        message: dict[str, Any],
    ) -> int:
        """
        Envia mensagem para todas conexoes de um usuario.

        Args:
            user_id: ID do usuario
            message: Mensagem a enviar

        Returns:
            Quantidade de conexoes que receberam
        """
        count = 0
        connection_ids = self.user_connections.get(user_id, set()).copy()

        for connection_id in connection_ids:
            if await self._send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_to_role(
        self,
        role: str,
        message: dict[str, Any],
        tenant_id: str | None = None,
    ) -> int:
        """
        Envia mensagem para todas conexoes de uma role.

        Args:
            role: Nome da role
            message: Mensagem a enviar
            tenant_id: Filtrar por tenant (opcional)

        Returns:
            Quantidade de conexoes que receberam
        """
        count = 0
        connection_ids = self.role_connections.get(role, set()).copy()

        for connection_id in connection_ids:
            if connection_id not in self.active_connections:
                continue

            _, info = self.active_connections[connection_id]

            # Filtra por tenant se especificado
            if tenant_id and info.tenant_id != tenant_id:
                continue

            if await self._send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        message: dict[str, Any],
    ) -> int:
        """
        Envia mensagem para todas conexoes de um tenant.

        Args:
            tenant_id: ID do tenant
            message: Mensagem a enviar

        Returns:
            Quantidade de conexoes que receberam
        """
        count = 0
        connection_ids = self.tenant_connections.get(tenant_id, set()).copy()

        for connection_id in connection_ids:
            if await self._send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_all(
        self,
        message: dict[str, Any],
    ) -> int:
        """
        Envia mensagem para todas conexoes ativas.

        Args:
            message: Mensagem a enviar

        Returns:
            Quantidade de conexoes que receberam
        """
        count = 0
        connection_ids = list(self.active_connections.keys())

        for connection_id in connection_ids:
            if await self._send_to_connection(connection_id, message):
                count += 1

        return count

    async def broadcast_alert(
        self,
        alert: Alert,
        tenant_id: str,
    ) -> int:
        """
        Faz broadcast de um alerta para destinatarios.

        Args:
            alert: Alerta a ser transmitido
            tenant_id: ID do tenant

        Returns:
            Quantidade de conexoes que receberam
        """
        message = alert.to_websocket_message()
        message["timestamp"] = datetime.utcnow().isoformat()

        count = 0

        # Envia para usuarios especificos
        for user_id in alert.target_users or []:
            count += await self.broadcast_to_user(user_id, message)

        # Envia para roles
        for role in alert.target_roles or []:
            count += await self.broadcast_to_role(role, message, tenant_id)

        # Se nao tiver destinatarios especificos, envia para todo o tenant
        if not alert.target_users and not alert.target_roles:
            count = await self.broadcast_to_tenant(tenant_id, message)

        logger.info(f"Alerta {alert.id} transmitido para {count} conexoes")

        return count

    def get_connection_count(self) -> int:
        """Retorna quantidade de conexoes ativas."""
        return len(self.active_connections)

    def get_user_connection_count(self, user_id: str) -> int:
        """Retorna quantidade de conexoes de um usuario."""
        return len(self.user_connections.get(user_id, set()))

    def is_user_connected(self, user_id: str) -> bool:
        """Verifica se um usuario esta conectado."""
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0


# Instancia global do gerenciador
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Retorna o gerenciador de conexoes."""
    return manager


async def _authenticate_websocket(
    websocket: WebSocket,
    token: str | None,
) -> dict[str, Any]:
    """
    Autentica conexao WebSocket.

    Args:
        websocket: Conexao WebSocket
        token: Token JWT

    Returns:
        Dados do usuario

    Raises:
        HTTPException: Se autenticacao falhar
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacao requerido",
        )

    try:
        from core.auth.jwt import verify_access_token

        payload = verify_access_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalido",
            )

        return {
            "user_id": user_id,
            "tenant_id": payload.get("tenant_id", user_id),
            "roles": payload.get("roles", []),
        }

    except Exception as e:
        logger.error(f"Erro na autenticacao WebSocket: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falha na autenticacao",
        )


@router.websocket("/ws/operacional/alertas")
async def websocket_alerts(
    websocket: WebSocket,
    token: str = Query(..., description="Token JWT de autenticacao"),
) -> None:
    """
    WebSocket para alertas em tempo real.

    Conecta e recebe alertas criticos conforme ocorrem.

    Args:
        websocket: Conexao WebSocket
        token: Token JWT de autenticacao
    """
    connection_id = None

    try:
        # Autentica
        auth_data = await _authenticate_websocket(websocket, token)

        # Conecta
        connection_id = await manager.connect(
            websocket=websocket,
            user_id=auth_data["user_id"],
            tenant_id=auth_data["tenant_id"],
            roles=auth_data["roles"],
        )

        # Loop de mensagens
        while True:
            try:
                # Recebe mensagem (ping/pong ou comandos)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=manager.heartbeat_interval,
                )

                # Processa comandos
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await websocket.send_json(
                            {
                                "type": "pong",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )
                    elif message.get("type") == "acknowledge":
                        # Processa confirmacao de alerta
                        alert_id = message.get("alert_id")
                        if alert_id:
                            logger.debug(f"Alerta {alert_id} confirmado via WebSocket")

                except json.JSONDecodeError:
                    pass

            except TimeoutError:
                # Envia ping para manter conexao
                try:
                    await websocket.send_json(
                        {
                            "type": "ping",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug(f"WebSocket desconectado normalmente: {connection_id}")

    except HTTPException as e:
        logger.warning(f"Erro de autenticacao WebSocket: {e.detail}")
        with contextlib.suppress(Exception):
            await websocket.close(code=4001, reason=e.detail)

    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")

    finally:
        if connection_id:
            await manager.disconnect(connection_id)


@router.websocket("/ws/operacional/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(..., description="Token JWT de autenticacao"),
) -> None:
    """
    WebSocket para notificacoes em tempo real.

    Conecta e recebe notificacoes conforme sao enviadas.

    Args:
        websocket: Conexao WebSocket
        token: Token JWT de autenticacao
    """
    connection_id = None

    try:
        # Autentica
        auth_data = await _authenticate_websocket(websocket, token)

        # Conecta
        connection_id = await manager.connect(
            websocket=websocket,
            user_id=auth_data["user_id"],
            tenant_id=auth_data["tenant_id"],
            roles=auth_data["roles"],
        )

        # Loop de mensagens
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=manager.heartbeat_interval,
                )

                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await websocket.send_json(
                            {
                                "type": "pong",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )
                    elif message.get("type") == "mark_read":
                        # Marca notificacao como lida
                        notification_id = message.get("notification_id")
                        if notification_id:
                            logger.debug(f"Notificacao {notification_id} lida via WebSocket")

                except json.JSONDecodeError:
                    pass

            except TimeoutError:
                try:
                    await websocket.send_json(
                        {
                            "type": "ping",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug(f"WebSocket desconectado normalmente: {connection_id}")

    except HTTPException as e:
        logger.warning(f"Erro de autenticacao WebSocket: {e.detail}")
        with contextlib.suppress(Exception):
            await websocket.close(code=4001, reason=e.detail)

    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")

    finally:
        if connection_id:
            await manager.disconnect(connection_id)


