"""
Integration test: Full job lifecycle.

Register → Create Job → Schedule → Scheduler enqueues → Worker executes → Verify SUCCESS

Uses FastAPI TestClient + direct function calls to scheduler/worker,
all against in-memory SQLite + FakeRedis. No external services needed.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from db.base import Base
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.schedule import Schedule, ScheduleStatus
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Fixtures ─────────────────────────────────────────

@pytest.fixture
def integration_db():
    """In-memory SQLite shared across threads via StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    # SQLite doesn't support FOR UPDATE — make it a no-op
    @event.listens_for(engine, "before_cursor_execute")
    def _strip_for_update(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            statement = statement.replace(" FOR UPDATE", "")
            return statement, parameters

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def integration_redis():
    """Import FakeRedis from conftest."""
    from tests.conftest import FakeRedis
    return FakeRedis()


@pytest.fixture
def app_client(integration_db):
    """FastAPI TestClient with DB dependency overridden (async wrapper)."""
    from unittest.mock import patch

    from db.session import get_db
    from main import app

    from tests.async_test_helpers import SyncToAsyncSessionWrapper

    async def override_get_db():
        yield SyncToAsyncSessionWrapper(integration_db)

    app.dependency_overrides[get_db] = override_get_db
    # Bypass Redis-based auth rate limiting in integration tests (no live Redis)
    with patch("api.auth.is_rate_limited", return_value=False):
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────

def register_and_get_token(client: TestClient) -> str:
    """Register a test user and return the JWT token."""
    resp = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPass123",
    })
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Tests ────────────────────────────────────────────

class TestFullJobLifecycle:
    """End-to-end test: job creation → scheduling → execution → success."""

    def test_job_lifecycle_happy_path(self, app_client, integration_db, integration_redis):
        """
        1. Register user via API
        2. Create a job via API
        3. Create a schedule via API
        4. Run scheduler — should create an Execution and enqueue to Redis
        5. Run worker processing — should mark execution SUCCESS
        """
        # ── Step 1: Register ──
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        # ── Step 2: Create Job ──
        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Integration Test Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
            "rate_limit_per_min": 60,
        }, headers=headers)
        assert job_resp.status_code == 200
        job_id = job_resp.json()["id"]

        # ── Step 3: Schedule (every 1 minute, 1 run max) ──
        sched_resp = app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/1 * * * *",
            "max_runs": 1,
        }, headers=headers)
        assert sched_resp.status_code == 200
        assert sched_resp.json()["status"] == "active"

        # Manually set next_run_at to the past so scheduler picks it up
        schedule = integration_db.query(Schedule).filter(Schedule.job_id == job_id).first()
        schedule.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        integration_db.commit()

        # ── Step 4: Run Scheduler ──
        with patch("scheduler.scheduler.redis_client", integration_redis):
            from scheduler.scheduler import run_scheduler_once
            processed = run_scheduler_once(integration_db)

        assert processed == 1, "Scheduler should have processed 1 schedule"

        # Verify execution was created
        execution = integration_db.query(Execution).filter(Execution.job_id == job_id).first()
        assert execution is not None
        assert execution.status == ExecutionStatus.PENDING
        execution_id = execution.execution_id

        # Verify enqueued to Redis
        assert integration_redis.llen("queue:ready:medium") == 1

        # Verify schedule completed (max_runs=1)
        integration_db.refresh(schedule)
        assert schedule.status == ScheduleStatus.COMPLETED
        assert schedule.run_count == 1

        # ── Step 5: Run Worker ──
        with patch("worker.worker.execute_job", return_value={"status": "no_op"}), \
             patch("worker.worker.is_rate_limited", return_value=False):
            from worker.worker import process_execution
            process_execution(integration_db, integration_redis, execution_id)

        # Verify execution is SUCCESS
        integration_db.refresh(execution)
        assert execution.status == ExecutionStatus.SUCCESS
        assert execution.finished_at is not None

    def test_job_lifecycle_failure_to_dlq(self, app_client, integration_db, integration_redis):
        """
        Test the failure path:
        1. Create job + schedule
        2. Scheduler enqueues
        3. Worker fails → retries → exceeds max → lands in DLQ
        """
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        # Create job
        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Failing Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
            "rate_limit_per_min": 60,
        }, headers=headers)
        job_id = job_resp.json()["id"]

        # Create schedule
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/1 * * * *",
            "max_runs": 1,
        }, headers=headers)

        # Set next_run_at to past
        schedule = integration_db.query(Schedule).filter(Schedule.job_id == job_id).first()
        schedule.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        integration_db.commit()

        # Run scheduler
        with patch("scheduler.scheduler.redis_client", integration_redis):
            from scheduler.scheduler import run_scheduler_once
            run_scheduler_once(integration_db)

        execution = integration_db.query(Execution).filter(Execution.job_id == job_id).first()
        execution_id = execution.execution_id

        # Simulate repeated failures until DLQ
        # handle_failure increments attempt THEN checks attempt > max_retries
        # With max_retries=2: call1 → attempt=2 (retry), call2 → attempt=3 (DLQ)
        job = integration_db.query(Job).filter(Job.id == job_id).first()
        with patch("worker.worker.execute_job", side_effect=RuntimeError("API down")), \
             patch("worker.worker.is_rate_limited", return_value=False):
            from worker.worker import handle_failure

            # Attempt 1 → retry (attempt becomes 2, 2 <= 2 so retry)
            handle_failure(integration_db, integration_redis, execution, job, RuntimeError("API down"), max_retries=2, base_delay=0)
            assert execution.status == ExecutionStatus.PENDING
            assert execution.attempt == 2

            # Attempt 2 → DLQ (attempt becomes 3, 3 > 2 so DLQ)
            handle_failure(integration_db, integration_redis, execution, job, RuntimeError("API down"), max_retries=2, base_delay=0)
            assert execution.status == ExecutionStatus.FAILED

        # Verify DLQ entry exists
        from db.models.dead_letter import DeadLetterJob
        dlq = integration_db.query(DeadLetterJob).filter(
            DeadLetterJob.execution_id == execution_id
        ).first()
        assert dlq is not None
        assert "API down" in dlq.error

        # Verify it's in the failed queue
        assert integration_redis.llen("queue:failed") == 1

    def test_api_auth_required(self, app_client):
        """Verify that API endpoints reject unauthenticated requests."""
        resp = app_client.get("/api/v1/jobs")
        assert resp.status_code in (401, 403)

        resp = app_client.post("/api/v1/jobs", json={
            "name": "Test",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        })
        assert resp.status_code in (401, 403)


