"""WebSocket API endpoint."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config.assets import ACTIVE_SYMBOLS
from app.core.cache import get_dashboard_state
from app.websocket.manager import manager

ws_router = APIRouter()


@ws_router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        for sym in ACTIVE_SYMBOLS:
            cached = await get_dashboard_state(sym)
            if cached:
                await websocket.send_json({"type": "dashboard_update", "data": cached})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
