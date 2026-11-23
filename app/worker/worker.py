from __future__ import annotations

import json
import random
import signal
import sys
import threading
import time
import types
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

from config import (
    BASE_RETRY_DELAY,
    CIRCUIT_MAX_OPEN_RETRIES,
    JOB_EXECUTION_TIMEOUT,
    MAX_RETRIES,
    MAX_WORKERS,
    RATE_LIMIT_WINDOW,
    WORKER_POLL_TIMEOUT,
)
from constants import (
    QUEUE_FAILED,
    QUEUE_PROCESSING,
    QUEUE_READY_HIGH,
    QUEUE_READY_LOW,
    QUEUE_READY_MEDIUM,
    queue_for_priority,
)
from db.models.dead_letter import DeadLetterJob
from db.models.execution import Execution, ExecutionStatus
from db.models.job import Job
from db.models.retry_policy import RetryPolicy
from db.session import SessionLocal
from logging_config import get_logger
from metrics.prometheus import (
    job_dlq_total,
    job_execution_duration,
    job_executions_total,
    job_failure_total,
    job_retry_total,
    job_success_total,
    queue_failed_size,
    queue_processing_size,
    queue_ready_priority_size,
    queue_ready_size,
    running_executions,
)
from queues.rate_limiter import is_rate_limited
from queues.redis_client import redis_client
from redis import Redis
from sqlalchemy.orm import Session
from worker.circuit_breaker import CircuitOpenError
from worker.executor import execute_job

logger = get_logger("worker")

PUBSUB_CHANNEL = "execution:updates"


def _publish_update(redis: Redis, execution: Execution, job: Job) -> None:
    """Publish an execution status change to Redis pub/sub for WebSocket broadcast."""
    message = json.dumps({
        "execution_id": execution.execution_id,
        "job_id": execution.job_id,
        "user_id": job.user_id,
        "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        "attempt": execution.attempt,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "error": execution.error,
    })
    try:
        redis.publish(PUBSUB_CHANNEL, message)
    except Exception as e:
        logger.error("Failed to publish execution update: %s", e)

# ----------------------------
# Graceful shutdown
# ----------------------------
SHUTDOWN = False


def handle_shutdown(signum: int, frame: types.FrameType | None) -> None:
    global SHUTDOWN
    logger.info("Shutdown signal received")
    SHUTDOWN = True


signal.signal(signal.SIGINT, handle_shutdown)
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, handle_shutdown)


# ----------------------------
# Queue metrics updater
# ----------------------------
def update_queue_metrics(redis: Redis) -> None:
    high = redis.llen(QUEUE_READY_HIGH)
    med = redis.llen(QUEUE_READY_MEDIUM)
    low = redis.llen(QUEUE_READY_LOW)

    queue_ready_size.set(high + med + low)
    queue_ready_priority_size.labels(priority="high").set(high)
    queue_ready_priority_size.labels(priority="medium").set(med)
    queue_ready_priority_size.labels(priority="low").set(low)

    queue_processing_size.set(redis.llen(QUEUE_PROCESSING))
    queue_failed_size.set(redis.llen(QUEUE_FAILED))


# ----------------------------
# Weighted priority queue selection
# ----------------------------
def _pick_queue_order() -> list[str]:
    """Return queue poll order based on weighted random selection.

    60% chance: HIGH first, then MEDIUM, then LOW
    30% chance: MEDIUM first, then HIGH, then LOW
    10% chance: LOW first, then HIGH, then MEDIUM
    """
    roll = random.random()
    if roll < 0.6:
        return [QUEUE_READY_HIGH, QUEUE_READY_MEDIUM, QUEUE_READY_LOW]
    elif roll < 0.9:
        return [QUEUE_READY_MEDIUM, QUEUE_READY_HIGH, QUEUE_READY_LOW]
    else:
        return [QUEUE_READY_LOW, QUEUE_READY_HIGH, QUEUE_READY_MEDIUM]


