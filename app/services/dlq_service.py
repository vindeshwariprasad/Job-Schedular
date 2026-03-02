import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from queues.redis_client import redis_client
from utils.execution import generate_execution_id
from constants import QUEUE_READY, QUEUE_FAILED
from logging_config import get_logger

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

    redis_client.lpush(QUEUE_READY, payload)
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
