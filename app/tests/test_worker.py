"""Tests for worker retry logic, DLQ flow, and execution processing."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from worker.worker import handle_failure, process_execution


class TestHandleFailure:
    """Tests for the retry / DLQ decision logic."""

    def _make_execution(self, db, job_id, attempt=1):
        ex = Execution(
            job_id=job_id,
            execution_id="test-exec-001",
            status=ExecutionStatus.RUNNING,
            attempt=attempt,
            started_at=datetime.now(UTC),
        )
        db.add(ex)
        db.commit()
        return ex

    def test_retry_on_first_failure(self, db, sample_job, fake_redis):
        """First failure should increment attempt, set PENDING, and re-enqueue."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("boom"), max_retries=3, base_delay=0)

        db.refresh(execution)
        assert execution.attempt == 2
        assert execution.status == ExecutionStatus.PENDING
        assert execution.error == "boom"
        assert fake_redis.llen("queue:ready:medium") == 1

    def test_moves_to_dlq_after_max_retries(self, db, sample_job, fake_redis):
        """When attempts exceed max_retries, execution goes to DLQ."""
        execution = self._make_execution(db, sample_job.id, attempt=3)

        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("final fail"), max_retries=3, base_delay=0)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.FAILED
        assert execution.attempt == 4

        dlq = db.query(DeadLetterJob).first()
        assert dlq is not None
        assert dlq.execution_id == "test-exec-001"
        assert dlq.error == "final fail"

        # Should be in failed queue, NOT ready queue
        assert fake_redis.llen("queue:failed") == 1
        assert fake_redis.llen("queue:ready:medium") == 0

    def test_retry_re_enqueues_to_ready(self, db, sample_job, fake_redis):
        """Retried execution should land back in the ready queue with correct payload."""
        execution = self._make_execution(db, sample_job.id, attempt=1)
        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("temp"), max_retries=3, base_delay=0)

        items = fake_redis.lrange("queue:ready:medium", 0, -1)
        assert len(items) == 1
        payload = json.loads(items[0])
        assert payload["execution_id"] == "test-exec-001"
        assert payload["job_id"] == sample_job.id

    def test_error_message_stored(self, db, sample_job, fake_redis):
        """The error message should be persisted on the execution record."""
        execution = self._make_execution(db, sample_job.id, attempt=1)
        handle_failure(db, fake_redis, execution, sample_job, ValueError("bad input"), max_retries=3, base_delay=0)

        db.refresh(execution)
        assert execution.error == "bad input"


class TestProcessExecution:
    """Tests for the full process_execution flow."""

    def test_skips_non_pending_execution(self, db, sample_job, fake_redis):
        """Already-running executions should be skipped."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="already-running",
            status=ExecutionStatus.RUNNING,
            attempt=1,
            started_at=datetime.now(UTC),
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.execute_job") as mock_exec:
            process_execution(db, fake_redis, "already-running")
            mock_exec.assert_not_called()

    def test_success_path(self, db, sample_job, fake_redis):
        """Successful execution should mark status SUCCESS."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="will-succeed",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=False), \
             patch("worker.worker.execute_job", return_value={"ok": True}):
            process_execution(db, fake_redis, "will-succeed")

        db.refresh(ex)
        assert ex.status == ExecutionStatus.SUCCESS
        assert ex.finished_at is not None
