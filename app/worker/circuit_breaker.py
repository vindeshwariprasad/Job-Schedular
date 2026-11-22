"""Circuit breaker pattern for external API calls.

States:
    CLOSED   (0) — Normal operation. Requests pass through.
    OPEN     (1) — Endpoint is down. Requests fail fast.
    HALF_OPEN(2) — Cooldown expired. One probe request is allowed.

State stored in Redis hash per endpoint domain:
    circuit:{domain} → {state, failure_count, opened_at}
"""

import hashlib
import time
from enum import IntEnum

from config import CIRCUIT_COOLDOWN_SECONDS, CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_STATE_TTL
from logging_config import get_logger
from metrics.prometheus import (
    circuit_breaker_rejections_total,
    circuit_breaker_state,
    circuit_breaker_trips_total,
)

logger = get_logger("worker.circuit_breaker")


class CircuitState(IntEnum):
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and the request is rejected."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        super().__init__(f"Circuit open for endpoint: {endpoint}")


class CircuitBreaker:
    """Redis-backed circuit breaker for external HTTP endpoints."""

    def __init__(self, endpoint: str, redis):
        self.endpoint = endpoint
        self.redis = redis
        safe = hashlib.sha256(endpoint.encode()).hexdigest()[:12]
        self._key = f"circuit:{safe}"

    def _get_state(self) -> dict:
        """Read circuit state from Redis."""
        data = self.redis.hgetall(self._key)
        if not data:
            return {
                "state": str(CircuitState.CLOSED.value),
                "failure_count": "0",
                "opened_at": "0",
            }
        return data

    def check(self):
        """Check if the request should be allowed.

        Raises CircuitOpenError if the circuit is OPEN and cooldown hasn't expired.
        Transitions OPEN → HALF_OPEN if cooldown has expired.
        """
        data = self._get_state()
        state = int(data.get("state", "0"))

        if state == CircuitState.CLOSED:
            return  # Allow

        if state == CircuitState.HALF_OPEN:
            return  # Allow probe request

        # State is OPEN — check cooldown
        opened_at = float(data.get("opened_at", "0"))
        elapsed = time.time() - opened_at

        if elapsed >= CIRCUIT_COOLDOWN_SECONDS:
            # Cooldown expired → transition to HALF_OPEN
            self.redis.hset(self._key, "state", str(CircuitState.HALF_OPEN.value))
            self.redis.expire(self._key, CIRCUIT_STATE_TTL)
            circuit_breaker_state.labels(endpoint=self.endpoint).set(CircuitState.HALF_OPEN)
            logger.info(
                "Circuit %s → HALF_OPEN (cooldown expired after %.0fs)",
                self.endpoint, elapsed,
            )
            return  # Allow probe

        # Still within cooldown — reject
        circuit_breaker_rejections_total.inc()
        raise CircuitOpenError(self.endpoint)

    def record_success(self):
        """Record a successful request. Resets circuit to CLOSED."""
        data = self._get_state()
        state = int(data.get("state", "0"))

        if state == CircuitState.CLOSED and int(data.get("failure_count", "0")) == 0:
            return  # Already healthy, no-op

        # Reset to CLOSED
        self.redis.hset(self._key, mapping={
            "state": str(CircuitState.CLOSED.value),
            "failure_count": "0",
            "opened_at": "0",
        })
        self.redis.expire(self._key, CIRCUIT_STATE_TTL)
        circuit_breaker_state.labels(endpoint=self.endpoint).set(CircuitState.CLOSED)

        if state != CircuitState.CLOSED:
            logger.info("Circuit %s → CLOSED (success)", self.endpoint)

    def record_failure(self):
        """Record a failed request. May trip circuit to OPEN."""
        data = self._get_state()
        state = int(data.get("state", "0"))

        if state == CircuitState.HALF_OPEN:
            # Probe failed → back to OPEN
            self.redis.hset(self._key, mapping={
                "state": str(CircuitState.OPEN.value),
                "opened_at": str(time.time()),
            })
            self.redis.expire(self._key, CIRCUIT_STATE_TTL)
            circuit_breaker_state.labels(endpoint=self.endpoint).set(CircuitState.OPEN)
            circuit_breaker_trips_total.inc()
            logger.warning("Circuit %s → OPEN (probe failed)", self.endpoint)
            return

        # CLOSED state: increment failure count atomically
        new_count = self.redis.hincrby(self._key, "failure_count", 1)
        self.redis.expire(self._key, CIRCUIT_STATE_TTL)

        if new_count >= CIRCUIT_FAILURE_THRESHOLD:
            # Trip the circuit
            self.redis.hset(self._key, mapping={
                "state": str(CircuitState.OPEN.value),
                "opened_at": str(time.time()),
            })
            self.redis.expire(self._key, CIRCUIT_STATE_TTL)
            circuit_breaker_state.labels(endpoint=self.endpoint).set(CircuitState.OPEN)
            circuit_breaker_trips_total.inc()
            logger.warning(
                "Circuit %s → OPEN (failure_count=%d >= threshold=%d)",
                self.endpoint, new_count, CIRCUIT_FAILURE_THRESHOLD,
            )
        else:
            logger.debug(
                "Circuit %s failure_count=%d/%d",
                self.endpoint, new_count, CIRCUIT_FAILURE_THRESHOLD,
            )
