"""Comprehensive tests for WebSocket connection manager."""

from unittest.mock import AsyncMock

import pytest
from websocket.connection_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestConnectionManager:

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self, manager, mock_websocket):
        await manager.connect(1, mock_websocket)
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_adds_to_connections(self, manager, mock_websocket):
        await manager.connect(1, mock_websocket)
        assert manager.active_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, manager, mock_websocket):
        await manager.connect(1, mock_websocket)
        await manager.disconnect(1, mock_websocket)
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_last_removes_user_key(self, manager, mock_websocket):
        await manager.connect(1, mock_websocket)
        await manager.disconnect(1, mock_websocket)
        assert 1 not in manager._connections

    @pytest.mark.asyncio
    async def test_multiple_connections_same_user(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(1, ws1)
        await manager.connect(1, ws2)
        assert manager.active_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_one_keeps_other(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(1, ws1)
        await manager.connect(1, ws2)
        await manager.disconnect(1, ws1)
        assert manager.active_count == 1

    @pytest.mark.asyncio
    async def test_multiple_users(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(1, ws1)
        await manager.connect(2, ws2)
        assert manager.active_count == 2

    @pytest.mark.asyncio
    async def test_broadcast_to_user(self, manager, mock_websocket):
        await manager.connect(1, mock_websocket)
        message = {"type": "update", "data": "test"}
        await manager.broadcast_to_user(1, message)
        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_only_to_target_user(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(1, ws1)
        await manager.connect(2, ws2)
        await manager.broadcast_to_user(1, {"msg": "hello"})
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_all_user_sockets(self, manager):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(1, ws1)
        await manager.connect(1, ws2)
        await manager.broadcast_to_user(1, {"msg": "hello"})
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_handles_failed_send(self, manager):
        ws = AsyncMock()
        ws.send_json.side_effect = Exception("Connection closed")
        await manager.connect(1, ws)
        await manager.broadcast_to_user(1, {"msg": "hello"})
        # Should disconnect the failed socket
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_user(self, manager):
        # Should not raise
        await manager.broadcast_to_user(999, {"msg": "hello"})

    @pytest.mark.asyncio
    async def test_active_count_empty(self, manager):
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_websocket(self, manager, mock_websocket):
        # Disconnecting a socket that was never connected should not raise
        await manager.disconnect(1, mock_websocket)
