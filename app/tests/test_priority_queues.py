"""Tests for priority queue routing, weighted polling, and queue_for_priority helper."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from constants import (
    ALL_READY_QUEUES,
    QUEUE_READY_HIGH,
    QUEUE_READY_LOW,
    QUEUE_READY_MEDIUM,
    queue_for_priority,
)
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.schedule import Schedule, ScheduleStatus

REDIS_PATCH = "scheduler.scheduler.redis_client"


class TestQueueForPriority:
    """Tests for the queue_for_priority helper function."""

    def test_high_maps_to_high_queue(self):
        assert queue_for_priority("HIGH") == QUEUE_READY_HIGH

    def test_medium_maps_to_medium_queue(self):
        assert queue_for_priority("MEDIUM") == QUEUE_READY_MEDIUM

    def test_low_maps_to_low_queue(self):
        assert queue_for_priority("LOW") == QUEUE_READY_LOW

    def test_unknown_defaults_to_medium(self):
        assert queue_for_priority("INVALID") == QUEUE_READY_MEDIUM

    def test_empty_string_defaults_to_medium(self):
        assert queue_for_priority("") == QUEUE_READY_MEDIUM

    def test_none_defaults_to_medium(self):
        assert queue_for_priority(None) == QUEUE_READY_MEDIUM


class TestSchedulerPriorityRouting:
    """Tests that the scheduler enqueues to the correct priority queue."""

    def _create_job(self, db, job_id, priority="MEDIUM"):
        job = Job(
            id=job_id,
            user_id=1,
            name=f"Priority {priority} Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
            is_active=True,
            priority=priority,
        )
        db.add(job)
        db.commit()
        return job

    def test_high_priority_job_enqueued_to_high_queue(self, db, fake_redis):
        job = self._create_job(db, 1, priority="HIGH")
        schedule = Schedule(
            job_id=job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 1
        assert fake_redis.llen(QUEUE_READY_HIGH) == 1
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0
        assert fake_redis.llen(QUEUE_READY_LOW) == 0

    def test_low_priority_job_enqueued_to_low_queue(self, db, fake_redis):
        job = self._create_job(db, 1, priority="LOW")
        schedule = Schedule(
            job_id=job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 1
        assert fake_redis.llen(QUEUE_READY_LOW) == 1
        assert fake_redis.llen(QUEUE_READY_HIGH) == 0
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0

    def test_mixed_priorities_routed_correctly(self, db, fake_redis):
        for i, priority in enumerate(["HIGH", "MEDIUM", "LOW"], start=1):
            job = self._create_job(db, i, priority=priority)
            schedule = Schedule(
                job_id=job.id,
                cron_expression="*/5 * * * *",
                next_run_at=datetime.now(UTC) - timedelta(minutes=1),
                status=ScheduleStatus.ACTIVE,
                run_count=0,
            )
            db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 3
        assert fake_redis.llen(QUEUE_READY_HIGH) == 1
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 1
        assert fake_redis.llen(QUEUE_READY_LOW) == 1


class TestWorkerWeightedPolling:
    """Tests for the weighted random queue selection."""

    def test_pick_queue_order_returns_all_three_queues(self):
        from worker.worker import _pick_queue_order
        order = _pick_queue_order()
        assert len(order) == 3
        assert set(order) == {QUEUE_READY_HIGH, QUEUE_READY_MEDIUM, QUEUE_READY_LOW}

    def test_pick_queue_order_distribution(self):
        """Over many rolls, HIGH should be first ~60%, MEDIUM ~30%, LOW ~10%."""
        from worker.worker import _pick_queue_order
        counts = Counter()
        n = 10000
        for _ in range(n):
            order = _pick_queue_order()
            counts[order[0]] += 1

        # Allow generous margin (±5%)
        assert counts[QUEUE_READY_HIGH] / n > 0.50
        assert counts[QUEUE_READY_HIGH] / n < 0.70
        assert counts[QUEUE_READY_MEDIUM] / n > 0.20
        assert counts[QUEUE_READY_MEDIUM] / n < 0.40
        assert counts[QUEUE_READY_LOW] / n > 0.05
        assert counts[QUEUE_READY_LOW] / n < 0.20


class TestWorkerPriorityRetry:
    """Tests that worker retries use the correct priority queue."""

    def test_retry_enqueues_to_correct_priority_queue(self, db, fake_redis):
        job = Job(
            id=1,
            user_id=1,
            name="High Priority Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
            is_active=True,
            priority="HIGH",
        )
        db.add(job)
        db.commit()

        execution = Execution(
            job_id=job.id,
            execution_id="retry-priority-001",
            status=ExecutionStatus.RUNNING,
            attempt=1,
            started_at=datetime.now(UTC),
        )
        db.add(execution)
        db.commit()

        from worker.worker import handle_failure
        handle_failure(db, fake_redis, execution, job, RuntimeError("temp"), max_retries=3, base_delay=0)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.PENDING
        # Should be in the HIGH queue, not MEDIUM
        assert fake_redis.llen(QUEUE_READY_HIGH) == 1
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0

    def test_rate_limited_re_enqueues_to_correct_priority(self, db, fake_redis):
        job = Job(
            id=1,
            user_id=1,
            name="Low Priority Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
            is_active=True,
            priority="LOW",
        )
        db.add(job)
        db.commit()

        execution = Execution(
            job_id=job.id,
            execution_id="rate-limited-priority-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(execution)
        db.commit()

        with patch("worker.worker.is_rate_limited", return_value=True):
            from worker.worker import process_execution
            process_execution(db, fake_redis, "rate-limited-priority-001")

        assert fake_redis.llen(QUEUE_READY_LOW) == 1
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0


class TestAllReadyQueues:
    """Tests for ALL_READY_QUEUES constant."""

    def test_contains_all_three_queues(self):
        assert len(ALL_READY_QUEUES) == 3
        assert QUEUE_READY_HIGH in ALL_READY_QUEUES
        assert QUEUE_READY_MEDIUM in ALL_READY_QUEUES
        assert QUEUE_READY_LOW in ALL_READY_QUEUES

    def test_order_is_high_medium_low(self):
        assert ALL_READY_QUEUES[0] == QUEUE_READY_HIGH
        assert ALL_READY_QUEUES[1] == QUEUE_READY_MEDIUM
        assert ALL_READY_QUEUES[2] == QUEUE_READY_LOW
