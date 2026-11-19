"""Extended tests for admin DLQ API endpoints: queue details, pagination, filtering, stats with data."""

import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.base import Base
from db.models.user import User
from db.models.job import Job
from db.models.execution import Execution, ExecutionStatus
from db.models.dead_letter import DeadLetterJob
from tests.conftest import FakeRedis


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

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
def test_redis():
    return FakeRedis()


@pytest.fixture
def client(test_db):
    from unittest.mock import patch
    from main import app
    from db.session import get_db
    from tests.async_test_helpers import SyncToAsyncSessionWrapper

    async def override_get_db():
        yield SyncToAsyncSessionWrapper(test_db)

    app.dependency_overrides[get_db] = override_get_db
    # Bypass Redis-based auth rate limiting in tests (no live Redis)
    with patch("api.auth.is_rate_limited", return_value=False):
        c = TestClient(app)
        yield c
    app.dependency_overrides.clear()


def _register(client, username="dlquser", email="dlq@example.com"):
    resp = client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": "TestPass1",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestQueueDetails:

    def test_returns_all_queues(self, client, test_redis):
        headers = _register(client)
        with patch("api.admin_dlq.redis_client", test_redis):
            resp = client.get("/api/v1/admin/dlq/queues/details", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "processing" in data
        assert "failed" in data

    def test_returns_queue_counts(self, client, test_redis):
        headers = _register(client)
        test_redis.lpush("queue:ready", json.dumps({"execution_id": "e1", "job_id": 1}))
        test_redis.lpush("queue:ready", json.dumps({"execution_id": "e2", "job_id": 2}))
        test_redis.lpush("queue:processing", json.dumps({"execution_id": "e3", "job_id": 1}))

        with patch("api.admin_dlq.redis_client", test_redis):
            resp = client.get("/api/v1/admin/dlq/queues/details", headers=headers)

        data = resp.json()
        assert data["ready"]["count"] == 2
        assert data["processing"]["count"] == 1
        assert data["failed"]["count"] == 0

    def test_returns_parsed_items(self, client, test_redis):
        headers = _register(client)
        test_redis.lpush("queue:ready", json.dumps({"execution_id": "e1", "job_id": 1}))

        with patch("api.admin_dlq.redis_client", test_redis):
            resp = client.get("/api/v1/admin/dlq/queues/details", headers=headers)

        items = resp.json()["ready"]["items"]
        assert len(items) == 1
        assert items[0]["execution_id"] == "e1"

    def test_handles_unparseable_items(self, client, test_redis):
        headers = _register(client)
        test_redis.lpush("queue:ready", "not-json")

        with patch("api.admin_dlq.redis_client", test_redis):
            resp = client.get("/api/v1/admin/dlq/queues/details", headers=headers)

        items = resp.json()["ready"]["items"]
        assert len(items) == 1
        assert "raw" in items[0]


class TestQueueStats:

    def test_returns_queue_sizes(self, client, test_redis):
        headers = _register(client)
        test_redis.lpush("queue:ready", "a")
        test_redis.lpush("queue:failed", "b", "c")

        with patch("api.admin_dlq.redis_client", test_redis):
            resp = client.get("/api/v1/admin/dlq/queues", headers=headers)

        data = resp.json()
        assert data["ready"] == 1
        assert data["processing"] == 0
        assert data["failed"] == 2

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/admin/dlq/queues")
        assert resp.status_code in (401, 403)


class TestDLQListPagination:

    def test_pagination_params(self, client, test_db):
        headers = _register(client)

        # Create job and DLQ entries
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="PagJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        for i in range(5):
            dlq = DeadLetterJob(
                job_id=job.id,
                execution_id=f"dlq-page-{i}",
                payload={},
                error=f"Error {i}",
            )
            test_db.add(dlq)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/?page=1&size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["size"] == 2

    def test_page_2(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="PagJob2", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        for i in range(5):
            dlq = DeadLetterJob(job_id=job.id, execution_id=f"dlq-p2-{i}", payload={}, error=f"E{i}")
            test_db.add(dlq)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/?page=2&size=2", headers=headers)
        data = resp.json()
        assert len(data["items"]) == 2

    def test_empty_dlq(self, client):
        headers = _register(client)
        resp = client.get("/api/v1/admin/dlq/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestExecutionsFilter:

    def test_filter_by_status(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="FilterJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        # Add executions with different statuses
        for status, exec_id in [
            (ExecutionStatus.SUCCESS, "s1"),
            (ExecutionStatus.SUCCESS, "s2"),
            (ExecutionStatus.FAILED, "f1"),
            (ExecutionStatus.PENDING, "p1"),
        ]:
            ex = Execution(job_id=job.id, execution_id=exec_id, status=status, attempt=1)
            test_db.add(ex)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/executions?status=SUCCESS", headers=headers)
        data = resp.json()
        assert data["total"] == 2

    def test_no_filter_returns_all(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="AllJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        for i in range(3):
            ex = Execution(job_id=job.id, execution_id=f"all-{i}", status=ExecutionStatus.SUCCESS, attempt=1)
            test_db.add(ex)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/executions", headers=headers)
        data = resp.json()
        assert data["total"] == 3

    def test_executions_pagination(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="PagExecJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        for i in range(10):
            ex = Execution(job_id=job.id, execution_id=f"pag-{i}", status=ExecutionStatus.SUCCESS, attempt=1)
            test_db.add(ex)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/executions?page=1&size=3", headers=headers)
        data = resp.json()
        assert data["total"] == 10
        assert len(data["items"]) == 3


class TestUserStatsWithData:

    def test_user_stats_with_executions(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="StatsJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        # Add executions
        import uuid
        for status in [ExecutionStatus.SUCCESS, ExecutionStatus.SUCCESS, ExecutionStatus.FAILED]:
            ex = Execution(
                job_id=job.id,
                execution_id=f"stats-{uuid.uuid4().hex[:12]}",
                status=status,
                attempt=1,
            )
            test_db.add(ex)

        # Add DLQ entry
        dlq = DeadLetterJob(job_id=job.id, execution_id="dlq-stats", payload={}, error="err")
        test_db.add(dlq)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/user-stats", headers=headers)
        data = resp.json()
        assert data["total_executions"] == 3
        assert data["success"] == 2
        assert data["failed"] == 1
        assert data["dlq"] == 1


class TestGlobalStats:

    def test_global_stats_returns_counts(self, client, test_db):
        headers = _register(client)
        resp = client.get("/api/v1/admin/dlq/global-stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_executions" in data
        assert "success" in data
        assert "failed" in data
        assert "dlq" in data


class TestExecutionHistory:

    def test_returns_list(self, client):
        headers = _register(client)
        resp = client.get("/api/v1/admin/dlq/execution-history", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_grouped_by_date(self, client, test_db):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="HistJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        ex = Execution(job_id=job.id, execution_id="hist-1", status=ExecutionStatus.SUCCESS, attempt=1)
        test_db.add(ex)
        test_db.commit()

        resp = client.get("/api/v1/admin/dlq/execution-history", headers=headers)
        data = resp.json()
        if len(data) > 0:
            assert "date" in data[0]
            assert "total" in data[0]
            assert "success" in data[0]
            assert "failed" in data[0]


class TestReplayEndpoint:

    def test_replay_not_found(self, client, test_redis):
        headers = _register(client)
        with patch("api.admin_dlq.redis_client", test_redis), \
             patch("services.dlq_service.redis_client", test_redis):
            resp = client.post("/api/v1/admin/dlq/nonexistent-id/replay", headers=headers)
        assert resp.status_code == 404

    def test_replay_success(self, client, test_db, test_redis):
        headers = _register(client)
        user = test_db.query(User).first()
        job = Job(user_id=user.id, name="ReplayJob", task_type="api_call", payload={})
        test_db.add(job)
        test_db.commit()

        dlq = DeadLetterJob(
            job_id=job.id,
            execution_id="replay-exec-001",
            payload={"job_id": job.id},
            error="failed",
        )
        test_db.add(dlq)
        test_db.commit()

        with patch("api.admin_dlq.redis_client", test_redis), \
             patch("services.dlq_service.redis_client", test_redis):
            resp = client.post("/api/v1/admin/dlq/replay-exec-001/replay", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "replayed"
        assert data["old_execution_id"] == "replay-exec-001"

    def test_replay_requires_auth(self, client):
        resp = client.post("/api/v1/admin/dlq/some-id/replay")
        assert resp.status_code in (401, 403)
