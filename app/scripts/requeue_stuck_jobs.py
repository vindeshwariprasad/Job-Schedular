import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from db.models.execution import Execution, ExecutionStatus
from queues.redis_client import redis_client
from db.session import SessionLocal
from config import VISIBILITY_TIMEOUT
from constants import QUEUE_READY, QUEUE_PROCESSING


def requeue_stuck_jobs():
    db: Session = SessionLocal()

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=VISIBILITY_TIMEOUT)

    # 1. Recover RUNNING jobs that have been stuck too long
    stuck_running = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.RUNNING,
            Execution.started_at < cutoff,
        )
        .all()
    )

    for execution in stuck_running:
        print(f"Requeuing stuck RUNNING execution: {execution.execution_id}")

        execution.status = ExecutionStatus.PENDING
        db.commit()

        payload = json.dumps({
            "execution_id": execution.execution_id,
            "job_id": execution.job_id,
        })

        redis_client.lrem(QUEUE_PROCESSING, 0, payload)
        redis_client.lpush(QUEUE_READY, payload)

    # 2. Recover orphaned PENDING jobs (in DB but missing from Redis queue)
    stuck_pending = (
        db.query(Execution)
        .filter(
            Execution.status == ExecutionStatus.PENDING,
            Execution.created_at < cutoff,
        )
        .all()
    )

    # Get all execution_ids currently in Redis queues to avoid duplicates
    ready_items = redis_client.lrange(QUEUE_READY, 0, -1)
    processing_items = redis_client.lrange(QUEUE_PROCESSING, 0, -1)

    queued_execution_ids = set()
    for item in ready_items + processing_items:
        try:
            data = json.loads(item)
            queued_execution_ids.add(data["execution_id"])
        except (json.JSONDecodeError, KeyError):
            continue

    for execution in stuck_pending:
        if execution.execution_id in queued_execution_ids:
            continue

        print(f"Requeuing orphaned PENDING execution: {execution.execution_id}")

        payload = json.dumps({
            "execution_id": execution.execution_id,
            "job_id": execution.job_id,
        })

        redis_client.lpush(QUEUE_READY, payload)

    db.close()
    print("Requeue complete.")


if __name__ == "__main__":
    requeue_stuck_jobs()
