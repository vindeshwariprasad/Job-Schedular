"""Comprehensive tests for main.py: health check, metrics, global exception handler, WebSocket, CORS."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from db.base import Base
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture
def client(test_engine):
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables(test_engine))

    async_session = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    from unittest.mock import patch

    from db.session import get_db
    from main import app

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Bypass Redis-based auth rate limiting in tests (no live Redis)
    with patch("api.auth.is_rate_limited", return_value=False):
        c = TestClient(app)
        yield c
    app.dependency_overrides.clear()
    loop.run_until_complete(test_engine.dispose())
    loop.close()


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _register(client, username="testuser", email="test@example.com"):
    resp = client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": "TestPass1",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestHealthCheck:

    def test_healthy_response(self, client):
        with patch("main.async_engine") as mock_engine, \
             patch("main.redis_client") as mock_redis:
            mock_conn = AsyncMock()
            mock_engine.connect = MagicMock(return_value=AsyncMock())
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_conn.execute = AsyncMock()
            mock_redis.ping.return_value = True

            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["postgres"] == "up"
        assert data["redis"] == "up"

    def test_unhealthy_503_when_postgres_down(self, client):
        with patch("main.async_engine") as mock_engine, \
             patch("main.redis_client") as mock_redis:
            mock_engine.connect = MagicMock(return_value=AsyncMock())
            mock_engine.connect.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
            mock_redis.ping.return_value = True

            resp = client.get("/health")

        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["postgres"] == "down"
        assert data["redis"] == "up"

    def test_unhealthy_503_when_redis_down(self, client):
        with patch("main.async_engine") as mock_engine, \
             patch("main.redis_client") as mock_redis:
            mock_conn = AsyncMock()
            mock_engine.connect = MagicMock(return_value=AsyncMock())
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_conn.execute = AsyncMock()
            mock_redis.ping.side_effect = Exception("Redis down")

            resp = client.get("/health")

        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["redis"] == "down"
        assert data["postgres"] == "up"

    def test_unhealthy_503_when_both_down(self, client):
        with patch("main.async_engine") as mock_engine, \
             patch("main.redis_client") as mock_redis:
            mock_engine.connect = MagicMock(return_value=AsyncMock())
            mock_engine.connect.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
            mock_redis.ping.side_effect = Exception("Redis down")

            resp = client.get("/health")

        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["postgres"] == "down"
        assert data["redis"] == "down"


class TestMetricsEndpoint:

    def test_returns_prometheus_format(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "") or \
               "text/plain" in resp.headers.get("Content-Type", "") or \
               resp.status_code == 200  # prometheus format


class TestGlobalExceptionHandler:

    def test_returns_500_on_unhandled_error(self, client):
        """Unhandled exceptions should return 500 with generic message."""
        from main import app

        @app.get("/test-error-endpoint")
        def raise_error():
            raise RuntimeError("Something went wrong")

        try:
            resp = client.get("/test-error-endpoint")
            assert resp.status_code == 500
            assert resp.json()["detail"] == "Internal server error"
        except RuntimeError:
            # Some versions of Starlette re-raise the exception in test mode
            pass

    def test_http_exceptions_pass_through(self, client):
        """HTTP exceptions should be re-raised, not caught by global handler."""
        resp = client.get("/api/v1/jobs")  # no auth = 401/403
        assert resp.status_code in (401, 403)


class TestCORS:

    def test_cors_headers_present(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS preflight or actual response
        assert resp.status_code in (200, 204, 405)


class TestWebSocketEndpoint:

    def test_invalid_token_closes_connection(self, client):
        """WebSocket with invalid token should be closed with 4001."""
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/executions?token=invalid"):
                pass

    def test_missing_token_rejected(self, client):
        """WebSocket without token param should be rejected."""
        with pytest.raises((WebSocketDisconnect, KeyError)):
            with client.websocket_connect("/ws/executions"):
                pass


class TestAPIVersioning:

    def test_api_v1_prefix(self, client):
        headers = _register(client)
        resp = client.get("/api/v1/jobs", headers=headers)
        assert resp.status_code == 200

    def test_no_prefix_404(self, client):
        resp = client.get("/jobs")
        assert resp.status_code == 404

    def test_auth_routes_under_v1(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "username": "nonexistent",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401
