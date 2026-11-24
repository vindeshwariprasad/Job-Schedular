from __future__ import annotations

from auth import get_current_user
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution
from db.models.job import Job
from db.models.job_dependency import JobDependency
from db.models.retry_policy import RetryPolicy
from db.models.schedule import Schedule
from db.models.user import User
from db.session import get_db
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from logging_config import get_logger
from queues.redis_client import redis_client
from schemas.job import JobCreate
from services.idempotency_service import (
    IdempotencyResult,
    claim_idempotency_key,
    compute_payload_hash,
    store_idempotency_response,
    validate_idempotency_key,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("api.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ------------------------------------
# Helpers
# ------------------------------------

async def _load_dependencies_for_jobs(
    db: AsyncSession,
    job_ids: list[int],
) -> dict[int, list[dict]]:
    """Batch-load dependencies for a list of job IDs. Returns {job_id: [{id, name}]}."""
    if not job_ids:
        return {}

    result = await db.execute(
        select(JobDependency.job_id, JobDependency.depends_on_job_id)
        .where(JobDependency.job_id.in_(job_ids))
    )
    dep_rows = result.all()

    if not dep_rows:
        return {jid: [] for jid in job_ids}

    # Collect all parent IDs to batch-load names
    parent_ids = {row.depends_on_job_id for row in dep_rows}
    parent_result = await db.execute(
        select(Job.id, Job.name).where(Job.id.in_(parent_ids))
    )
    parent_names = {row.id: row.name for row in parent_result.all()}

    # Group by child job_id
    deps_map: dict[int, list[dict]] = {jid: [] for jid in job_ids}
    for row in dep_rows:
        deps_map.setdefault(row.job_id, []).append({
            "id": row.depends_on_job_id,
            "name": parent_names.get(row.depends_on_job_id, "Unknown"),
        })

    return deps_map


def _enrich_job_response(job: Job, deps: list[dict]) -> dict:
    """Build a JobResponse-compatible dict with dependency info."""
    return {
        "id": job.id,
        "name": job.name,
        "task_type": job.task_type,
        "payload": job.payload,
        "priority": job.priority,
        "rate_limit_per_min": job.rate_limit_per_min,
        "is_active": job.is_active,
        "depends_on_job_ids": [d["id"] for d in deps],
        "depends_on_jobs": deps,
    }


async def _validate_dependencies_async(
    db: AsyncSession,
    user_id: int,
    depends_on_job_ids: list[int],
) -> None:
    """Async version of dependency validation for use in API endpoints."""
    from constants import MAX_DEPENDENCY_PARENTS

    if not depends_on_job_ids:
        return

    if len(depends_on_job_ids) > MAX_DEPENDENCY_PARENTS:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "TOO_MANY_DEPENDENCIES",
                    "message": f"A job can depend on at most {MAX_DEPENDENCY_PARENTS} parent jobs"},
        )

    if len(depends_on_job_ids) != len(set(depends_on_job_ids)):
        raise HTTPException(
            status_code=422,
            detail={"error_code": "DUPLICATE_DEPENDENCIES",
                    "message": "Duplicate parent job IDs"},
        )

    # Batch-load parents
    result = await db.execute(
        select(Job).where(Job.id.in_(depends_on_job_ids))
    )
    parents = result.scalars().all()
    found_ids = {p.id for p in parents}

    for pid in depends_on_job_ids:
        if pid not in found_ids:
            raise HTTPException(
                status_code=404,
                detail={"error_code": "DEPENDENCY_NOT_FOUND",
                        "message": f"Parent job {pid} not found"},
            )

    for parent in parents:
        if parent.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "DEPENDENCY_FORBIDDEN",
                        "message": f"Cannot depend on job {parent.id}: belongs to another user"},
            )


async def _detect_cycle_async(
    db: AsyncSession,
    child_job_id: int,
    proposed_parent_ids: list[int],
) -> bool:
    """Async cycle detection using BFS."""
    from collections import deque

    if not proposed_parent_ids:
        return False

    result = await db.execute(select(JobDependency))
    all_deps = result.scalars().all()

    parent_map: dict[int, set[int]] = {}
    for dep in all_deps:
        parent_map.setdefault(dep.job_id, set()).add(dep.depends_on_job_id)

    # Temporarily add proposed edges
    parent_map.setdefault(child_job_id, set()).update(proposed_parent_ids)

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


# ------------------------------------
# Endpoints
# ------------------------------------

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

    # Batch-load dependencies to avoid N+1 (Issue 3)
    job_ids = [j.id for j in items]
    deps_map = await _load_dependencies_for_jobs(db, job_ids)

    enriched = [_enrich_job_response(job, deps_map.get(job.id, [])) for job in items]

    return {"items": enriched, "total": total, "page": page, "size": size}


