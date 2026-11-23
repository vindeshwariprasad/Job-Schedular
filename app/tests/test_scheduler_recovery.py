"""Tests for scheduler orphan recovery and extended scheduling scenarios."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.schedule import Schedule, ScheduleStatus

REDIS_PATCH = "scheduler.scheduler.redis_client"


class TestRecoverOrphanedExecutions:
    """Tests for recover_orphaned_executions()."""

    def _create_job(self, db, job_id=1):
        job = Job(
            id=job_id,
            user_id=1,
            name="Recovery Test Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
            is_active=True,
        )
        db.add(job)
        db.commit()
        return job

    def test_recovers_stuck_running(self, db, fake_redis):
        """RUNNING executions older than VISIBILITY_TIMEOUT should be reset to PENDING."""
        job = self._create_job(db)
        cutoff = datetime.now(UTC) - timedelta(seconds=60)
        execution = Execution(
            job_id=job.id,
            execution_id="stuck-running-001",
            status=ExecutionStatus.RUNNING,
            attempt=1,
            started_at=cutoff,
        )
        db.add(execution)
        db.commit()

        with patch(REDIS_PATCH, fake_redis), \
             patch("scheduler.scheduler.VISIBILITY_TIMEOUT", 30):
            from scheduler.scheduler import recover_orphaned_executions
            recover_orphaned_executions(db)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.PENDING
        assert fake_redis.llen("queue:ready:medium") == 1

    def test_does_not_recover_recent_running(self, db, fake_redis):
        """Recently started RUNNING executions should not be recovered."""
        job = self._create_job(db)
        execution = Execution(
            job_id=job.id,
            execution_id="recent-running-001",
            status=ExecutionStatus.RUNNING,
            attempt=1,
            started_at=datetime.now(UTC),
        )
        db.add(execution)
        db.commit()

        with patch(REDIS_PATCH, fake_redis), \
             patch("scheduler.scheduler.VISIBILITY_TIMEOUT", 30):
            from scheduler.scheduler import recover_orphaned_executions
            recover_orphaned_executions(db)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.RUNNING
        assert fake_redis.llen("queue:ready:medium") == 0

    def test_recovers_orphaned_pending(self, db, fake_redis):
        """PENDING executions not in any Redis queue should be re-enqueued."""
        job = self._create_job(db)
        old_time = datetime.now(UTC) - timedelta(seconds=60)
        execution = Execution(
            job_id=job.id,
            execution_id="orphan-pending-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
            created_at=old_time,
        )
        db.add(execution)
        db.commit()

        with patch(REDIS_PATCH, fake_redis), \
             patch("scheduler.scheduler.VISIBILITY_TIMEOUT", 30):
            from scheduler.scheduler import recover_orphaned_executions
            recover_orphaned_executions(db)

        assert fake_redis.llen("queue:ready:medium") == 1

    def test_skips_already_queued_pending(self, db, fake_redis):
        """PENDING executions already in Redis should NOT be re-enqueued."""
        job = self._create_job(db)
        old_time = datetime.now(UTC) - timedelta(seconds=60)
        execution = Execution(
            job_id=job.id,
            execution_id="already-queued-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
            created_at=old_time,
        )
        db.add(execution)
        db.commit()

        # Put it in Redis ready queue already
        fake_redis.lpush("queue:ready:medium", json.dumps({
            "execution_id": "already-queued-001",
            "job_id": job.id,
        }))

        with patch(REDIS_PATCH, fake_redis), \
             patch("scheduler.scheduler.VISIBILITY_TIMEOUT", 30):
            from scheduler.scheduler import recover_orphaned_executions
            recover_orphaned_executions(db)

        # Should still be just 1 (the original), not duplicated
        assert fake_redis.llen("queue:ready:medium") == 1

    def test_does_not_recover_success_executions(self, db, fake_redis):
        """SUCCESS executions should never be recovered."""
        job = self._create_job(db)
        execution = Execution(
            job_id=job.id,
            execution_id="success-001",
            status=ExecutionStatus.SUCCESS,
            attempt=1,
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            finished_at=datetime.now(UTC) - timedelta(minutes=4),
        )
        db.add(execution)
        db.commit()

        with patch(REDIS_PATCH, fake_redis), \
             patch("scheduler.scheduler.VISIBILITY_TIMEOUT", 30):
            from scheduler.scheduler import recover_orphaned_executions
            recover_orphaned_executions(db)

        assert fake_redis.llen("queue:ready:medium") == 0


class TestRunSchedulerOnceExtended:
    """Extended tests for run_scheduler_once()."""

    def _create_job(self, db, job_id=1):
        job = Job(
            id=job_id,
            user_id=1,
            name=f"Sched Job {job_id}",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
            is_active=True,
        )
        db.add(job)
        db.commit()
        return job

    def test_multiple_due_schedules(self, db, fake_redis):
        """Multiple due schedules should all be processed in one call."""
        for i in range(1, 4):
            job = self._create_job(db, job_id=i)
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
        assert fake_redis.llen("queue:ready:medium") == 3
        assert db.query(Execution).count() == 3

    def test_batch_size_limit(self, db, fake_redis):
        """batch_size should limit how many schedules are processed."""
        for i in range(1, 6):
            job = self._create_job(db, job_id=i)
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
            processed = run_scheduler_once(db, batch_size=2)

        assert processed == 2

    def test_skips_completed_schedule(self, db, fake_redis):
        """Completed schedules should not be picked up."""
        job = self._create_job(db)
        schedule = Schedule(
            job_id=job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.COMPLETED,
            run_count=5,
            max_runs=5,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 0

    def test_increments_run_count(self, db, fake_redis):
        """run_count should increment after each execution."""
        job = self._create_job(db)
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
            run_scheduler_once(db)

        db.refresh(schedule)
        assert schedule.run_count == 1

    def test_sets_last_run_at(self, db, fake_redis):
        """last_run_at should be set after processing."""
        job = self._create_job(db)
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
            run_scheduler_once(db)

        db.refresh(schedule)
        assert schedule.last_run_at is not None

    def test_redis_payload_format(self, db, fake_redis):
        """Verify the Redis payload contains execution_id and job_id."""
        job = self._create_job(db)
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
            run_scheduler_once(db)

        items = fake_redis.lrange("queue:ready:medium", 0, -1)
        payload = json.loads(items[0])
        assert "execution_id" in payload
        assert "job_id" in payload
        assert payload["job_id"] == job.id

    def test_no_schedules_returns_zero(self, db, fake_redis):
        """Empty database should return 0 processed."""
        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 0

    def test_unlimited_runs(self, db, fake_redis):
        """Schedule with max_runs=None should continue running."""
        job = self._create_job(db)
        schedule = Schedule(
            job_id=job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.ACTIVE,
            max_runs=None,
            run_count=100,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            run_scheduler_once(db)

        db.refresh(schedule)
        assert schedule.status == ScheduleStatus.ACTIVE
        assert schedule.run_count == 101
