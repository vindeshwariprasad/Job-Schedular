"""Comprehensive tests for all database models: User, Job, Schedule, Execution, RetryPolicy, DeadLetterJob."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from db.models.user import User
from db.models.job import Job
from db.models.schedule import Schedule, ScheduleStatus
from db.models.execution import Execution, ExecutionStatus
from db.models.retry_policy import RetryPolicy
from db.models.dead_letter import DeadLetterJob


# ── User Model ────────────────────────────────────

class TestUserModel:

    def test_create_user(self, db):
        user = User(username="testuser", email="test@example.com", hashed_password="hashedpw")
        db.add(user)
        db.commit()
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    def test_user_unique_username(self, db):
        user1 = User(username="unique", email="a@example.com", hashed_password="hash1")
        user2 = User(username="unique", email="b@example.com", hashed_password="hash2")
        db.add(user1)
        db.commit()
        db.add(user2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_user_unique_email(self, db):
        user1 = User(username="user1", email="same@example.com", hashed_password="hash1")
        user2 = User(username="user2", email="same@example.com", hashed_password="hash2")
        db.add(user1)
        db.commit()
        db.add(user2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_user_tablename(self):
        assert User.__tablename__ == "users"

    def test_user_query(self, db):
        user = User(username="queryuser", email="q@example.com", hashed_password="hash")
        db.add(user)
        db.commit()
        found = db.query(User).filter(User.username == "queryuser").first()
        assert found is not None
        assert found.email == "q@example.com"


# ── Job Model ─────────────────────────────────────

class TestJobModel:

    def test_create_job(self, db):
        job = Job(
            user_id=1,
            name="Test Job",
            task_type="api_call",
            payload={"url": "https://example.com"},
            rate_limit_per_min=60,
        )
        db.add(job)
        db.commit()
        assert job.id is not None
        assert job.name == "Test Job"
        assert job.is_active is True  # default

    def test_job_defaults(self, db):
        job = Job(user_id=1, name="Default Job", task_type="math", payload={"expression": "1+1"})
        db.add(job)
        db.commit()
        assert job.rate_limit_per_min == 60
        assert job.is_active is True

    def test_job_inactive(self, db):
        job = Job(
            user_id=1,
            name="Inactive Job",
            task_type="api_call",
            payload={},
            is_active=False,
        )
        db.add(job)
        db.commit()
        assert job.is_active is False

    def test_job_json_payload(self, db):
        payload = {"url": "https://api.example.com", "method": "POST", "body": {"key": "value"}}
        job = Job(user_id=1, name="JSON Job", task_type="api_call", payload=payload)
        db.add(job)
        db.commit()
        db.refresh(job)
        assert job.payload["method"] == "POST"
        assert job.payload["body"]["key"] == "value"

    def test_job_tablename(self):
        assert Job.__tablename__ == "jobs"

    def test_job_foreign_key_user(self):
        cols = {c.name: c for c in Job.__table__.columns}
        fks = list(cols["user_id"].foreign_keys)
        assert len(fks) == 1
        assert "users.id" in str(fks[0].target_fullname)


# ── Schedule Model ────────────────────────────────

class TestScheduleModel:

    def test_create_schedule(self, db, sample_job):
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/5 * * * *",
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        db.commit()
        assert schedule.id is not None
        assert schedule.status == "active"

    def test_schedule_status_constants(self):
        assert ScheduleStatus.ACTIVE == "active"
        assert ScheduleStatus.PAUSED == "paused"
        assert ScheduleStatus.COMPLETED == "completed"

    def test_schedule_max_runs_nullable(self, db, sample_job):
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="0 * * * *",
            status=ScheduleStatus.ACTIVE,
            run_count=0,
            max_runs=None,
        )
        db.add(schedule)
        db.commit()
        assert schedule.max_runs is None

    def test_schedule_with_next_run(self, db, sample_job):
        now = datetime.now(timezone.utc)
        schedule = Schedule(
            job_id=sample_job.id,
            cron_expression="*/10 * * * *",
            next_run_at=now,
            status=ScheduleStatus.ACTIVE,
            run_count=5,
        )
        db.add(schedule)
        db.commit()
        assert schedule.next_run_at is not None
        assert schedule.run_count == 5

    def test_schedule_tablename(self):
        assert Schedule.__tablename__ == "schedules"


# ── Execution Model ──────────────────────────────

class TestExecutionModel:

    def test_create_execution(self, db, sample_job):
        execution = Execution(
            job_id=sample_job.id,
            execution_id="exec-001",
            status=ExecutionStatus.PENDING,
            attempt=1,
        )
        db.add(execution)
        db.commit()
        assert execution.id is not None
        assert execution.status == ExecutionStatus.PENDING

    def test_execution_status_enum(self):
        assert ExecutionStatus.PENDING == "PENDING"
        assert ExecutionStatus.RUNNING == "RUNNING"
        assert ExecutionStatus.SUCCESS == "SUCCESS"
        assert ExecutionStatus.FAILED == "FAILED"

    def test_execution_terminal_states(self):
        terminal = ExecutionStatus.terminal_states()
        assert ExecutionStatus.SUCCESS in terminal
        assert ExecutionStatus.FAILED in terminal
        assert ExecutionStatus.PENDING not in terminal
        assert ExecutionStatus.RUNNING not in terminal

    def test_execution_status_is_string_enum(self):
        assert isinstance(ExecutionStatus.PENDING, str)
        assert ExecutionStatus.PENDING == "PENDING"

    def test_execution_with_timestamps(self, db, sample_job):
        now = datetime.now(timezone.utc)
        execution = Execution(
            job_id=sample_job.id,
            execution_id="exec-002",
            status=ExecutionStatus.SUCCESS,
            attempt=1,
            started_at=now,
            finished_at=now,
        )
        db.add(execution)
        db.commit()
        assert execution.started_at is not None
        assert execution.finished_at is not None

    def test_execution_with_error(self, db, sample_job):
        execution = Execution(
            job_id=sample_job.id,
            execution_id="exec-003",
            status=ExecutionStatus.FAILED,
            attempt=3,
            error="Connection timeout",
        )
        db.add(execution)
        db.commit()
        assert execution.error == "Connection timeout"

    def test_execution_unique_execution_id(self, db, sample_job):
        ex1 = Execution(job_id=sample_job.id, execution_id="same-id", status=ExecutionStatus.PENDING, attempt=1)
        ex2 = Execution(job_id=sample_job.id, execution_id="same-id", status=ExecutionStatus.PENDING, attempt=1)
        db.add(ex1)
        db.commit()
        db.add(ex2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_execution_tablename(self):
        assert Execution.__tablename__ == "executions"


# ── RetryPolicy Model ────────────────────────────

class TestRetryPolicyModel:

    def test_create_retry_policy(self, db, sample_job):
        policy = RetryPolicy(
            job_id=sample_job.id,
            max_retries=5,
            base_delay_seconds=10,
        )
        db.add(policy)
        db.commit()
        assert policy.max_retries == 5
        assert policy.base_delay_seconds == 10

    def test_retry_policy_defaults(self, db, sample_job):
        policy = RetryPolicy(job_id=sample_job.id)
        db.add(policy)
        db.commit()
        assert policy.max_retries == 3
        assert policy.base_delay_seconds == 30

    def test_retry_policy_tablename(self):
        assert RetryPolicy.__tablename__ == "retry_policies"

    def test_retry_policy_primary_key_is_job_id(self):
        pk_cols = [c.name for c in RetryPolicy.__table__.primary_key.columns]
        assert pk_cols == ["job_id"]


# ── DeadLetterJob Model ──────────────────────────

class TestDeadLetterJobModel:

    def test_create_dlq_entry(self, db):
        dlq = DeadLetterJob(
            job_id=1,
            execution_id="dlq-exec-001",
            payload={"job_id": 1, "execution_id": "dlq-exec-001"},
            error="Max retries exceeded",
        )
        db.add(dlq)
        db.commit()
        assert dlq.id is not None
        assert dlq.error == "Max retries exceeded"

    def test_dlq_json_payload(self, db):
        payload = {"job_id": 1, "execution_id": "dlq-002", "extra": "data"}
        dlq = DeadLetterJob(job_id=1, execution_id="dlq-002", payload=payload, error="fail")
        db.add(dlq)
        db.commit()
        db.refresh(dlq)
        assert dlq.payload["extra"] == "data"

    def test_dlq_tablename(self):
        assert DeadLetterJob.__tablename__ == "dead_letter_jobs"

    def test_dlq_query_by_execution_id(self, db):
        dlq = DeadLetterJob(job_id=1, execution_id="findme-001", payload={}, error="err")
        db.add(dlq)
        db.commit()
        found = db.query(DeadLetterJob).filter(DeadLetterJob.execution_id == "findme-001").first()
        assert found is not None
        assert found.job_id == 1
