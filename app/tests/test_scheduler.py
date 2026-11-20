"""Tests for scheduler logic: scheduling due jobs, max_runs, skipping paused schedules."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from db.models.execution import Execution, ExecutionStatus
from db.models.schedule import Schedule, ScheduleStatus

# We patch redis_client at the module level where scheduler imports it
REDIS_PATCH = "scheduler.scheduler.redis_client"


class TestRunSchedulerOnce:
    """Tests for run_scheduler_once()."""

    def test_creates_execution_for_due_schedule(self, db, sample_job, fake_redis):
        """A schedule whose next_run_at is in the past should produce an execution."""
        schedule = Schedule(
            job_id=sample_job.id,
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
        execution = db.query(Execution).first()
        assert execution is not None
        assert execution.job_id == sample_job.id
        assert execution.status == ExecutionStatus.PENDING

        # Verify it was pushed to Redis
        assert fake_redis.llen("queue:ready") == 1

    def test_skips_paused_schedule(self, db, sample_job, fake_redis):
        """Paused schedules should not be picked up."""
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.PAUSED,
            run_count=0,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 0
        assert db.query(Execution).count() == 0

    def test_skips_future_schedule(self, db, sample_job, fake_redis):
        """A schedule whose next_run_at is in the future should not fire."""
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) + timedelta(hours=1),
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(db)

        assert processed == 0

    def test_max_runs_marks_completed(self, db, sample_job, fake_redis):
        """When run_count reaches max_runs, schedule should become COMPLETED."""
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
            status=ScheduleStatus.ACTIVE,
            max_runs=3,
            run_count=2,  # next run will be the 3rd
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            run_scheduler_once(db)

        db.refresh(schedule)
        assert schedule.status == ScheduleStatus.COMPLETED
        assert schedule.next_run_at is None
        assert schedule.run_count == 3

    def test_updates_next_run_at(self, db, sample_job, fake_redis):
        """After processing, next_run_at should advance to the next cron tick."""
        past = datetime.now(UTC) - timedelta(minutes=1)
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/5 * * * *",
            next_run_at=past,
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        db.commit()

        with patch(REDIS_PATCH, fake_redis):
            from scheduler.scheduler import run_scheduler_once
            run_scheduler_once(db)

        db.refresh(schedule)
        assert schedule.next_run_at is not None
        # croniter may return naive datetime; strip tzinfo for comparison
        next_run = schedule.next_run_at.replace(tzinfo=None) if schedule.next_run_at.tzinfo else schedule.next_run_at
        past_naive = past.replace(tzinfo=None)
        assert next_run > past_naive
        assert schedule.run_count == 1
