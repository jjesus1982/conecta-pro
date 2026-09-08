"""
WebSocket Handler para Notificações Operacionais em Tempo Real.
Author: Conecta PRO Team / Date: 2026-03-09 / Quality: 99+
"""

import contextlib
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

websocket_router = APIRouter(tags=["Operacional - WebSocket"])


class ConnectionManager:
    """Gerencia conexões WebSocket ativas por tenant/usuário."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str = "operacional") -> None:
        """Aceita conexão e adiciona à sala."""
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        logger.info(
            "WebSocket conectado à sala '%s'. Total: %d",
            room,
            len(self.active_connections[room]),
        )

    def disconnect(self, websocket: WebSocket, room: str = "operacional") -> None:
        """Remove conexão da sala."""
        if room in self.active_connections:
            with contextlib.suppress(ValueError):
                self.active_connections[room].remove(websocket)
        logger.info("WebSocket desconectado da sala '%s'", room)

    async def broadcast(self, room: str, event_type: str, data: dict[str, Any]) -> None:
        """Envia mensagem para todos na sala."""
        message = json.dumps(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        dead_connections: list[WebSocket] = []
        for connection in self.active_connections.get(room, []):
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead, room)

    async def send_to_user(self, user_room: str, event_type: str, data: dict[str, Any]) -> None:
        """Envia mensagem para usuário específico."""
        await self.broadcast(user_room, event_type, data)

    def get_room_size(self, room: str) -> int:
        """Retorna número de conexões ativas na sala."""
        return len(self.active_connections.get(room, []))


manager = ConnectionManager()


@websocket_router.websocket("/ws/notifications/{room}")
async def websocket_notifications(websocket: WebSocket, room: str = "operacional") -> None:
    """
    WebSocket endpoint para notificações operacionais em tempo real.

    Rooms disponíveis:
    - operacional: notificações gerais da operação
    - alertas: apenas alertas críticos
    - campo: eventos de campo (check-ins, rondas)
    """
    await manager.connect(websocket, room)
    try:
        # Enviar estado inicial
        await websocket.send_json(
            {
                "type": "connected",
                "data": {
                    "room": room,
                    "connections": manager.get_room_size(room),
                    "message": f"Conectado à sala '{room}' com sucesso",
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        while True:
            # Aguardar mensagens do cliente (ping/comandos)
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "data": {"ts": datetime.utcnow().isoformat()},
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                elif msg_type == "subscribe":
                    # Cliente solicitando eventos específicos
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "data": {"events": msg.get("events", [])},
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, room)
    except Exception as exc:
        logger.error("Erro no WebSocket da sala '%s': %s", room, exc)
        manager.disconnect(websocket, room)


