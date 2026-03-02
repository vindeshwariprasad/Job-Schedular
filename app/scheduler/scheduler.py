import json
import random
from datetime import datetime, timedelta, timezone

from croniter import croniter

MAX_JITTER_SECONDS = 5
from sqlalchemy.orm import Session

from db.models.schedule import Schedule, ScheduleStatus
from db.models.execution import Execution, ExecutionStatus
from queues.redis_client import redis_client
from utils.execution import generate_execution_id
from config import VISIBILITY_TIMEOUT
from constants import QUEUE_READY, QUEUE_PROCESSING
from logging_config import get_logger

logger = get_logger("scheduler")


def run_scheduler_once(db: Session, batch_size: int = 100) -> int:
    """
    Scan due schedules, create executions,
    enqueue them, and compute next run times.

    Scheduler NEVER executes jobs.
    Only picks up schedules that are active (not paused/completed).
    Respects max_runs limit.
    """
    now = datetime.now(timezone.utc)

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

    redis_payloads = []

    for schedule in due_schedules:
        execution_id = generate_execution_id()

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

        redis_payloads.append(json.dumps({
            "execution_id": execution_id,
            "job_id": schedule.job_id,
        }))

    db.commit()

    # Enqueue after commit so Redis and DB are consistent
    for payload in redis_payloads:
        redis_client.lpush(QUEUE_READY, payload)

    return len(due_schedules)


def recover_orphaned_executions(db: Session) -> None:
    """
    Find PENDING/RUNNING executions that are not in any Redis queue
    and re-enqueue them. Runs automatically as part of the scheduler loop.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=VISIBILITY_TIMEOUT)

    # 1. Recover stuck RUNNING executions (started too long ago)
    stuck_running = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.RUNNING,
            Execution.started_at < cutoff,
        )
        .all()
    )

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
        redis_client.lpush(QUEUE_READY, payload)

    # 2. Recover orphaned PENDING executions (in DB but not in Redis)
    orphaned_pending = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.PENDING,
            Execution.created_at < cutoff,
        )
        .all()
    )

    if orphaned_pending:
        # Build set of execution_ids already in Redis to avoid duplicates
        ready_items = redis_client.lrange(QUEUE_READY, 0, -1)
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
                redis_client.lpush(
                    QUEUE_READY,
                    json.dumps({
                        "execution_id": execution.execution_id,
                        "job_id": execution.job_id,
                    }),
                )

    db.commit()
