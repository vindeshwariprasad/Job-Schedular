"""Tests for config.py and constants.py."""

from config import (
    BASE_RETRY_DELAY,
    JOB_EXECUTION_TIMEOUT,
    MAX_RETRIES,
    RATE_LIMIT_WINDOW,
    VISIBILITY_TIMEOUT,
    WORKER_POLL_TIMEOUT,
)
from constants import QUEUE_FAILED, QUEUE_PROCESSING, QUEUE_READY


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

    def test_all_positive(self):
        assert MAX_RETRIES > 0
        assert VISIBILITY_TIMEOUT > 0
        assert WORKER_POLL_TIMEOUT > 0
        assert RATE_LIMIT_WINDOW > 0
        assert BASE_RETRY_DELAY > 0
        assert JOB_EXECUTION_TIMEOUT > 0


class TestConstants:

    def test_queue_ready(self):
        assert QUEUE_READY == "queue:ready"

    def test_queue_processing(self):
        assert QUEUE_PROCESSING == "queue:processing"

    def test_queue_failed(self):
        assert QUEUE_FAILED == "queue:failed"

    def test_queue_names_are_strings(self):
        assert isinstance(QUEUE_READY, str)
        assert isinstance(QUEUE_PROCESSING, str)
        assert isinstance(QUEUE_FAILED, str)

    def test_queue_names_use_colon_namespace(self):
        assert ":" in QUEUE_READY
        assert ":" in QUEUE_PROCESSING
        assert ":" in QUEUE_FAILED
