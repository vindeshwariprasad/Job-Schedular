import json
import random
from datetime import UTC, datetime, timedelta

from config import VISIBILITY_TIMEOUT
from constants import (
    ALL_READY_QUEUES,
    QUEUE_PROCESSING,
    queue_for_priority,
)
from croniter import croniter
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.job_dependency import JobDependency
from db.models.schedule import Schedule, ScheduleStatus
from logging_config import get_logger
from queues.redis_client import redis_client
from services.dependency_service import check_parents_satisfied
from sqlalchemy.orm import Session
from utils.execution import generate_execution_id

logger = get_logger("scheduler")

MAX_JITTER_SECONDS = 5


def run_scheduler_once(db: Session, batch_size: int = 100) -> int:
    """
    Scan due schedules, create executions,
    enqueue them, and compute next run times.

    Scheduler NEVER executes jobs.
    Only picks up schedules that are active (not paused/completed).
    Respects max_runs limit.
    Handles job dependencies: creates BLOCKED executions when parents not satisfied.
    """
    now = datetime.now(UTC)

    # Only pick active schedules that are due
    due_schedules = (
        db.query(Schedule)
        .filter(
            Schedule.next_run_at <= now,
            Schedule.status == ScheduleStatus.ACTIVE,
        )
        .order_by(Schedule.next_run_at)
        .with_for_update(skip_locked=True)
        .limit(batch_size)
        .all()
    )

    # Pre-load dependency info for all due jobs (Issue 2: load BEFORE creating executions)
    due_job_ids = {s.job_id for s in due_schedules}
    deps_by_job: dict[int, list[int]] = {}
    if due_job_ids:
        all_deps = (
            db.query(JobDependency)
            .filter(JobDependency.job_id.in_(due_job_ids))
            .all()
        )
        for dep in all_deps:
            deps_by_job.setdefault(dep.job_id, []).append(dep.depends_on_job_id)

    # Collect (payload_json, job_id) pairs for PENDING executions only
    enqueue_items: list[tuple[str, int]] = []

    for schedule in due_schedules:
        execution_id = generate_execution_id()
        has_deps = schedule.job_id in deps_by_job

        # Check if dependencies are satisfied
        if has_deps:
            parents_ok = check_parents_satisfied(db, schedule.job_id)
        else:
            parents_ok = True

        if parents_ok:
            # Normal flow: PENDING execution
            execution = Execution(
                job_id=schedule.job_id,
                execution_id=execution_id,
                status=ExecutionStatus.PENDING,
                attempt=1,
            )
            db.add(execution)

            # Track last run for observability
            schedule.last_run_at = now
            schedule.run_count += 1

            # Check if max_runs limit reached
            if schedule.max_runs is not None and schedule.run_count >= schedule.max_runs:
                schedule.status = ScheduleStatus.COMPLETED
                schedule.next_run_at = None
            else:
                # Compute next run with jitter to avoid thundering herd
                cron = croniter(schedule.cron_expression, now)
                jitter = timedelta(seconds=random.uniform(0, MAX_JITTER_SECONDS))
                schedule.next_run_at = cron.get_next(datetime) + jitter

            enqueue_items.append((
                json.dumps({
                    "execution_id": execution_id,
                    "job_id": schedule.job_id,
                }),
                schedule.job_id,
            ))
        else:
            # Dependencies not satisfied: BLOCKED execution
            execution = Execution(
                job_id=schedule.job_id,
                execution_id=execution_id,
                status=ExecutionStatus.BLOCKED,
                attempt=1,
            )
            db.add(execution)

            # Do NOT increment run_count (BLOCKED doesn't count toward max_runs)
            # But DO advance next_run_at so scheduler doesn't retry immediately
            cron = croniter(schedule.cron_expression, now)
            jitter = timedelta(seconds=random.uniform(0, MAX_JITTER_SECONDS))
            schedule.next_run_at = cron.get_next(datetime) + jitter

            logger.info(
                "Execution BLOCKED: parents %s not all satisfied for job %d",
                deps_by_job.get(schedule.job_id, []),
                schedule.job_id,
                extra={"execution_id": execution_id, "job_id": schedule.job_id},
            )

    db.commit()

    # Batch-load job priorities for all scheduled jobs
    if enqueue_items:
        job_ids = {item[1] for item in enqueue_items}
        jobs = {j.id: j for j in db.query(Job).filter(Job.id.in_(job_ids)).all()}
    else:
        jobs = {}

    # Enqueue after commit so Redis and DB are consistent
    for payload, job_id in enqueue_items:
        job = jobs.get(job_id)
        queue = queue_for_priority(job.priority if job else "MEDIUM")
        redis_client.lpush(queue, payload)

    return len(due_schedules)


def recover_orphaned_executions(db: Session) -> None:
    """
    Find PENDING/RUNNING executions that are not in any Redis queue
    and re-enqueue them. Runs automatically as part of the scheduler loop.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=VISIBILITY_TIMEOUT)

    # 1. Recover stuck RUNNING executions (started too long ago)
    stuck_running = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.RUNNING,
            Execution.started_at < cutoff,
        )
        .all()
    )

    # 2. Recover orphaned PENDING executions (in DB but not in Redis)
    orphaned_pending = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.PENDING,
            Execution.created_at < cutoff,
        )
        .all()
    )

    # Batch-load job priorities for all orphaned executions
    all_orphans = stuck_running + orphaned_pending
    if all_orphans:
        job_ids = {e.job_id for e in all_orphans}
        jobs = {j.id: j for j in db.query(Job).filter(Job.id.in_(job_ids)).all()}
    else:
        jobs = {}

    for execution in stuck_running:
        logger.warning(
            "Recovering stuck RUNNING execution",
            extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
        )
        execution.status = ExecutionStatus.PENDING
        payload = json.dumps({
            "execution_id": execution.execution_id,
            "job_id": execution.job_id,
        })
        redis_client.lrem(QUEUE_PROCESSING, 0, payload)
        job = jobs.get(execution.job_id)
        queue = queue_for_priority(job.priority if job else "MEDIUM")
        redis_client.lpush(queue, payload)

    if orphaned_pending:
        # Build set of execution_ids already in Redis to avoid duplicates
        ready_items = []
        for q in ALL_READY_QUEUES:
            ready_items.extend(redis_client.lrange(q, 0, -1))
        processing_items = redis_client.lrange(QUEUE_PROCESSING, 0, -1)

        queued_ids = set()
        for item in ready_items + processing_items:
            try:
                queued_ids.add(json.loads(item)["execution_id"])
            except (json.JSONDecodeError, KeyError):
                continue

        for execution in orphaned_pending:
            if execution.execution_id not in queued_ids:
                logger.warning(
                    "Recovering orphaned PENDING execution",
                    extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
                )
                job = jobs.get(execution.job_id)
                queue = queue_for_priority(job.priority if job else "MEDIUM")
                redis_client.lpush(
                    queue,
                    json.dumps({
                        "execution_id": execution.execution_id,
                        "job_id": execution.job_id,
                    }),
                )

    db.commit()
