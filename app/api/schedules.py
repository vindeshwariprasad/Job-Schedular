from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from croniter import croniter
from db.session import get_db

from db.models.job import Job
from db.models.user import User
from db.models.schedule import Schedule, ScheduleStatus
from schemas.schedule import ScheduleCreate, ScheduleResponse
from auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["schedules"])


async def _get_user_job(job_id: int, db: AsyncSession, current_user: User) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})
    return job


@router.post("/{job_id}/schedule", response_model=ScheduleResponse)
async def create_schedule(
    job_id: int,
    payload: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_job(job_id, db, current_user)

    # Prevent duplicate schedule
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"error_code": "SCHEDULE_EXISTS", "message": "Schedule already exists for this job"})

    # Validate cron
    now = datetime.now(timezone.utc)
    try:
        cron = croniter(payload.cron_expression, now)
        next_run_at = cron.get_next(datetime)
    except Exception:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_CRON", "message": "Invalid cron expression"})

    schedule = Schedule(
        job_id=job_id,
        cron_expression=payload.cron_expression,
        next_run_at=next_run_at,
        status=ScheduleStatus.ACTIVE,
        max_runs=payload.max_runs,
        run_count=0,
    )

    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return schedule


@router.get("/{job_id}/schedule", response_model=ScheduleResponse)
async def get_schedule(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_job(job_id, db, current_user)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail={"error_code": "SCHEDULE_NOT_FOUND", "message": "Schedule not found"})
    return schedule


@router.patch("/{job_id}/schedule/pause", response_model=ScheduleResponse)
async def pause_schedule(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_job(job_id, db, current_user)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail={"error_code": "SCHEDULE_NOT_FOUND", "message": "Schedule not found"})

    if schedule.status == ScheduleStatus.COMPLETED:
        raise HTTPException(status_code=400, detail={"error_code": "SCHEDULE_COMPLETED", "message": "Schedule already completed its max runs"})

    schedule.status = ScheduleStatus.PAUSED
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.patch("/{job_id}/schedule/resume", response_model=ScheduleResponse)
async def resume_schedule(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_job(job_id, db, current_user)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail={"error_code": "SCHEDULE_NOT_FOUND", "message": "Schedule not found"})

    if schedule.status != ScheduleStatus.PAUSED:
        raise HTTPException(status_code=400, detail={"error_code": "SCHEDULE_NOT_PAUSED", "message": "Schedule is not paused"})

    # Recalculate next_run_at from now
    now = datetime.now(timezone.utc)
    cron = croniter(schedule.cron_expression, now)
    schedule.next_run_at = cron.get_next(datetime)
    schedule.status = ScheduleStatus.ACTIVE
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{job_id}/schedule", status_code=204)
async def delete_schedule(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_job(job_id, db, current_user)
    result = await db.execute(select(Schedule).where(Schedule.job_id == job_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail={"error_code": "SCHEDULE_NOT_FOUND", "message": "Schedule not found"})

    await db.delete(schedule)
    await db.commit()
