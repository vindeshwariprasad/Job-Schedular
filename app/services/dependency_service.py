"""Job dependency management: validation, cycle detection, unblocking, cascade delete."""

from __future__ import annotations

import json
from collections import deque

from constants import MAX_DEPENDENCY_PARENTS, queue_for_priority
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.job_dependency import JobDependency
from db.models.retry_policy import RetryPolicy
from db.models.schedule import Schedule
from logging_config import get_logger
from redis import Redis
from sqlalchemy import delete
from sqlalchemy.orm import Session

logger = get_logger("dependency_service")


def validate_dependencies_sync(
    db: Session,
    user_id: int,
    depends_on_job_ids: list[int],
    exclude_job_id: int | None = None,
) -> None:
    """Validate dependency list for a job being created.

    Raises ValueError with a descriptive message on any validation failure.
    Called from the async API layer which wraps errors into HTTPException.
    """
    if not depends_on_job_ids:
        return

    if len(depends_on_job_ids) > MAX_DEPENDENCY_PARENTS:
        raise ValueError(
            f"A job can depend on at most {MAX_DEPENDENCY_PARENTS} parent jobs"
        )

    if len(depends_on_job_ids) != len(set(depends_on_job_ids)):
        raise ValueError("Duplicate parent job IDs")

    if exclude_job_id and exclude_job_id in depends_on_job_ids:
        raise ValueError("A job cannot depend on itself")

    # Batch-load all referenced parent jobs
    parents = db.query(Job).filter(Job.id.in_(depends_on_job_ids)).all()
    found_ids = {p.id for p in parents}

    for pid in depends_on_job_ids:
        if pid not in found_ids:
            raise LookupError(f"Parent job {pid} not found")

    for parent in parents:
        if parent.user_id != user_id:
            raise PermissionError(f"Cannot depend on job {parent.id}: belongs to another user")


def detect_cycle(
    db: Session,
    child_job_id: int,
    proposed_parent_ids: list[int],
) -> bool:
    """Return True if adding proposed_parent_ids as parents of child_job_id creates a cycle.

    Uses BFS: starting from each proposed parent, walk upward through existing
    dependencies. If we ever reach child_job_id, there's a cycle.
    """
    if not proposed_parent_ids:
        return False

    # Load the full dependency graph for the user (bounded by user's job count)
    # Build adjacency: child -> [parents]
    all_deps = db.query(JobDependency).all()
    # Map: job_id -> set of parent_ids
    parent_map: dict[int, set[int]] = {}
    for dep in all_deps:
        parent_map.setdefault(dep.job_id, set()).add(dep.depends_on_job_id)

    # Temporarily add the proposed edges
    parent_map.setdefault(child_job_id, set()).update(proposed_parent_ids)

    # BFS from child_job_id following parent edges — if we reach child_job_id again, cycle
    visited: set[int] = set()
    queue: deque[int] = deque(proposed_parent_ids)

    while queue:
        node = queue.popleft()
        if node == child_job_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        for parent in parent_map.get(node, set()):
            queue.append(parent)

    return False


def check_parents_satisfied(db: Session, job_id: int) -> bool:
    """Check if ALL parents of a job have their latest terminal execution as SUCCESS.

    Also checks that parent jobs are active. Returns True if the job has no dependencies.
    """
    deps = (
        db.query(JobDependency)
        .filter(JobDependency.job_id == job_id)
        .all()
    )

    if not deps:
        return True

    parent_ids = [d.depends_on_job_id for d in deps]

    # Batch-load parent jobs to check is_active
    parents = db.query(Job).filter(Job.id.in_(parent_ids)).all()
    parent_map = {p.id: p for p in parents}

    for pid in parent_ids:
        parent = parent_map.get(pid)

        # If parent was deleted (FK CASCADE set the row to gone), treat as satisfied
        # since the dependency row should have been cascade-deleted too.
        # This is a safety check for edge cases.
        if parent is None:
            return False

        # Inactive parent = not satisfied
        if not parent.is_active:
            return False

        # Get latest terminal execution for this parent
        latest = (
            db.query(Execution)
            .filter(
                Execution.job_id == pid,
                Execution.status.in_([ExecutionStatus.SUCCESS, ExecutionStatus.FAILED]),
            )
            .order_by(Execution.created_at.desc())
            .first()
        )

        if latest is None or latest.status != ExecutionStatus.SUCCESS:
            return False

    return True


