from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.models.job import Job
from db.models.user import User
from db.models.schedule import Schedule
from db.models.execution import Execution
from db.models.retry_policy import RetryPolicy
from db.models.dead_letter import DeadLetterJob
from schemas.job import JobCreate, JobResponse
from auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count_result = await db.execute(
        select(func.count(Job.id)).where(Job.user_id == current_user.id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Job)
        .where(Job.user_id == current_user.id)
        .order_by(Job.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("", response_model=JobResponse)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = Job(
        user_id=current_user.id,
        name=payload.name,
        task_type=payload.task_type,
        payload=payload.payload,
        rate_limit_per_min=payload.rate_limit_per_min,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    # Cascade delete related records
    await db.execute(delete(Schedule).where(Schedule.job_id == job_id))
    await db.execute(delete(DeadLetterJob).where(DeadLetterJob.job_id == job_id))
    await db.execute(delete(RetryPolicy).where(RetryPolicy.job_id == job_id))
    await db.execute(delete(Execution).where(Execution.job_id == job_id))
    await db.delete(job)
    await db.commit()
