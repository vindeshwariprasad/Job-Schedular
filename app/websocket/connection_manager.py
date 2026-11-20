import asyncio
from collections import defaultdict

from fastapi import WebSocket
from logging_config import get_logger

logger = get_logger("websocket")


class ConnectionManager:
    """Manages active WebSocket connections grouped by user ID."""

    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)
        logger.info("WebSocket connected", extra={"user_id": user_id})

    async def disconnect(self, user_id: int, websocket: WebSocket):
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("WebSocket disconnected", extra={"user_id": user_id})

    async def broadcast_to_user(self, user_id: int, message: dict):
        async with self._lock:
            sockets = list(self._connections.get(user_id, []))

        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(user_id, ws)

    @property
    def active_count(self) -> int:
        return sum(len(s) for s in self._connections.values())


manager = ConnectionManager()
