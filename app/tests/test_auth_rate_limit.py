"""Tests for Redis-backed auth rate limiting in api/auth.py.

We set required env vars and mock infrastructure modules before importing
api.auth, because its import chain triggers database engine initialization
(requires asyncpg) and JWT setup (requires JWT_SECRET_KEY).
"""

import os
import sys
from unittest.mock import MagicMock

# Set env vars required by transitive imports (auth.py needs JWT_SECRET_KEY).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

# Prevent db.session from initializing real database engines during import.
# This must happen before any import of api.auth.
_mock_session = MagicMock()
_mock_session.get_db = MagicMock()
sys.modules.setdefault("db.session", _mock_session)

_mock_redis_client = MagicMock()
_mock_redis_client.redis_client = MagicMock()
sys.modules.setdefault("queues.redis_client", _mock_redis_client)

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from api.auth import AUTH_RATE_LIMIT, AUTH_RATE_WINDOW, _check_auth_rate_limit  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _make_request(client_ip: str = "192.168.1.1") -> MagicMock:
    """Create a mock Request object with a given client IP."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = client_ip
    return request


class TestAuthRateLimitConfig:
    """Verify rate limit constants are set correctly."""

    def test_rate_limit_default(self):
        assert AUTH_RATE_LIMIT == 20

    def test_rate_window_default(self):
        assert AUTH_RATE_WINDOW == 120


class TestAuthRateLimitAllows:
    """Test that requests under the limit are allowed through."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Request should pass when is_rate_limited returns False."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", return_value=False) as mock_rl:
            # Should not raise
            await _check_auth_rate_limit(request)

            mock_rl.assert_called_once()
            call_kwargs = mock_rl.call_args.kwargs
            assert call_kwargs["key"] == "auth:192.168.1.1"
            assert call_kwargs["limit"] == AUTH_RATE_LIMIT
            assert call_kwargs["window_seconds"] == AUTH_RATE_WINDOW

    @pytest.mark.asyncio
    async def test_different_ips_independent(self):
        """Different IPs should be rate-limited independently."""
        request_a = _make_request("10.0.0.1")
        request_b = _make_request("10.0.0.2")

        with patch("api.auth.is_rate_limited", return_value=False) as mock_rl:
            await _check_auth_rate_limit(request_a)
            await _check_auth_rate_limit(request_b)

            # Verify different keys were used
            calls = mock_rl.call_args_list
            assert calls[0].kwargs["key"] == "auth:10.0.0.1"
            assert calls[1].kwargs["key"] == "auth:10.0.0.2"


class TestAuthRateLimitBlocks:
    """Test that requests at or over the limit are blocked."""

    @pytest.mark.asyncio
    async def test_blocks_when_limited(self):
        """Should raise 429 when is_rate_limited returns True."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.status_code == 429
            assert "Too many authentication attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_429_includes_retry_after(self):
        """429 response should include Retry-After header."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.headers["Retry-After"] == str(AUTH_RATE_WINDOW)

    @pytest.mark.asyncio
    async def test_unknown_client_uses_fallback_ip(self):
        """Request with no client info should use 'unknown' as key."""
        request = MagicMock()
        request.client = None

        with patch("api.auth.is_rate_limited", return_value=False) as mock_rl:
            await _check_auth_rate_limit(request)
            assert mock_rl.call_args.kwargs["key"] == "auth:unknown"


class TestAuthRateLimitRedisFailure:
    """Test fail-closed behavior when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_connection_error_returns_503(self):
        """ConnectionError from Redis should result in 503."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=ConnectionError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_timeout_error_returns_503(self):
        """TimeoutError from Redis should result in 503."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=TimeoutError("timed out")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_redis_error_returns_503(self):
        """RedisError from Redis should result in 503."""
        from redis.exceptions import RedisError
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=RedisError("cluster down")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_503_includes_retry_after_30(self):
        """503 response should include Retry-After: 30 header."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=ConnectionError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            assert exc_info.value.headers["Retry-After"] == "30"

    @pytest.mark.asyncio
    async def test_503_response_body(self):
        """503 response should contain error_code and message."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=ConnectionError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit(request)

            detail = exc_info.value.detail
            assert detail["error_code"] == "SERVICE_UNAVAILABLE"
            assert "temporarily unavailable" in detail["message"]

    @pytest.mark.asyncio
    async def test_redis_failure_logs_error(self):
        """Redis failure should log at ERROR level."""
        request = _make_request()

        with patch("api.auth.is_rate_limited", side_effect=ConnectionError("refused")):
            with patch("api.auth.logger") as mock_logger:
                with pytest.raises(HTTPException):
                    await _check_auth_rate_limit(request)

                mock_logger.error.assert_called_once()
                # Verify exc_info=True was passed for stack trace
                call_kwargs = mock_logger.error.call_args.kwargs
                assert call_kwargs.get("exc_info") is True

    @pytest.mark.asyncio
    async def test_redis_failure_increments_prometheus_counter(self):
        """Redis failure should increment auth_redis_failures_total metric."""
        from metrics.prometheus import auth_redis_failures_total

        request = _make_request()
        before = auth_redis_failures_total._value.get()

        with patch("api.auth.is_rate_limited", side_effect=ConnectionError("refused")):
            with pytest.raises(HTTPException):
                await _check_auth_rate_limit(request)

        after = auth_redis_failures_total._value.get()
        assert after == before + 1