# ----------------------------
# Thread-safe job handler
# ----------------------------
def handle_task(task: str | bytes) -> None:
    """Process a single task in its own thread with its own DB session."""
    db = SessionLocal()
    try:
        if isinstance(task, bytes):
            task = task.decode("utf-8")

        payload = json.loads(task)
        execution_id: str = payload["execution_id"]

        try:
            process_execution(db, redis_client, execution_id)
        except Exception as e:
            logger.error(
                "Worker error: %s", e,
                extra={"execution_id": execution_id},
            )
            # Push back to medium queue as safe default (no DB lookup on error path)
            redis_client.lpush(QUEUE_READY_MEDIUM, task)
        finally:
            # Always remove from processing queue (either succeeded or re-enqueued)
            redis_client.lrem(QUEUE_PROCESSING, 1, task)
    finally:
        db.close()


# ----------------------------
# Worker main loop
# ----------------------------
def worker_loop(redis: Redis) -> None:
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures: list[Future[None]] = []

    logger.info("Worker started with %d concurrent threads", MAX_WORKERS)

    while not SHUTDOWN:
        update_queue_metrics(redis)

        # Clean up completed futures
        futures = [f for f in futures if not f.done()]

        # If all threads are busy, wait briefly before polling again
        if len(futures) >= MAX_WORKERS:
            time.sleep(0.1)
            continue

        # Try queues in weighted priority order (non-blocking)
        task = None
        for queue in _pick_queue_order():
            task = redis.brpoplpush(
                queue,
                QUEUE_PROCESSING,
                timeout=0,
            )
            if task:
                break

        if not task:
            time.sleep(WORKER_POLL_TIMEOUT)
            continue

        future = executor.submit(handle_task, task)
        futures.append(future)

    # Graceful shutdown: wait for in-flight tasks to finish
    logger.info("Waiting for in-flight tasks to complete...")
    executor.shutdown(wait=True)
    logger.info("Worker shut down cleanly")


