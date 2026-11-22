"""Tests for the circuit breaker pattern: state transitions, failure counting, cooldown."""

import time
from unittest.mock import patch

import pytest
from worker.circuit_breaker import CircuitBreaker, CircuitOpenError


class TestCircuitBreakerClosed:
    """Tests for CLOSED state behavior."""

    def test_allows_requests_when_closed(self, fake_redis):
        """CLOSED circuit should allow requests (no exception)."""
        cb = CircuitBreaker("example.com", fake_redis)
        cb.check()  # Should not raise

    def test_stays_closed_below_threshold(self, fake_redis):
        """Circuit should stay CLOSED when failures are below threshold."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 5):
            for _ in range(4):
                cb.record_failure()
            cb.check()  # Should not raise — still CLOSED

    def test_record_success_resets_failure_count(self, fake_redis):
        """Success should reset failure count to 0."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 5):
            for _ in range(3):
                cb.record_failure()
            cb.record_success()
            # Now add 4 more failures — should still be below threshold
            for _ in range(4):
                cb.record_failure()
            cb.check()  # Should not raise


class TestCircuitBreakerTripping:
    """Tests for CLOSED → OPEN transition."""

    def test_trips_open_at_threshold(self, fake_redis):
        """Circuit should trip OPEN after reaching failure threshold."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 3):
            cb.record_failure()
            cb.record_failure()
            cb.record_failure()  # 3rd failure = threshold
            with pytest.raises(CircuitOpenError):
                cb.check()

    def test_open_circuit_rejects_immediately(self, fake_redis):
        """OPEN circuit should raise CircuitOpenError."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 1), \
             patch("worker.circuit_breaker.CIRCUIT_COOLDOWN_SECONDS", 60):
            cb.record_failure()
            with pytest.raises(CircuitOpenError) as exc_info:
                cb.check()
            assert "example.com" in str(exc_info.value)

    def test_circuit_open_error_has_endpoint(self, fake_redis):
        """CircuitOpenError should contain the endpoint name."""
        err = CircuitOpenError("api.example.com")
        assert err.endpoint == "api.example.com"
        assert "api.example.com" in str(err)


class TestCircuitBreakerCooldown:
    """Tests for OPEN → HALF_OPEN transition via cooldown."""

    def test_transitions_to_half_open_after_cooldown(self, fake_redis):
        """After cooldown expires, circuit should transition to HALF_OPEN."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 1), \
             patch("worker.circuit_breaker.CIRCUIT_COOLDOWN_SECONDS", 1):
            cb.record_failure()  # Trip to OPEN

            # Verify it's OPEN
            with pytest.raises(CircuitOpenError):
                cb.check()

            # Wait for cooldown
            time.sleep(1.1)

            # Should now be HALF_OPEN — allows request
            cb.check()  # Should not raise

    def test_stays_open_during_cooldown(self, fake_redis):
        """Circuit should stay OPEN during cooldown period."""
        cb = CircuitBreaker("example.com", fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 1), \
             patch("worker.circuit_breaker.CIRCUIT_COOLDOWN_SECONDS", 60):
            cb.record_failure()
            with pytest.raises(CircuitOpenError):
                cb.check()


class TestCircuitBreakerHalfOpen:
    """Tests for HALF_OPEN state behavior."""

    def _make_half_open(self, fake_redis, endpoint="example.com"):
        """Helper: create a circuit in HALF_OPEN state."""
        cb = CircuitBreaker(endpoint, fake_redis)
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 1), \
             patch("worker.circuit_breaker.CIRCUIT_COOLDOWN_SECONDS", 0):
            cb.record_failure()  # Trip to OPEN
            cb.check()  # Cooldown=0, transitions to HALF_OPEN
        return cb

    def test_half_open_success_closes_circuit(self, fake_redis):
        """Success in HALF_OPEN should transition to CLOSED."""
        cb = self._make_half_open(fake_redis)
        cb.record_success()

        # Should be CLOSED now — verify by adding failures below threshold
        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 5):
            cb.record_failure()
            cb.check()  # Should not raise — CLOSED with 1 failure

    def test_half_open_failure_reopens_circuit(self, fake_redis):
        """Failure in HALF_OPEN should transition back to OPEN."""
        cb = self._make_half_open(fake_redis)

        with patch("worker.circuit_breaker.CIRCUIT_COOLDOWN_SECONDS", 60):
            cb.record_failure()  # Back to OPEN
            with pytest.raises(CircuitOpenError):
                cb.check()


class TestCircuitBreakerIsolation:
    """Tests for independent circuit breakers per endpoint."""

    def test_different_endpoints_independent(self, fake_redis):
        """Failures on one endpoint should not affect another."""
        cb_a = CircuitBreaker("api-a.com", fake_redis)
        cb_b = CircuitBreaker("api-b.com", fake_redis)

        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 2):
            cb_a.record_failure()
            cb_a.record_failure()  # Trip A to OPEN

            # B should still be CLOSED
            cb_b.check()  # Should not raise

    def test_same_endpoint_shares_state(self, fake_redis):
        """Multiple CircuitBreaker instances for the same endpoint share state."""
        cb1 = CircuitBreaker("api.com", fake_redis)
        cb2 = CircuitBreaker("api.com", fake_redis)

        with patch("worker.circuit_breaker.CIRCUIT_FAILURE_THRESHOLD", 2):
            cb1.record_failure()
            cb1.record_failure()  # Trip to OPEN

            with pytest.raises(CircuitOpenError):
                cb2.check()  # Same endpoint, should be OPEN


class TestCircuitBreakerTTL:
    """Tests for Redis key TTL."""

    def test_sets_ttl_on_state_change(self, fake_redis):
        """Circuit breaker should set TTL on Redis key."""
        cb = CircuitBreaker("example.com", fake_redis)
        cb.record_failure()
        # Check that expire was called on the key
        assert cb._key in fake_redis._expiry
