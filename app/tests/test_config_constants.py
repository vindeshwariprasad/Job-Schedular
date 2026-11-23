"""Tests for config.py and constants.py."""

from config import (
    BACKPRESSURE_CRITICAL_THRESHOLD,
    BACKPRESSURE_WARN_THRESHOLD,
    BASE_RETRY_DELAY,
    CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_MAX_OPEN_RETRIES,
    CIRCUIT_STATE_TTL,
    JOB_EXECUTION_TIMEOUT,
    MAX_RETRIES,
    RATE_LIMIT_WINDOW,
    VISIBILITY_TIMEOUT,
    WORKER_POLL_TIMEOUT,
)
from constants import (
    ALL_READY_QUEUES,
    QUEUE_FAILED,
    QUEUE_PROCESSING,
    QUEUE_READY_HIGH,
    QUEUE_READY_LOW,
    QUEUE_READY_MEDIUM,
    VALID_PRIORITIES,
    queue_for_priority,
)


class TestConfig:

    def test_max_retries_default(self):
        assert MAX_RETRIES == 3

    def test_max_retries_is_int(self):
        assert isinstance(MAX_RETRIES, int)

    def test_visibility_timeout_default(self):
        assert VISIBILITY_TIMEOUT == 30

    def test_worker_poll_timeout_default(self):
        assert WORKER_POLL_TIMEOUT == 5

    def test_rate_limit_window_default(self):
        assert RATE_LIMIT_WINDOW == 60

    def test_base_retry_delay_default(self):
        assert BASE_RETRY_DELAY == 2

    def test_job_execution_timeout_default(self):
        assert JOB_EXECUTION_TIMEOUT == 120

    # Circuit breaker config defaults
    def test_circuit_failure_threshold_default(self):
        assert CIRCUIT_FAILURE_THRESHOLD == 5

    def test_circuit_cooldown_seconds_default(self):
        assert CIRCUIT_COOLDOWN_SECONDS == 30

    def test_circuit_state_ttl_default(self):
        assert CIRCUIT_STATE_TTL == 3600

    def test_circuit_max_open_retries_default(self):
        assert CIRCUIT_MAX_OPEN_RETRIES == 10

    # Backpressure config defaults
    def test_backpressure_warn_threshold_default(self):
        assert BACKPRESSURE_WARN_THRESHOLD == 1000

    def test_backpressure_critical_threshold_default(self):
        assert BACKPRESSURE_CRITICAL_THRESHOLD == 5000

    def test_backpressure_thresholds_are_ints(self):
        assert isinstance(BACKPRESSURE_WARN_THRESHOLD, int)
        assert isinstance(BACKPRESSURE_CRITICAL_THRESHOLD, int)

    def test_backpressure_critical_greater_than_warn(self):
        assert BACKPRESSURE_CRITICAL_THRESHOLD > BACKPRESSURE_WARN_THRESHOLD

    def test_all_positive(self):
        assert MAX_RETRIES > 0
        assert VISIBILITY_TIMEOUT > 0
        assert WORKER_POLL_TIMEOUT > 0
        assert RATE_LIMIT_WINDOW > 0
        assert BASE_RETRY_DELAY > 0
        assert JOB_EXECUTION_TIMEOUT > 0
        assert CIRCUIT_FAILURE_THRESHOLD > 0
        assert CIRCUIT_COOLDOWN_SECONDS > 0
        assert CIRCUIT_STATE_TTL > 0
        assert CIRCUIT_MAX_OPEN_RETRIES > 0
        assert BACKPRESSURE_WARN_THRESHOLD > 0
        assert BACKPRESSURE_CRITICAL_THRESHOLD > 0


class TestConstants:

    def test_queue_ready_high(self):
        assert QUEUE_READY_HIGH == "queue:ready:high"

    def test_queue_ready_medium(self):
        assert QUEUE_READY_MEDIUM == "queue:ready:medium"

    def test_queue_ready_low(self):
        assert QUEUE_READY_LOW == "queue:ready:low"

    def test_queue_processing(self):
        assert QUEUE_PROCESSING == "queue:processing"

    def test_queue_failed(self):
        assert QUEUE_FAILED == "queue:failed"

    def test_all_ready_queues(self):
        assert ALL_READY_QUEUES == [QUEUE_READY_HIGH, QUEUE_READY_MEDIUM, QUEUE_READY_LOW]

    def test_queue_names_are_strings(self):
        assert isinstance(QUEUE_READY_HIGH, str)
        assert isinstance(QUEUE_READY_MEDIUM, str)
        assert isinstance(QUEUE_READY_LOW, str)
        assert isinstance(QUEUE_PROCESSING, str)
        assert isinstance(QUEUE_FAILED, str)

    def test_queue_names_use_colon_namespace(self):
        assert ":" in QUEUE_READY_HIGH
        assert ":" in QUEUE_READY_MEDIUM
        assert ":" in QUEUE_READY_LOW
        assert ":" in QUEUE_PROCESSING
        assert ":" in QUEUE_FAILED

    def test_valid_priorities(self):
        assert VALID_PRIORITIES == {"HIGH", "MEDIUM", "LOW"}

    def test_queue_for_priority_high(self):
        assert queue_for_priority("HIGH") == QUEUE_READY_HIGH

    def test_queue_for_priority_medium(self):
        assert queue_for_priority("MEDIUM") == QUEUE_READY_MEDIUM

    def test_queue_for_priority_low(self):
        assert queue_for_priority("LOW") == QUEUE_READY_LOW

    def test_queue_for_priority_unknown_defaults_medium(self):
        assert queue_for_priority("UNKNOWN") == QUEUE_READY_MEDIUM
