"""Integration tests: circuit breaker + worker handle_failure interaction."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from worker.circuit_breaker import CircuitOpenError
from worker.worker import handle_failure


class TestCircuitOpenHandleFailure:
    """Tests for handle_failure when error is CircuitOpenError."""

    def _make_execution(self, db, job_id, attempt=1, error=None):
        ex = Execution(
            job_id=job_id,
            execution_id="circuit-test-001",
            status=ExecutionStatus.RUNNING,
            attempt=attempt,
            started_at=datetime.now(UTC),
            error=error,
        )
        db.add(ex)
        db.commit()
        return ex

    def test_does_not_increment_attempt(self, db, sample_job, fake_redis):
        """CircuitOpenError should NOT increment attempt counter."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        handle_failure(
            db, fake_redis, execution, sample_job,
            CircuitOpenError("example.com"),
            max_retries=3, base_delay=0,
        )

        db.refresh(execution)
        assert execution.attempt == 1  # NOT incremented
        assert execution.status == ExecutionStatus.PENDING
        assert fake_redis.llen("queue:ready") == 1

    def test_re_enqueues_to_ready_queue(self, db, sample_job, fake_redis):
        """CircuitOpenError should re-enqueue the execution."""
        execution = self._make_execution(db, sample_job.id, attempt=2)

        handle_failure(
            db, fake_redis, execution, sample_job,
            CircuitOpenError("example.com"),
            max_retries=3, base_delay=0,
        )

        items = fake_redis.lrange("queue:ready", 0, -1)
        assert len(items) == 1
        payload = json.loads(items[0])
        assert payload["execution_id"] == "circuit-test-001"

    def test_tracks_circuit_retries_in_error(self, db, sample_job, fake_redis):
        """Circuit retry count should be tracked in execution.error."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        handle_failure(
            db, fake_redis, execution, sample_job,
            CircuitOpenError("example.com"),
            max_retries=3, base_delay=0,
        )

        db.refresh(execution)
        assert "circuit_retries=1" in execution.error

    def test_increments_circuit_retries(self, db, sample_job, fake_redis):
        """Consecutive circuit-open failures should increment circuit retry count."""
        execution = self._make_execution(
            db, sample_job.id, attempt=1,
            error="Circuit open for example.com (circuit_retries=3)",
        )

        handle_failure(
            db, fake_redis, execution, sample_job,
            CircuitOpenError("example.com"),
            max_retries=3, base_delay=0,
        )

        db.refresh(execution)
        assert "circuit_retries=4" in execution.error

    def test_dlq_after_max_circuit_retries(self, db, sample_job, fake_redis):
        """After CIRCUIT_MAX_OPEN_RETRIES, should send to DLQ."""
        execution = self._make_execution(
            db, sample_job.id, attempt=1,
            error="Circuit open for example.com (circuit_retries=10)",
        )

        with patch("worker.worker.CIRCUIT_MAX_OPEN_RETRIES", 10):
            handle_failure(
                db, fake_redis, execution, sample_job,
                CircuitOpenError("example.com"),
                max_retries=3, base_delay=0,
            )

        db.refresh(execution)
        assert execution.status == ExecutionStatus.FAILED
        dlq = db.query(DeadLetterJob).first()
        assert dlq is not None
        assert "circuit open" in dlq.error.lower()
        assert fake_redis.llen("queue:failed") == 1

    def test_preserves_retry_budget(self, db, sample_job, fake_redis):
        """After circuit-open retries, attempt should still be 1 (budget preserved)."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        # 5 circuit-open failures
        for _ in range(5):
            handle_failure(
                db, fake_redis, execution, sample_job,
                CircuitOpenError("example.com"),
                max_retries=3, base_delay=0,
            )
            db.refresh(execution)

        # Attempt should still be 1 — retry budget untouched
        assert execution.attempt == 1
        assert execution.status == ExecutionStatus.PENDING

    def test_normal_error_still_increments_attempt(self, db, sample_job, fake_redis):
        """Regular errors (not CircuitOpenError) should still increment attempt."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        handle_failure(
            db, fake_redis, execution, sample_job,
            RuntimeError("API down"),
            max_retries=3, base_delay=0,
        )

        db.refresh(execution)
        assert execution.attempt == 2  # Incremented normally