# ── Auth Integration Tests ──────────────────────────

class TestAuthIntegration:
    """Test auth flows: register, login, duplicate prevention, token validation."""

    def test_register_returns_token_and_user(self, app_client):
        resp = app_client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "SecurePass1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "newuser"
        assert data["user"]["email"] == "new@example.com"

    def test_register_duplicate_username_rejected(self, app_client):
        app_client.post("/api/v1/auth/register", json={
            "username": "dupeuser",
            "email": "first@example.com",
            "password": "TestPass1",
        })
        resp = app_client.post("/api/v1/auth/register", json={
            "username": "dupeuser",
            "email": "second@example.com",
            "password": "TestPass1",
        })
        assert resp.status_code == 409

    def test_register_duplicate_email_rejected(self, app_client):
        app_client.post("/api/v1/auth/register", json={
            "username": "user_a",
            "email": "same@example.com",
            "password": "TestPass1",
        })
        resp = app_client.post("/api/v1/auth/register", json={
            "username": "user_b",
            "email": "same@example.com",
            "password": "TestPass1",
        })
        assert resp.status_code == 409

    def test_login_success(self, app_client):
        app_client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "MyPassword1",
        })
        resp = app_client.post("/api/v1/auth/login", json={
            "username": "loginuser",
            "password": "MyPassword1",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, app_client):
        app_client.post("/api/v1/auth/register", json={
            "username": "wrongpw",
            "email": "wp@example.com",
            "password": "Correct123",
        })
        resp = app_client.post("/api/v1/auth/login", json={
            "username": "wrongpw",
            "password": "Incorrect1",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, app_client):
        resp = app_client.post("/api/v1/auth/login", json={
            "username": "ghost",
            "password": "NopePass1",
        })
        assert resp.status_code == 401

    def test_me_endpoint(self, app_client):
        token = register_and_get_token(app_client)
        resp = app_client.get("/api/v1/auth/me", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    def test_invalid_token_rejected(self, app_client):
        resp = app_client.get("/api/v1/jobs", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code in (401, 403)


# ── Job CRUD Integration Tests ──────────────────────

class TestJobCRUDIntegration:
    """Test job creation, listing, retrieval, and deletion via API."""

    def _register(self, client, username="jobuser", email="job@example.com"):
        resp = client.post("/api/v1/auth/register", json={
            "username": username,
            "email": email,
            "password": "TestPass1",
        })
        return auth_headers(resp.json()["access_token"])

    def test_create_and_list_jobs(self, app_client):
        headers = self._register(app_client)

        # Create two jobs
        app_client.post("/api/v1/jobs", json={
            "name": "Job A",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
            "rate_limit_per_min": 30,
        }, headers=headers)
        app_client.post("/api/v1/jobs", json={
            "name": "Job B",
            "task_type": "string_manipulation",
            "payload": {"input": "hello world"},
        }, headers=headers)

        resp = app_client.get("/api/v1/jobs", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        jobs = data["items"]
        assert len(jobs) == 2
        names = {j["name"] for j in jobs}
        assert names == {"Job A", "Job B"}

    def test_get_single_job(self, app_client):
        headers = self._register(app_client)
        create_resp = app_client.post("/api/v1/jobs", json={
            "name": "Single Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        job_id = create_resp.json()["id"]

        resp = app_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Single Job"

    def test_get_nonexistent_job_404(self, app_client):
        headers = self._register(app_client)
        resp = app_client.get("/api/v1/jobs/99999", headers=headers)
        assert resp.status_code == 404

    def test_delete_job(self, app_client):
        headers = self._register(app_client)
        create_resp = app_client.post("/api/v1/jobs", json={
            "name": "Delete Me",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        job_id = create_resp.json()["id"]

        del_resp = app_client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
        assert del_resp.status_code == 204

        get_resp = app_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert get_resp.status_code == 404

    def test_delete_nonexistent_job_404(self, app_client):
        headers = self._register(app_client)
        resp = app_client.delete("/api/v1/jobs/99999", headers=headers)
        assert resp.status_code == 404

    def test_create_job_validates_payload(self, app_client):
        headers = self._register(app_client)
        resp = app_client.post("/api/v1/jobs", json={
            "name": "",  # empty name violates min_length=1
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        assert resp.status_code == 422


# ── Schedule Integration Tests ──────────────────────

class TestScheduleIntegration:
    """Test schedule creation, pause, resume, delete via API."""

    def _setup(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "username": "scheduser",
            "email": "sched@example.com",
            "password": "TestPass1",
        })
        headers = auth_headers(resp.json()["access_token"])

        job_resp = client.post("/api/v1/jobs", json={
            "name": "Sched Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        job_id = job_resp.json()["id"]
        return headers, job_id

    def test_create_schedule(self, app_client):
        headers, job_id = self._setup(app_client)
        resp = app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/10 * * * *",
            "max_runs": 5,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["cron_expression"] == "*/10 * * * *"
        assert data["max_runs"] == 5
        assert data["run_count"] == 0

    def test_duplicate_schedule_rejected(self, app_client):
        headers, job_id = self._setup(app_client)
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)

        resp = app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/10 * * * *",
        }, headers=headers)
        assert resp.status_code == 409

    def test_invalid_cron_rejected(self, app_client):
        headers, job_id = self._setup(app_client)
        resp = app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "not a cron",
        }, headers=headers)
        assert resp.status_code == 400

    def test_pause_and_resume_schedule(self, app_client):
        headers, job_id = self._setup(app_client)
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)

        # Pause
        resp = app_client.patch(f"/api/v1/jobs/{job_id}/schedule/pause", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Resume
        resp = app_client.patch(f"/api/v1/jobs/{job_id}/schedule/resume", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_resume_non_paused_rejected(self, app_client):
        headers, job_id = self._setup(app_client)
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)

        # Try to resume an already-active schedule
        resp = app_client.patch(f"/api/v1/jobs/{job_id}/schedule/resume", headers=headers)
        assert resp.status_code == 400

    def test_delete_schedule(self, app_client):
        headers, job_id = self._setup(app_client)
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)

        resp = app_client.delete(f"/api/v1/jobs/{job_id}/schedule", headers=headers)
        assert resp.status_code == 204

        resp = app_client.get(f"/api/v1/jobs/{job_id}/schedule", headers=headers)
        assert resp.status_code == 404

    def test_schedule_for_nonexistent_job_404(self, app_client):
        resp = app_client.post("/api/v1/auth/register", json={
            "username": "scheduser2",
            "email": "sched2@example.com",
            "password": "TestPass1",
        })
        headers = auth_headers(resp.json()["access_token"])
        resp = app_client.post("/api/v1/jobs/99999/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)
        assert resp.status_code == 404


# ── Multi-User Isolation Tests ──────────────────────

class TestMultiUserIsolation:
    """Verify that users cannot see or modify each other's jobs."""

    def test_user_cannot_see_other_users_jobs(self, app_client):
        # Register user A
        resp_a = app_client.post("/api/v1/auth/register", json={
            "username": "user_alpha",
            "email": "alpha@example.com",
            "password": "TestPass1",
        })
        headers_a = auth_headers(resp_a.json()["access_token"])

        # Register user B
        resp_b = app_client.post("/api/v1/auth/register", json={
            "username": "user_beta",
            "email": "beta@example.com",
            "password": "TestPass1",
        })
        headers_b = auth_headers(resp_b.json()["access_token"])

        # User A creates a job
        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Alpha's Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers_a)
        job_id = job_resp.json()["id"]

        # User B should not see it
        resp = app_client.get("/api/v1/jobs", headers=headers_b)
        assert len(resp.json()["items"]) == 0

        # User B should get 404 trying to access it directly
        resp = app_client.get(f"/api/v1/jobs/{job_id}", headers=headers_b)
        assert resp.status_code == 404

    def test_user_cannot_delete_other_users_jobs(self, app_client):
        resp_a = app_client.post("/api/v1/auth/register", json={
            "username": "owner",
            "email": "owner@example.com",
            "password": "TestPass1",
        })
        headers_a = auth_headers(resp_a.json()["access_token"])

        resp_b = app_client.post("/api/v1/auth/register", json={
            "username": "attacker",
            "email": "attacker@example.com",
            "password": "TestPass1",
        })
        headers_b = auth_headers(resp_b.json()["access_token"])

        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Owner's Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers_a)
        job_id = job_resp.json()["id"]

        # User B tries to delete User A's job
        resp = app_client.delete(f"/api/v1/jobs/{job_id}", headers=headers_b)
        assert resp.status_code == 404

        # Job should still exist for User A
        resp = app_client.get(f"/api/v1/jobs/{job_id}", headers=headers_a)
        assert resp.status_code == 200


# ── DLQ Replay Integration Test ─────────────────────

class TestDLQReplayIntegration:
    """Test the full failure → DLQ → replay → success cycle."""

    def test_dlq_replay_creates_new_execution(self, app_client, integration_db, integration_redis):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        # Create job
        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Replay Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        job_id = job_resp.json()["id"]

        # Create schedule and trigger
        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/1 * * * *",
            "max_runs": 1,
        }, headers=headers)

        schedule = integration_db.query(Schedule).filter(Schedule.job_id == job_id).first()
        schedule.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        integration_db.commit()

        with patch("scheduler.scheduler.redis_client", integration_redis):
            from scheduler.scheduler import run_scheduler_once
            run_scheduler_once(integration_db)

        execution = integration_db.query(Execution).filter(Execution.job_id == job_id).first()
        execution_id = execution.execution_id

        # Fail to DLQ
        job = integration_db.query(Job).filter(Job.id == job_id).first()
        with patch("worker.worker.execute_job", side_effect=RuntimeError("down")), \
             patch("worker.worker.is_rate_limited", return_value=False):
            from worker.worker import handle_failure
            handle_failure(integration_db, integration_redis, execution, job, RuntimeError("down"), max_retries=1, base_delay=0)

        assert execution.status == ExecutionStatus.FAILED

        # Replay via DLQ service (async function — wrap sync session)
        import asyncio

        from tests.async_test_helpers import SyncToAsyncSessionWrapper

        async def _replay():
            with patch("services.dlq_service.redis_client", integration_redis):
                from services.dlq_service import replay_dlq_execution
                return await replay_dlq_execution(
                    SyncToAsyncSessionWrapper(integration_db), execution_id
                )

        result = asyncio.run(_replay())

        assert result["status"] == "replayed"
        assert result["new_execution_id"] != execution_id

        # Verify new execution exists
        new_exec = integration_db.query(Execution).filter(
            Execution.execution_id == result["new_execution_id"]
        ).first()
        assert new_exec is not None
        assert new_exec.status == ExecutionStatus.PENDING

        # Process the replayed execution successfully
        with patch("worker.worker.execute_job", return_value={"ok": True}), \
             patch("worker.worker.is_rate_limited", return_value=False):
            from worker.worker import process_execution
            process_execution(integration_db, integration_redis, result["new_execution_id"])

        integration_db.refresh(new_exec)
        assert new_exec.status == ExecutionStatus.SUCCESS


# ── Stats & Admin Endpoint Tests ────────────────────

class TestStatsEndpoints:
    """Test the admin/DLQ stats endpoints return correct data."""

    def test_user_stats_empty(self, app_client):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        resp = app_client.get("/api/v1/admin/dlq/user-stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_executions"] == 0
        assert data["success"] == 0
        assert data["failed"] == 0
        assert data["dlq"] == 0

    def test_global_stats(self, app_client):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        resp = app_client.get("/api/v1/admin/dlq/global-stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_executions" in data
        assert "success" in data
        assert "failed" in data
        assert "dlq" in data

    def test_execution_history(self, app_client):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        resp = app_client.get("/api/v1/admin/dlq/execution-history", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_executions_list(self, app_client):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        resp = app_client.get("/api/v1/admin/dlq/executions", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_queue_stats(self, app_client, integration_redis):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        with patch("api.admin_dlq.redis_client", integration_redis):
            resp = app_client.get("/api/v1/admin/dlq/queues", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "ready_high" in data
        assert "ready_medium" in data
        assert "ready_low" in data
        assert "processing" in data
        assert "failed" in data


# ── Delete Job Cascade Test ─────────────────────────

class TestDeleteJobCascade:
    """Verify deleting a job removes schedules, executions, and DLQ entries."""

    def test_delete_cascades_related_records(self, app_client, integration_db):
        token = register_and_get_token(app_client)
        headers = auth_headers(token)

        # Create job + schedule
        job_resp = app_client.post("/api/v1/jobs", json={
            "name": "Cascade Job",
            "task_type": "api_call",
            "payload": {"url": "https://example.com"},
        }, headers=headers)
        job_id = job_resp.json()["id"]

        app_client.post(f"/api/v1/jobs/{job_id}/schedule", json={
            "cron_expression": "*/5 * * * *",
        }, headers=headers)

        # Add execution and DLQ entry directly to DB
        from db.models.dead_letter import DeadLetterJob
        ex = Execution(
            job_id=job_id,
            execution_id="cascade-test-001",
            status=ExecutionStatus.FAILED,
            attempt=3,
        )
        dlq = DeadLetterJob(
            job_id=job_id,
            execution_id="cascade-test-001",
            payload={"job_id": job_id},
            error="test error",
        )
        integration_db.add_all([ex, dlq])
        integration_db.commit()

        # Delete the job
        resp = app_client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 204

        # Verify all related records are gone
        assert integration_db.query(Schedule).filter(Schedule.job_id == job_id).count() == 0
        assert integration_db.query(Execution).filter(Execution.job_id == job_id).count() == 0
        assert integration_db.query(DeadLetterJob).filter(DeadLetterJob.job_id == job_id).count() == 0
