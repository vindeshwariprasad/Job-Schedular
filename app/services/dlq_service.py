import json

from constants import QUEUE_FAILED, queue_for_priority
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from logging_config import get_logger
from queues.redis_client import redis_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from utils.execution import generate_execution_id

logger = get_logger("dlq_service")


async def replay_dlq_execution(db: AsyncSession, execution_id: str):
    result = await db.execute(
        select(DeadLetterJob).where(DeadLetterJob.execution_id == execution_id)
    )
    dlq = result.scalar_one_or_none()

    if not dlq:
        raise ValueError("DLQ entry not found")

    # Idempotency: check if a replay is already in-flight (PENDING or RUNNING)
    result = await db.execute(
        select(Execution).where(
            Execution.job_id == dlq.job_id,
            Execution.status.in_([ExecutionStatus.PENDING, ExecutionStatus.RUNNING]),
        )
    )
    existing_replay = result.scalar_one_or_none()

    if existing_replay:
        logger.info(
            "Replay skipped, in-flight execution already exists",
            extra={
                "execution_id": execution_id,
                "existing_execution_id": existing_replay.execution_id,
                "job_id": dlq.job_id,
            },
        )
        return {
            "old_execution_id": execution_id,
            "new_execution_id": existing_replay.execution_id,
            "status": "already_in_flight",
        }

    # Look up job priority for correct queue routing
    result = await db.execute(select(Job).where(Job.id == dlq.job_id))
    job = result.scalar_one_or_none()
    target_queue = queue_for_priority(job.priority if job else "MEDIUM")

    new_execution_id = generate_execution_id()

    execution = Execution(
        job_id=dlq.job_id,
        execution_id=new_execution_id,
        status=ExecutionStatus.PENDING,
        attempt=1,
    )

    db.add(execution)
    await db.delete(dlq)
    await db.commit()

    payload = json.dumps({
        "execution_id": new_execution_id,
        "job_id": dlq.job_id,
    })

    redis_client.lpush(target_queue, payload)
    redis_client.lrem(QUEUE_FAILED, 0, execution_id)

    logger.info(
        "DLQ execution replayed",
        extra={"execution_id": execution_id, "new_execution_id": new_execution_id, "job_id": dlq.job_id},
    )

    return {
        "old_execution_id": execution_id,
        "new_execution_id": new_execution_id,
        "status": "replayed",
    }
