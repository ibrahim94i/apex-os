"""WebSocket connection manager and broadcaster."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.logging_config import logger


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("ws_client_connected", total=len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("ws_client_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.active_connections:
            return

        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        async with self._lock:
            connections = list(self.active_connections)

        for connection in connections:
            try:
                await connection.send_text(payload)
            except (WebSocketDisconnect, RuntimeError):
                dead.append(connection)
            except Exception as exc:
                logger.error("ws_broadcast_error", error=str(exc))
                dead.append(connection)

        if dead:
            async with self._lock:
                for conn in dead:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)


class Broadcaster:
    def __init__(self, manager: ConnectionManager) -> None:
        self.manager = manager

    async def broadcast_dashboard_update(self, state: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "dashboard_update", "data": state})

    async def broadcast_signal(self, signal: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "new_signal", "data": signal})

    async def broadcast_regime(self, regime: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "regime_update", "data": regime})

    async def broadcast_kill_switch(self, status: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "kill_switch_update", "data": status})

    async def broadcast_price(self, price: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "price_update", "data": price})

    async def broadcast_display_price(self, price: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "display_price_update", "data": price})

    async def broadcast_agent_consensus(self, consensus: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "agent_consensus_update", "data": consensus})

    async def broadcast_market_status(self, statuses: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "market_status_update", "data": statuses})

    async def broadcast_hourly_report(self, report: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "hourly_report_update", "data": report})

    async def broadcast_memory_patterns(self, payload: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "memory_patterns_update", "data": payload})

    async def broadcast_feed_status(self, statuses: dict[str, Any]) -> None:
        await self.manager.broadcast({"type": "feed_status", "data": statuses})


manager = ConnectionManager()
broadcaster = Broadcaster(manager)
