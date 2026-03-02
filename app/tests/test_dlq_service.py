"""Tests for DLQ replay service with idempotency checks."""

from unittest.mock import patch
from db.models.execution import Execution, ExecutionStatus
from db.models.dead_letter import DeadLetterJob
from tests.async_test_helpers import SyncToAsyncSessionWrapper


REDIS_PATCH = "services.dlq_service.redis_client"


class TestReplayDLQExecution:

    def _add_dlq_entry(self, db, job_id=1, execution_id="failed-exec-001"):
        dlq = DeadLetterJob(
            job_id=job_id,
            execution_id=execution_id,
            payload={"job_id": job_id, "execution_id": execution_id},
            error="something broke",
        )
        db.add(dlq)
        db.commit()
        return dlq

    async def test_replay_creates_new_execution(self, db, sample_job, fake_redis):
        """Replaying a DLQ entry should create a new PENDING execution."""
        self._add_dlq_entry(db, job_id=sample_job.id)

        with patch(REDIS_PATCH, fake_redis):
            from services.dlq_service import replay_dlq_execution
            result = await replay_dlq_execution(
                SyncToAsyncSessionWrapper(db), "failed-exec-001"
            )

        assert result["status"] == "replayed"
        assert result["old_execution_id"] == "failed-exec-001"
        assert result["new_execution_id"] != "failed-exec-001"

        new_exec = db.query(Execution).filter(
            Execution.execution_id == result["new_execution_id"]
        ).first()
        assert new_exec is not None
        assert new_exec.status == ExecutionStatus.PENDING
        assert fake_redis.llen("queue:ready") == 1

    async def test_idempotency_blocks_duplicate_replay(self, db, sample_job, fake_redis):
        """If a PENDING execution already exists for the job, replay should be skipped."""
        self._add_dlq_entry(db, job_id=sample_job.id)

        # Simulate an existing in-flight execution for the same job
        existing = Execution(
            job_id=sample_job.id,
            execution_id="already-in-flight",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(existing)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from services.dlq_service import replay_dlq_execution
            result = await replay_dlq_execution(
                SyncToAsyncSessionWrapper(db), "failed-exec-001"
            )

        assert result["status"] == "already_in_flight"
        assert result["new_execution_id"] == "already-in-flight"
        # No new execution should be created
        assert db.query(Execution).count() == 1
        assert fake_redis.llen("queue:ready") == 0

    async def test_replay_not_found_raises(self, db, fake_redis):
        """Replaying a non-existent DLQ entry should raise ValueError."""
        import pytest
        with patch(REDIS_PATCH, fake_redis):
            from services.dlq_service import replay_dlq_execution
            with pytest.raises(ValueError, match="DLQ entry not found"):
                await replay_dlq_execution(
                    SyncToAsyncSessionWrapper(db), "does-not-exist"
                )