@router.post("")
async def create_job(
    payload: JobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    # --- Idempotency check ---
    idem_active = False
    payload_hash = ""

    if idempotency_key is not None:
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={"error_code": "IDEMPOTENCY_KEY_TOO_LONG", "message": str(e)},
            ) from None

        payload_hash = compute_payload_hash(payload.model_dump())

        try:
            check = claim_idempotency_key(
                redis_client, current_user.id, idempotency_key, payload_hash,
            )
        except Exception:
            # Redis down — fail-open (Issue 1 mitigation)
            logger.warning("Idempotency Redis unavailable, proceeding without")
            check = None

        if check is not None:
            if check.result == IdempotencyResult.CACHED:
                logger.info("Idempotency hit for user %d", current_user.id)
                return check.cached_response

            if check.result == IdempotencyResult.MISMATCH:
                raise HTTPException(
                    status_code=422,
                    detail={"error_code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                            "message": "Idempotency-Key was used with a different request body"},
                )

            if check.result == IdempotencyResult.IN_PROGRESS:
                raise HTTPException(
                    status_code=409,
                    detail={"error_code": "IDEMPOTENCY_IN_PROGRESS",
                            "message": "A request with this key is already being processed"},
                )

            # IdempotencyResult.NEW — proceed to create
            idem_active = True

    # --- Dependency validation ---
    await _validate_dependencies_async(db, current_user.id, payload.depends_on_job_ids)

    if payload.depends_on_job_ids:
        # We don't know the new job's ID yet, so we can't do self-ref check here.
        # But we can detect cycles: the new job doesn't exist yet, so we use a
        # temporary sentinel. If any proposed parent can reach any other proposed parent,
        # that's already a cycle (handled by the existing graph).
        # For the actual new-job cycle check, we do it after creation.
        pass

    # --- Create job ---
    job = Job(
        user_id=current_user.id,
        name=payload.name,
        task_type=payload.task_type,
        payload=payload.payload,
        priority=payload.priority,
        rate_limit_per_min=payload.rate_limit_per_min,
    )

    db.add(job)
    await db.flush()  # Get job.id before creating dependency rows

    # --- Create dependency rows ---
    if payload.depends_on_job_ids:
        # Now we have job.id — check for cycles
        has_cycle = await _detect_cycle_async(db, job.id, payload.depends_on_job_ids)
        if has_cycle:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail={"error_code": "CIRCULAR_DEPENDENCY",
                        "message": "Adding this dependency would create a cycle"},
            )

        for parent_id in payload.depends_on_job_ids:
            dep = JobDependency(job_id=job.id, depends_on_job_id=parent_id)
            db.add(dep)

    await db.commit()
    await db.refresh(job)

    # Build response with dependency info
    deps = [{"id": pid, "name": ""} for pid in payload.depends_on_job_ids]
    if payload.depends_on_job_ids:
        deps_map = await _load_dependencies_for_jobs(db, [job.id])
        deps = deps_map.get(job.id, deps)

    response_data = _enrich_job_response(job, deps)

    # --- Store idempotency response ---
    if idem_active:
        try:
            store_idempotency_response(
                redis_client,
                current_user.id,
                idempotency_key,
                payload_hash,
                response_data,
            )
        except Exception:
            logger.warning("Failed to store idempotency response, key will expire")

    return response_data


@router.get("/{job_id}")
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

    deps_map = await _load_dependencies_for_jobs(db, [job.id])
    return _enrich_job_response(job, deps_map.get(job.id, []))


@router.get("/{job_id}/dependents")
async def get_job_dependents(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the full recursive tree of jobs depending on this job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    # BFS to collect all dependents
    from collections import deque

    dependents: list[dict] = []
    visited: set[int] = set()
    queue: deque[int] = deque([job_id])

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        children_result = await db.execute(
            select(JobDependency.job_id)
            .where(JobDependency.depends_on_job_id == current)
        )
        child_ids = [row.job_id for row in children_result.all()]

        for cid in child_ids:
            if cid not in visited:
                child_result = await db.execute(
                    select(Job.id, Job.name).where(Job.id == cid)
                )
                child = child_result.first()
                if child:
                    dependents.append({"id": child.id, "name": child.name})
                queue.append(cid)

    return {"dependents": dependents}


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: int,
    cascade: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "JOB_NOT_FOUND", "message": "Job not found"})

    if cascade:
        # Collect full dependent tree, delete from leaves to root
        from collections import deque

        all_ids: list[int] = []
        visited: set[int] = set()
        queue: deque[int] = deque([job_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            children_result = await db.execute(
                select(JobDependency.job_id)
                .where(JobDependency.depends_on_job_id == current)
            )
            child_ids = [row.job_id for row in children_result.all()]

            for cid in child_ids:
                if cid not in visited:
                    queue.append(cid)

            all_ids.append(current)

        # Reverse so leaves are deleted first
        all_ids.reverse()

        for jid in all_ids:
            await db.execute(delete(Schedule).where(Schedule.job_id == jid))
            await db.execute(delete(DeadLetterJob).where(DeadLetterJob.job_id == jid))
            await db.execute(delete(RetryPolicy).where(RetryPolicy.job_id == jid))
            await db.execute(delete(Execution).where(Execution.job_id == jid))
            await db.execute(delete(JobDependency).where(
                (JobDependency.job_id == jid) | (JobDependency.depends_on_job_id == jid)
            ))
            target = await db.execute(select(Job).where(Job.id == jid))
            target_job = target.scalar_one_or_none()
            if target_job:
                await db.delete(target_job)

        logger.info("Cascade deleted job %d and %d dependents", job_id, len(all_ids) - 1)

    else:
        # Simple delete — just the target job. FK CASCADE removes dependency rows.
        await db.execute(delete(Schedule).where(Schedule.job_id == job_id))
        await db.execute(delete(DeadLetterJob).where(DeadLetterJob.job_id == job_id))
        await db.execute(delete(RetryPolicy).where(RetryPolicy.job_id == job_id))
        await db.execute(delete(Execution).where(Execution.job_id == job_id))
        await db.execute(delete(JobDependency).where(
            (JobDependency.job_id == job_id) | (JobDependency.depends_on_job_id == job_id)
        ))
        await db.delete(job)

    await db.commit()