def unblock_children(db: Session, redis: Redis, parent_job_id: int) -> int:
    """After a parent job succeeds, check all children and unblock those fully satisfied.

    Uses FOR UPDATE on BLOCKED executions to prevent double-enqueue from
    concurrent parent completions.

    Returns the number of executions unblocked.
    """
    # Find all child job IDs that depend on this parent
    child_deps = (
        db.query(JobDependency.job_id)
        .filter(JobDependency.depends_on_job_id == parent_job_id)
        .distinct()
        .all()
    )

    if not child_deps:
        return 0

    child_job_ids = [d.job_id for d in child_deps]
    unblocked_count = 0

    for child_id in child_job_ids:
        # Check if ALL parents of this child are now satisfied
        if not check_parents_satisfied(db, child_id):
            continue

        # Load the child job for priority info
        child_job = db.query(Job).filter(Job.id == child_id).first()
        if not child_job:
            continue

        # Lock and unblock BLOCKED executions for this child
        blocked_execs = (
            db.query(Execution)
            .filter(
                Execution.job_id == child_id,
                Execution.status == ExecutionStatus.BLOCKED,
            )
            .with_for_update()
            .all()
        )

        target_queue = queue_for_priority(child_job.priority)

        for execution in blocked_execs:
            execution.status = ExecutionStatus.PENDING
            unblocked_count += 1

            redis.lpush(
                target_queue,
                json.dumps({
                    "execution_id": execution.execution_id,
                    "job_id": child_id,
                }),
            )

    if unblocked_count > 0:
        db.commit()
        logger.info(
            "Unblocked %d execution(s) for child jobs %s after parent %d succeeded",
            unblocked_count,
            child_job_ids,
            parent_job_id,
        )

    return unblocked_count


def sweep_blocked_executions(db: Session, redis: Redis) -> int:
    """Safety-net sweep: re-evaluate all BLOCKED executions.

    Called periodically by the scheduler alongside orphan recovery.
    Returns the number of executions unblocked.
    """
    blocked = (
        db.query(Execution)
        .filter(Execution.status == ExecutionStatus.BLOCKED)
        .all()
    )

    if not blocked:
        return 0

    # Group by job_id to avoid redundant parent checks
    job_ids = {e.job_id for e in blocked}

    # Batch check which jobs have all parents satisfied
    satisfied_jobs: set[int] = set()
    for jid in job_ids:
        if check_parents_satisfied(db, jid):
            satisfied_jobs.add(jid)

    if not satisfied_jobs:
        return 0

    # Load job objects for priority lookup
    jobs = {j.id: j for j in db.query(Job).filter(Job.id.in_(satisfied_jobs)).all()}

    unblocked_count = 0
    for execution in blocked:
        if execution.job_id not in satisfied_jobs:
            continue

        # Lock to prevent concurrent modification
        locked = (
            db.query(Execution)
            .filter(
                Execution.id == execution.id,
                Execution.status == ExecutionStatus.BLOCKED,
            )
            .with_for_update()
            .first()
        )
        if not locked:
            continue

        locked.status = ExecutionStatus.PENDING
        unblocked_count += 1

        job = jobs.get(locked.job_id)
        target_queue = queue_for_priority(job.priority if job else "MEDIUM")

        redis.lpush(
            target_queue,
            json.dumps({
                "execution_id": locked.execution_id,
                "job_id": locked.job_id,
            }),
        )

    if unblocked_count > 0:
        db.commit()
        logger.info("BLOCKED sweep: unblocked %d execution(s)", unblocked_count)

    return unblocked_count


def get_dependents_tree(db: Session, job_id: int) -> list[dict]:
    """Return the full recursive tree of jobs that depend on this job.

    Uses BFS to traverse all direct and transitive children.
    Returns list of {id, name} dicts.
    """
    result: list[dict] = []
    visited: set[int] = set()
    queue: deque[int] = deque([job_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        children = (
            db.query(JobDependency.job_id)
            .filter(JobDependency.depends_on_job_id == current)
            .all()
        )

        for (child_id,) in children:
            if child_id not in visited:
                child_job = db.query(Job).filter(Job.id == child_id).first()
                if child_job:
                    result.append({"id": child_job.id, "name": child_job.name})
                queue.append(child_id)

    return result


def cascade_delete_job(db: Session, job_id: int) -> list[int]:
    """Recursively delete a job and all its dependents.

    Collects the full tree, then deletes from leaves to root.
    Returns list of deleted job IDs (not including the original).
    """
    dependents = get_dependents_tree(db, job_id)
    # Reverse so we delete leaves first (furthest from root)
    dependent_ids = [d["id"] for d in reversed(dependents)]

    all_ids_to_delete = dependent_ids + [job_id]

    for jid in all_ids_to_delete:
        db.execute(delete(Schedule).where(Schedule.job_id == jid))
        db.execute(delete(DeadLetterJob).where(DeadLetterJob.job_id == jid))
        db.execute(delete(RetryPolicy).where(RetryPolicy.job_id == jid))
        db.execute(delete(Execution).where(Execution.job_id == jid))
        db.execute(delete(JobDependency).where(
            (JobDependency.job_id == jid) | (JobDependency.depends_on_job_id == jid)
        ))

    # Delete the job rows themselves
    for jid in all_ids_to_delete:
        job = db.query(Job).filter(Job.id == jid).first()
        if job:
            db.delete(job)

    db.commit()

    logger.info(
        "Cascade deleted job %d and %d dependents: %s",
        job_id, len(dependent_ids), dependent_ids,
    )

    return dependent_ids
