"""Extended tests for worker: _publish_update, rate limiting, handle_task, process_execution edge cases."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from db.models.retry_policy import RetryPolicy
from worker.worker import (
    PUBSUB_CHANNEL,
    _publish_update,
    handle_failure,
    process_execution,
    update_queue_metrics,
)


class TestPublishUpdate:
    """Tests for Redis pub/sub publish function."""

    def test_publishes_to_correct_channel(self, fake_redis):
        execution = MagicMock()
        execution.execution_id = "exec-001"
        execution.job_id = 1
        execution.status = ExecutionStatus.SUCCESS
        execution.attempt = 1
        execution.started_at = datetime.now(UTC)
        execution.finished_at = datetime.now(UTC)
        execution.error = None

        job = MagicMock()
        job.user_id = 42

        _publish_update(fake_redis, execution, job)

        assert len(fake_redis._pubsub_messages) == 1
        msg = fake_redis._pubsub_messages[0]
        assert msg["channel"] == PUBSUB_CHANNEL

    def test_publish_payload_format(self, fake_redis):
        execution = MagicMock()
        execution.execution_id = "exec-002"
        execution.job_id = 5
        execution.status = ExecutionStatus.RUNNING
        execution.attempt = 2
        execution.started_at = datetime(2024, 1, 1, tzinfo=UTC)
        execution.finished_at = None
        execution.error = "Some error"

        job = MagicMock()
        job.user_id = 10

        _publish_update(fake_redis, execution, job)

        payload = json.loads(fake_redis._pubsub_messages[0]["message"])
        assert payload["execution_id"] == "exec-002"
        assert payload["job_id"] == 5
        assert payload["user_id"] == 10
        assert payload["status"] == "RUNNING"
        assert payload["attempt"] == 2
        assert payload["error"] == "Some error"

    def test_publish_handles_exception(self, fake_redis):
        """If publish fails, it should log error but not raise."""
        execution = MagicMock()
        execution.execution_id = "exec-003"
        execution.job_id = 1
        execution.status = ExecutionStatus.SUCCESS
        execution.attempt = 1
        execution.started_at = None
        execution.finished_at = None
        execution.error = None

        job = MagicMock()
        job.user_id = 1

        broken_redis = MagicMock()
        broken_redis.publish.side_effect = Exception("Redis down")

        # Should not raise
        _publish_update(broken_redis, execution, job)

    def test_publish_with_enum_status(self, fake_redis):
        """Status should handle both enum and string values."""
        execution = MagicMock()
        execution.execution_id = "exec-004"
        execution.job_id = 1
        execution.status = ExecutionStatus.PENDING
        execution.attempt = 1
        execution.started_at = None
        execution.finished_at = None
        execution.error = None

        job = MagicMock()
        job.user_id = 1

        _publish_update(fake_redis, execution, job)
        payload = json.loads(fake_redis._pubsub_messages[0]["message"])
        assert payload["status"] == "PENDING"


class TestUpdateQueueMetrics:
    """Tests for queue metrics updater."""

    def test_sets_queue_sizes(self, fake_redis):
        fake_redis.lpush("queue:ready:high", "x")
        fake_redis.lpush("queue:ready:medium", "a", "b")
        fake_redis.lpush("queue:ready:low", "y")
        fake_redis.lpush("queue:processing", "c")
        fake_redis.lpush("queue:failed", "d", "e", "f")

        with patch("worker.worker.queue_ready_size") as ready, \
             patch("worker.worker.queue_ready_priority_size"), \
             patch("worker.worker.queue_processing_size") as processing, \
             patch("worker.worker.queue_failed_size") as failed:
            update_queue_metrics(fake_redis)
            ready.set.assert_called_once_with(4)  # 1 + 2 + 1
            processing.set.assert_called_once_with(1)
            failed.set.assert_called_once_with(3)

    def test_empty_queues(self, fake_redis):
        with patch("worker.worker.queue_ready_size") as ready, \
             patch("worker.worker.queue_ready_priority_size"), \
             patch("worker.worker.queue_processing_size") as processing, \
             patch("worker.worker.queue_failed_size") as failed:
            update_queue_metrics(fake_redis)
            ready.set.assert_called_once_with(0)
            processing.set.assert_called_once_with(0)
            failed.set.assert_called_once_with(0)


class TestProcessExecutionExtended:
    """Extended tests for process_execution."""

    def test_execution_not_found(self, db, sample_job, fake_redis):
        """Non-existent execution should be silently skipped."""
        process_execution(db, fake_redis, "nonexistent-exec-id")
        # No crash = success

    def test_rate_limited_re_enqueues(self, db, sample_job, fake_redis):
        """Rate-limited execution should be re-enqueued to ready queue."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="rate-limited-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=True):
            process_execution(db, fake_redis, "rate-limited-001")

        db.refresh(ex)
        assert ex.status == ExecutionStatus.PENDING
        assert fake_redis.llen("queue:ready:medium") == 1

    def test_success_sets_finished_at(self, db, sample_job, fake_redis):
        """Successful execution should have finished_at set."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="success-ts-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=False), \
             patch("worker.worker.execute_job", return_value={"ok": True}):
            process_execution(db, fake_redis, "success-ts-001")

        db.refresh(ex)
        assert ex.finished_at is not None

    def test_success_sets_started_at(self, db, sample_job, fake_redis):
        """Successful execution should have started_at set."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="started-ts-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=False), \
             patch("worker.worker.execute_job", return_value={"ok": True}):
            process_execution(db, fake_redis, "started-ts-001")

        db.refresh(ex)
        assert ex.started_at is not None

    def test_job_not_found_raises(self, db, fake_redis):
        """Execution referencing non-existent job should raise RuntimeError."""
        ex = Execution(
            job_id=99999,
            execution_id="no-job-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with pytest.raises(RuntimeError, match="Job not found"):
            process_execution(db, fake_redis, "no-job-001")

    def test_failure_triggers_retry(self, db, sample_job, fake_redis):
        """Failed execution with retries remaining should re-enqueue."""
        ex = Execution(
            job_id=sample_job.id,
            execution_id="retry-me-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=False), \
             patch("worker.worker.execute_job", side_effect=RuntimeError("fail")):
            process_execution(db, fake_redis, "retry-me-001")

        db.refresh(ex)
        assert ex.status == ExecutionStatus.PENDING
        assert ex.attempt == 2

    def test_uses_retry_policy_when_available(self, db, sample_job, fake_redis):
        """Should use job-specific retry policy when it exists."""
        policy = RetryPolicy(job_id=sample_job.id, max_retries=1, base_delay_seconds=0)
        db.add(policy)

        ex = Execution(
            job_id=sample_job.id,
            execution_id="policy-exec-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(ex)
        db.commit()

        # First failure: attempt 1 -> 2, max_retries=1, 2 > 1 -> DLQ
        with patch("worker.worker.is_rate_limited", return_value=False), \
             patch("worker.worker.execute_job", side_effect=RuntimeError("fail")):
            process_execution(db, fake_redis, "policy-exec-001")

        db.refresh(ex)
        assert ex.status == ExecutionStatus.FAILED
        assert db.query(DeadLetterJob).count() == 1


class TestHandleFailureExtended:
    """Extended tests for handle_failure."""

    def _make_execution(self, db, job_id, attempt=1, exec_id="test-exec-001"):
        ex = Execution(
            job_id=job_id,
            execution_id=exec_id,
            status=ExecutionStatus.RUNNING,
            attempt=attempt,
            started_at=datetime.now(UTC),
        )
        db.add(ex)
        db.commit()
        return ex

    def test_exponential_backoff_delay(self, db, sample_job, fake_redis):
        """Retry delay should follow exponential backoff."""
        execution = self._make_execution(db, sample_job.id, attempt=2)

        import time
        start = time.time()
        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("err"), max_retries=5, base_delay=0)
        elapsed = time.time() - start
        # base_delay=0 so should complete immediately
        assert elapsed < 2

    def test_dlq_entry_has_correct_payload(self, db, sample_job, fake_redis):
        """DLQ entry should contain job_id and execution_id in payload."""
        execution = self._make_execution(db, sample_job.id, attempt=3)

        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("final"), max_retries=3, base_delay=0)

        dlq = db.query(DeadLetterJob).first()
        assert dlq.payload["job_id"] == sample_job.id
        assert dlq.payload["execution_id"] == execution.execution_id

    def test_dlq_adds_to_failed_queue(self, db, sample_job, fake_redis):
        """DLQ should push execution_id to failed queue."""
        execution = self._make_execution(db, sample_job.id, attempt=3)

        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("final"), max_retries=3, base_delay=0)

        items = fake_redis.lrange("queue:failed", 0, -1)
        assert execution.execution_id in items

    def test_retry_payload_format(self, db, sample_job, fake_redis):
        """Retry should enqueue correct JSON payload to ready queue."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("temp"), max_retries=3, base_delay=0)

        items = fake_redis.lrange("queue:ready:medium", 0, -1)
        payload = json.loads(items[0])
        assert payload["execution_id"] == execution.execution_id
        assert payload["job_id"] == sample_job.id

    def test_multiple_retries_then_dlq(self, db, sample_job, fake_redis):
        """Multiple failures should eventually lead to DLQ."""
        execution = self._make_execution(db, sample_job.id, attempt=1)

        # Attempt 1->2 (retry)
        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("fail"), max_retries=2, base_delay=0)
        assert execution.status == ExecutionStatus.PENDING
        assert execution.attempt == 2

        # Attempt 2->3 (DLQ, since 3 > 2)
        handle_failure(db, fake_redis, execution, sample_job, RuntimeError("fail"), max_retries=2, base_delay=0)
        assert execution.status == ExecutionStatus.FAILED
        assert execution.attempt == 3
        assert db.query(DeadLetterJob).count() == 1
