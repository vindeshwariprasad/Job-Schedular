import json

from auth import get_current_user
from constants import (
    QUEUE_FAILED,
    QUEUE_PROCESSING,
    QUEUE_READY_HIGH,
    QUEUE_READY_LOW,
    QUEUE_READY_MEDIUM,
)
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.user import User
from db.session import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from queues.redis_client import redis_client
from services.dlq_service import replay_dlq_execution
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/dlq", tags=["Admin DLQ"])


async def _user_job_ids(db: AsyncSession, current_user: User):
    result = await db.execute(
        select(Job.id).where(Job.user_id == current_user.id)
    )
    return [row[0] for row in result.all()]


@router.get("/user-stats")
async def user_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_ids = await _user_job_ids(db, current_user)

    if not job_ids:
        return {"total_executions": 0, "success": 0, "failed": 0, "dlq": 0}

    result = await db.execute(
        select(Execution.status, func.count(Execution.id))
        .where(Execution.job_id.in_(job_ids))
        .group_by(Execution.status)
    )
    status_counts = result.all()

    counts = {status: count for status, count in status_counts}
    total = sum(counts.values())
    success = counts.get("SUCCESS", 0)
    failed = counts.get("FAILED", 0)

    dlq_result = await db.execute(
        select(func.count(DeadLetterJob.id))
        .where(DeadLetterJob.job_id.in_(job_ids))
    )
    dlq_count = dlq_result.scalar()

    return {
        "total_executions": total,
        "success": success,
        "failed": failed,
        "dlq": dlq_count,
    }


@router.get("/global-stats")
async def global_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Execution.status, func.count(Execution.id))
        .group_by(Execution.status)
    )
    status_counts = result.all()

    counts = {status: count for status, count in status_counts}
    total = sum(counts.values())
    success = counts.get("SUCCESS", 0)
    failed = counts.get("FAILED", 0)

    dlq_result = await db.execute(select(func.count(DeadLetterJob.id)))
    dlq_count = dlq_result.scalar()

    return {
        "total_executions": total,
        "success": success,
        "failed": failed,
        "dlq": dlq_count,
    }


@router.get("/execution-history")
async def execution_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    date_col = func.date(Execution.created_at)

    result = await db.execute(
        select(
            date_col.label("date"),
            func.count(Execution.id).label("total"),
            func.sum(case((Execution.status == "SUCCESS", 1), else_=0)).label("success"),
            func.sum(case((Execution.status == "FAILED", 1), else_=0)).label("failed"),
        )
        .group_by(date_col)
        .order_by(date_col)
    )
    rows = result.all()

    return [
        {
            "date": str(row.date),
            "total": row.total,
            "success": row.success,
            "failed": row.failed,
        }
        for row in rows
    ]


@router.get("/")
async def list_dlq(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_ids = await _user_job_ids(db, current_user)
    if not job_ids:
        return {"items": [], "total": 0, "page": page, "size": size}

    count_result = await db.execute(
        select(func.count(DeadLetterJob.id)).where(DeadLetterJob.job_id.in_(job_ids))
    )
    total = count_result.scalar()

    result = await db.execute(
        select(DeadLetterJob)
        .where(DeadLetterJob.job_id.in_(job_ids))
        .order_by(DeadLetterJob.failed_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/{execution_id}/replay")
async def replay_dlq(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await replay_dlq_execution(db, execution_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/executions")
async def list_executions(
    status: ExecutionStatus | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_ids = await _user_job_ids(db, current_user)
    if not job_ids:
        return {"items": [], "total": 0, "page": page, "size": size}

    base_filter = Execution.job_id.in_(job_ids)
    filters = [base_filter]
    if status:
        filters.append(Execution.status == status)

    count_result = await db.execute(
        select(func.count(Execution.id)).where(*filters)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Execution)
        .where(*filters)
        .order_by(Execution.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/queues")
async def queue_stats(current_user: User = Depends(get_current_user)):
    high = redis_client.llen(QUEUE_READY_HIGH)
    med = redis_client.llen(QUEUE_READY_MEDIUM)
    low = redis_client.llen(QUEUE_READY_LOW)
    return {
        "ready": high + med + low,
        "ready_high": high,
        "ready_medium": med,
        "ready_low": low,
        "processing": redis_client.llen(QUEUE_PROCESSING),
        "failed": redis_client.llen(QUEUE_FAILED),
    }


@router.get("/queues/details")
async def queue_details(current_user: User = Depends(get_current_user)):
    """Return actual contents of all Redis queues."""
    def parse_queue(queue_name):
        items = redis_client.lrange(queue_name, 0, -1)
        parsed = []
        for item in items:
            try:
                parsed.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                parsed.append({"raw": item})
        return parsed

    return {
        "ready_high": {
            "count": redis_client.llen(QUEUE_READY_HIGH),
            "items": parse_queue(QUEUE_READY_HIGH),
        },
        "ready_medium": {
            "count": redis_client.llen(QUEUE_READY_MEDIUM),
            "items": parse_queue(QUEUE_READY_MEDIUM),
        },
        "ready_low": {
            "count": redis_client.llen(QUEUE_READY_LOW),
            "items": parse_queue(QUEUE_READY_LOW),
        },
        "processing": {
            "count": redis_client.llen(QUEUE_PROCESSING),
            "items": parse_queue(QUEUE_PROCESSING),
        },
        "failed": {
            "count": redis_client.llen(QUEUE_FAILED),
            "items": parse_queue(QUEUE_FAILED),
        },
    }