# ----------------------------
# Execution processing
# ----------------------------
def process_execution(db: Session, redis: Redis, execution_id: str) -> None:
    running_executions.inc()
    start_time = time.time()

    execution = (
        db.query(Execution)
        .filter(Execution.execution_id == execution_id)
        .with_for_update()
        .first()
    )

    if not execution:
        running_executions.dec()
        return

    if execution.status != ExecutionStatus.PENDING:
        logger.info(
            "Skipping execution, current_state=%s",
            execution.status,
            extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
        )
        running_executions.dec()
        return

    job = db.query(Job).filter(Job.id == execution.job_id).first()
    if not job:
        running_executions.dec()
        raise RuntimeError("Job not found")

    # ----------------------------
    # Rate limiting (check before marking RUNNING)
    # ----------------------------
    if is_rate_limited(
        redis,
        key=f"job:{job.id}",
        limit=job.rate_limit_per_min,
        window_seconds=RATE_LIMIT_WINDOW,
    ):
        execution.status = ExecutionStatus.PENDING
        db.commit()

        redis.lpush(
            queue_for_priority(job.priority),
            json.dumps({
                "execution_id": execution.execution_id,
                "job_id": job.id,
            }),
        )
        running_executions.dec()
        return

    # Mark RUNNING (only after rate-limit passes)
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.now(UTC)
    db.commit()
    _publish_update(redis, execution, job)

    job_executions_total.inc()

    # ----------------------------
    # Retry policy (per job)
    # ----------------------------
    policy = (
        db.query(RetryPolicy)
        .filter(RetryPolicy.job_id == job.id)
        .first()
    )

    max_retries: int = policy.max_retries if policy else MAX_RETRIES
    base_delay: int = policy.base_delay_seconds if policy else BASE_RETRY_DELAY

    # ----------------------------
    # Execute job (with hard timeout)
    # ----------------------------
    timeout: int = job.payload.get("timeout", JOB_EXECUTION_TIMEOUT)
    try:
        result_container: dict[str, dict] = {}
        error_container: dict[str, Exception] = {}

        def _run() -> None:
            try:
                result_container["value"] = execute_job(job)
            except Exception as exc:
                error_container["value"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            raise TimeoutError(
                f"Job execution exceeded {timeout}s timeout"
            )
        if "value" in error_container:
            raise error_container["value"]

    except Exception as e:
        handle_failure(
            db,
            redis,
            execution,
            job,
            e,
            max_retries,
            base_delay,
        )
        return

    # ----------------------------
    # SUCCESS
    # ----------------------------
    execution.status = ExecutionStatus.SUCCESS
    execution.finished_at = datetime.now(UTC)
    db.commit()
    _publish_update(redis, execution, job)

    job_success_total.inc()
    job_execution_duration.observe(time.time() - start_time)
    running_executions.dec()


# ----------------------------
# Failure handling + retry / DLQ
# ----------------------------
def handle_failure(
    db: Session,
    redis: Redis,
    execution: Execution,
    job: Job,
    error: Exception,
    max_retries: int,
    base_delay: int,
) -> None:
    target_queue = queue_for_priority(job.priority)

    # ----------------------------
    # Circuit breaker open — re-enqueue without consuming retry budget
    # ----------------------------
    if isinstance(error, CircuitOpenError):
        # Track how many times we've been blocked by an open circuit
        circuit_retries = 0
        if execution.error and "circuit_retries=" in execution.error:
            raw = execution.error.split("circuit_retries=")[1]
            # Strip trailing non-digit characters like ')'
            digits = "".join(c for c in raw if c.isdigit())
            circuit_retries = int(digits) if digits else 0
        circuit_retries += 1

        if circuit_retries > CIRCUIT_MAX_OPEN_RETRIES:
            # Exhausted circuit-open retries — send to DLQ
            execution.attempt += 1
            execution.error = f"Circuit open for {error.endpoint} after {circuit_retries} attempts"
            execution.status = ExecutionStatus.FAILED
            db.commit()
            _publish_update(redis, execution, job)

            dlq = DeadLetterJob(
                job_id=execution.job_id,
                execution_id=execution.execution_id,
                payload={
                    "job_id": execution.job_id,
                    "execution_id": execution.execution_id,
                },
                error=execution.error,
            )
            db.add(dlq)
            db.commit()
            redis.lpush(QUEUE_FAILED, execution.execution_id)

            job_failure_total.inc()
            job_dlq_total.inc()
            running_executions.dec()

            logger.warning(
                "Execution moved to DLQ: circuit open after %d retries",
                circuit_retries,
                extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
            )
            return

        # Re-enqueue without incrementing attempt
        execution.error = f"Circuit open for {error.endpoint} (circuit_retries={circuit_retries})"
        execution.status = ExecutionStatus.PENDING
        db.commit()
        _publish_update(redis, execution, job)
        running_executions.dec()

        logger.info(
            "Circuit open, re-enqueuing (circuit_retry %d/%d)",
            circuit_retries, CIRCUIT_MAX_OPEN_RETRIES,
            extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
        )

        redis.lpush(
            target_queue,
            json.dumps({
                "execution_id": execution.execution_id,
                "job_id": execution.job_id,
            }),
        )
        return

    execution.attempt += 1
    execution.error = str(error)

    # FINAL FAILURE -> DLQ
    if execution.attempt > max_retries:
        execution.status = ExecutionStatus.FAILED
        db.commit()
        _publish_update(redis, execution, job)

        dlq = DeadLetterJob(
            job_id=execution.job_id,
            execution_id=execution.execution_id,
            payload={
                "job_id": execution.job_id,
                "execution_id": execution.execution_id,
            },
            error=str(error),
        )

        db.add(dlq)
        db.commit()

        redis.lpush(QUEUE_FAILED, execution.execution_id)

        job_failure_total.inc()
        job_dlq_total.inc()
        running_executions.dec()

        logger.warning(
            "Execution moved to DLQ after %d attempts: %s",
            execution.attempt, str(error),
            extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
        )
        return

    # RETRY
    logger.warning(
        "Execution failed (attempt %d/%d): %s",
        execution.attempt, max_retries, str(error),
        extra={"execution_id": execution.execution_id, "job_id": execution.job_id},
    )
    execution.status = ExecutionStatus.PENDING
    db.commit()
    _publish_update(redis, execution, job)

    job_retry_total.inc()
    running_executions.dec()

    time.sleep(base_delay * (2 ** (execution.attempt - 1)))

    redis.lpush(
        target_queue,
        json.dumps({
            "execution_id": execution.execution_id,
            "job_id": execution.job_id,
        }),
    )
