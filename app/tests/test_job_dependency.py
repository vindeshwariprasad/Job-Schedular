"""Tests for multi-parent job dependency DAG: validation, cycle detection, scheduler blocking, worker unblock, cascade delete."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from constants import QUEUE_READY_HIGH, QUEUE_READY_MEDIUM
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.job_dependency import JobDependency
from db.models.schedule import Schedule, ScheduleStatus
from services.dependency_service import (
    cascade_delete_job,
    check_parents_satisfied,
    detect_cycle,
    get_dependents_tree,
    sweep_blocked_executions,
    unblock_children,
    validate_dependencies_sync,
)

REDIS_PATCH = "scheduler.scheduler.redis_client"


# ------------------------------------
# Helpers
# ------------------------------------


def _make_job(db, job_id, user_id=1, priority="MEDIUM", is_active=True):
    job = Job(
        id=job_id,
        user_id=user_id,
        name=f"Job {job_id}",
        task_type="api_call",
        payload={"url": "https://example.com"},
        rate_limit_per_min=60,
        is_active=is_active,
        priority=priority,
    )
    db.add(job)
    db.commit()
    return job


def _make_dep(db, child_id, parent_id):
    dep = JobDependency(job_id=child_id, depends_on_job_id=parent_id)
    db.add(dep)
    db.commit()
    return dep


def _make_execution(db, job_id, status, exec_id=None):
    exec_id = exec_id or f"exec-{job_id}-{status.lower()}"
    execution = Execution(
        job_id=job_id,
        execution_id=exec_id,
        status=status,
        attempt=1,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC) if status in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED) else None,
    )
    db.add(execution)
    db.commit()
    return execution


# ------------------------------------
# TestValidateDependencies
# ------------------------------------


class TestValidateDependencies:
    def test_empty_list_valid(self, db):
        _make_job(db, 1)
        validate_dependencies_sync(db, 1, [])

    def test_valid_single_parent(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        validate_dependencies_sync(db, 1, [1])

    def test_valid_three_parents(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_job(db, 4)
        validate_dependencies_sync(db, 1, [1, 2, 3])

    def test_too_many_parents(self, db):
        for i in range(1, 6):
            _make_job(db, i)
        try:
            validate_dependencies_sync(db, 1, [1, 2, 3, 4])
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            assert "at most 3" in str(e)

    def test_duplicate_parent_ids(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        try:
            validate_dependencies_sync(db, 1, [1, 1])
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            assert "Duplicate" in str(e)

    def test_parent_not_found(self, db):
        _make_job(db, 1)
        try:
            validate_dependencies_sync(db, 1, [999])
            pytest.fail("Should have raised LookupError")
        except LookupError as e:
            assert "999" in str(e)

    def test_cross_user_parent(self, db):
        _make_job(db, 1, user_id=1)
        _make_job(db, 2, user_id=2)
        try:
            validate_dependencies_sync(db, 1, [2])
            pytest.fail("Should have raised PermissionError")
        except PermissionError as e:
            assert "another user" in str(e)

    def test_self_dependency_blocked(self, db):
        _make_job(db, 1)
        try:
            validate_dependencies_sync(db, 1, [1], exclude_job_id=1)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            assert "itself" in str(e)


# ------------------------------------
# TestDetectCycle
# ------------------------------------


class TestDetectCycle:
    def test_no_cycle_simple(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        assert detect_cycle(db, 2, [1]) is False

    def test_direct_cycle(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 1, 2)  # 1 depends on 2
        # Now trying to add 2 depends on 1 -> cycle
        assert detect_cycle(db, 2, [1]) is True

    def test_indirect_cycle(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 1, 2)  # 1 depends on 2
        _make_dep(db, 2, 3)  # 2 depends on 3
        # Trying: 3 depends on 1 -> cycle: 3->1->2->3
        assert detect_cycle(db, 3, [1]) is True

    def test_no_cycle_with_existing_deps(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 2, 1)  # 2 depends on 1
        # 3 depends on 2 -> no cycle (chain: 3->2->1)
        assert detect_cycle(db, 3, [2]) is False

    def test_multi_parent_cycle(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 2, 1)  # 2 depends on 1
        _make_dep(db, 3, 2)  # 3 depends on 2
        # 1 depends on [3] -> cycle
        assert detect_cycle(db, 1, [3]) is True

    def test_no_deps_no_cycle(self, db):
        _make_job(db, 1)
        assert detect_cycle(db, 1, []) is False


# ------------------------------------
# TestCheckParentsSatisfied
# ------------------------------------


class TestCheckParentsSatisfied:
    def test_no_deps_satisfied(self, db):
        _make_job(db, 1)
        assert check_parents_satisfied(db, 1) is True

    def test_single_parent_success(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        assert check_parents_satisfied(db, 2) is True

    def test_single_parent_failed(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.FAILED)
        assert check_parents_satisfied(db, 2) is False

    def test_single_parent_no_executions(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        assert check_parents_satisfied(db, 2) is False

    def test_multi_parent_all_success(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 3, 1)
        _make_dep(db, 3, 2)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        _make_execution(db, 2, ExecutionStatus.SUCCESS)
        assert check_parents_satisfied(db, 3) is True

    def test_multi_parent_one_failed(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 3, 1)
        _make_dep(db, 3, 2)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        _make_execution(db, 2, ExecutionStatus.FAILED)
        assert check_parents_satisfied(db, 3) is False

    def test_inactive_parent_not_satisfied(self, db):
        _make_job(db, 1, is_active=False)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        assert check_parents_satisfied(db, 2) is False

    def test_latest_terminal_matters(self, db):
        """If parent succeeded once but then failed, latest terminal = FAILED -> not satisfied."""
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        # Older success
        exec1 = _make_execution(db, 1, ExecutionStatus.SUCCESS, exec_id="exec-1-old")
        exec1.created_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
        # Newer failure
        _make_execution(db, 1, ExecutionStatus.FAILED, exec_id="exec-1-new")
        assert check_parents_satisfied(db, 2) is False


# ------------------------------------
# TestUnblockChildren
# ------------------------------------


class TestUnblockChildren:
    def test_unblock_single_child(self, db, fake_redis):
        parent = _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        blocked = _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2")

        count = unblock_children(db, fake_redis, parent.id)

        assert count == 1
        db.refresh(blocked)
        assert blocked.status == ExecutionStatus.PENDING
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 1

    def test_no_unblock_when_other_parent_unsatisfied(self, db, fake_redis):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 3, 1)
        _make_dep(db, 3, 2)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        # Job 2 has no SUCCESS execution
        _make_execution(db, 3, ExecutionStatus.BLOCKED, exec_id="blocked-3")

        count = unblock_children(db, fake_redis, 1)

        assert count == 0
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0

    def test_unblock_uses_correct_priority_queue(self, db, fake_redis):
        _make_job(db, 1)
        _make_job(db, 2, priority="HIGH")
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2")

        unblock_children(db, fake_redis, 1)

        assert fake_redis.llen(QUEUE_READY_HIGH) == 1
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0

    def test_no_children_returns_zero(self, db, fake_redis):
        _make_job(db, 1)
        count = unblock_children(db, fake_redis, 1)
        assert count == 0

    def test_unblock_multiple_blocked_executions(self, db, fake_redis):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2a")
        _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2b")

        count = unblock_children(db, fake_redis, 1)

        assert count == 2
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 2


# ------------------------------------
# TestSweepBlockedExecutions
# ------------------------------------


class TestSweepBlockedExecutions:
    def test_sweep_unblocks_satisfied(self, db, fake_redis):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)
        blocked = _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2")

        count = sweep_blocked_executions(db, fake_redis)

        assert count == 1
        db.refresh(blocked)
        assert blocked.status == ExecutionStatus.PENDING

    def test_sweep_leaves_unsatisfied(self, db, fake_redis):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        # No SUCCESS execution for parent
        blocked = _make_execution(db, 2, ExecutionStatus.BLOCKED, exec_id="blocked-2")

        count = sweep_blocked_executions(db, fake_redis)

        assert count == 0
        db.refresh(blocked)
        assert blocked.status == ExecutionStatus.BLOCKED

    def test_sweep_empty(self, db, fake_redis):
        count = sweep_blocked_executions(db, fake_redis)
        assert count == 0


# ------------------------------------
# TestSchedulerDependencyRouting
# ------------------------------------


class TestSchedulerDependencyRouting:
    def test_dependent_job_blocked_when_parent_not_succeeded(self, db, fake_redis):
        _make_job(db, 1)
        child = _make_job(db, 2)
        _make_dep(db, 2, 1)

        schedule = Schedule(
            job_id=child.id,
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
        # Execution should be BLOCKED, not in any Redis queue
        execution = db.query(Execution).filter(Execution.job_id == 2).first()
        assert execution is not None
        assert execution.status == ExecutionStatus.BLOCKED
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 0

        # run_count should NOT have been incremented
        db.refresh(schedule)
        assert schedule.run_count == 0

    def test_dependent_job_pending_when_parent_succeeded(self, db, fake_redis):
        _make_job(db, 1)
        child = _make_job(db, 2)
        _make_dep(db, 2, 1)
        _make_execution(db, 1, ExecutionStatus.SUCCESS)

        schedule = Schedule(
            job_id=child.id,
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
        execution = db.query(Execution).filter(Execution.job_id == 2).first()
        assert execution is not None
        assert execution.status == ExecutionStatus.PENDING
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 1

        db.refresh(schedule)
        assert schedule.run_count == 1

    def test_independent_job_unaffected(self, db, fake_redis):
        """Job with no dependencies should work as before."""
        job = _make_job(db, 1)
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
        execution = db.query(Execution).filter(Execution.job_id == 1).first()
        assert execution.status == ExecutionStatus.PENDING
        assert fake_redis.llen(QUEUE_READY_MEDIUM) == 1


# ------------------------------------
# TestGetDependentsTree
# ------------------------------------


class TestGetDependentsTree:
    def test_no_dependents(self, db):
        _make_job(db, 1)
        result = get_dependents_tree(db, 1)
        assert result == []

    def test_single_level(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        result = get_dependents_tree(db, 1)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_multi_level(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 2, 1)
        _make_dep(db, 3, 2)
        result = get_dependents_tree(db, 1)
        ids = {d["id"] for d in result}
        assert ids == {2, 3}

    def test_diamond_shape(self, db):
        """A -> B, A -> C, B -> D, C -> D"""
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_job(db, 4)
        _make_dep(db, 2, 1)
        _make_dep(db, 3, 1)
        _make_dep(db, 4, 2)
        _make_dep(db, 4, 3)
        result = get_dependents_tree(db, 1)
        ids = {d["id"] for d in result}
        assert ids == {2, 3, 4}


# ------------------------------------
# TestCascadeDelete
# ------------------------------------


class TestCascadeDelete:
    def test_cascade_deletes_children(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)

        deleted = cascade_delete_job(db, 1)

        assert 2 in deleted
        assert db.query(Job).filter(Job.id == 1).first() is None
        assert db.query(Job).filter(Job.id == 2).first() is None

    def test_cascade_recursive(self, db):
        _make_job(db, 1)
        _make_job(db, 2)
        _make_job(db, 3)
        _make_dep(db, 2, 1)
        _make_dep(db, 3, 2)

        deleted = cascade_delete_job(db, 1)

        assert set(deleted) == {2, 3}
        assert db.query(Job).count() == 0

    def test_cascade_cleans_related_records(self, db):
        from db.models.schedule import Schedule

        _make_job(db, 1)
        _make_job(db, 2)
        _make_dep(db, 2, 1)
        schedule = Schedule(
            job_id=2,
            cron_expression="*/5 * * * *",
            next_run_at=datetime.now(UTC),
            status=ScheduleStatus.ACTIVE,
            run_count=0,
        )
        db.add(schedule)
        _make_execution(db, 2, ExecutionStatus.PENDING, exec_id="exec-2")
        db.commit()

        cascade_delete_job(db, 1)

        assert db.query(Schedule).count() == 0
        assert db.query(Execution).count() == 0

    def test_no_dependents_just_deletes_self(self, db):
        _make_job(db, 1)
        deleted = cascade_delete_job(db, 1)
        assert deleted == []
        assert db.query(Job).count() == 0
