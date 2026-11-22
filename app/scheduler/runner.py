import os
import signal
import socket
import sys
import time

from db.session import SessionLocal
from logging_config import get_logger
from metrics.prometheus import scheduler_is_leader
from queues.redis_client import redis_client
from scheduler.scheduler import recover_orphaned_executions, run_scheduler_once

logger = get_logger("scheduler.runner")

MIN_SLEEP = 0.5
MAX_SLEEP = 10.0
BACKOFF_MULTIPLIER = 1.5
RECOVERY_INTERVAL = 30  # seconds

# Leader election constants
LEADER_KEY = "scheduler_leader"
LEADER_TTL = 30  # seconds
STANDBY_RETRY_INTERVAL = 5  # seconds

INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"

SHUTDOWN = False


def handle_shutdown(signum, frame):
    global SHUTDOWN
    logger.info("Shutdown signal received, finishing current cycle...")
    SHUTDOWN = True


signal.signal(signal.SIGINT, handle_shutdown)
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, handle_shutdown)


def _try_acquire_lock(redis=None):
    """Attempt to acquire the scheduler leader lock. Returns True if acquired."""
    r = redis or redis_client
    result = r.set(LEADER_KEY, INSTANCE_ID, nx=True, ex=LEADER_TTL)
    return result is not None and result is not False


def _renew_lock(redis=None):
    """Renew the leader lock. Returns True if still leader."""
    r = redis or redis_client
    result = r.set(LEADER_KEY, INSTANCE_ID, xx=True, ex=LEADER_TTL)
    return result is not None and result is not False


def _release_lock(redis=None):
    """Release the leader lock only if we still own it."""
    r = redis or redis_client
    current = r.get(LEADER_KEY)
    if current == INSTANCE_ID:
        r.delete(LEADER_KEY)
        logger.info("Leader lock released")


def start_scheduler(redis=None):
    r = redis or redis_client

    logger.info(
        "Scheduler instance %s starting, adaptive polling %0.1fs-%0.1fs",
        INSTANCE_ID, MIN_SLEEP, MAX_SLEEP,
    )

    while not SHUTDOWN:
        # --- Standby: try to acquire leadership ---
        try:
            acquired = _try_acquire_lock(r)
        except Exception as e:
            logger.error("Failed to acquire leader lock: %s", e)
            scheduler_is_leader.set(0)
            time.sleep(STANDBY_RETRY_INTERVAL)
            continue

        if not acquired:
            scheduler_is_leader.set(0)
            logger.debug("Not leader, standby for %ds", STANDBY_RETRY_INTERVAL)
            time.sleep(STANDBY_RETRY_INTERVAL)
            continue

        # --- Leader: run scheduler loop ---
        scheduler_is_leader.set(1)
        logger.info("Acquired leader lock, instance=%s", INSTANCE_ID)

        sleep_seconds = MIN_SLEEP
        last_recovery = time.monotonic()

        while not SHUTDOWN:
            # Renew lock at the start of every iteration
            if not _renew_lock(r):
                logger.warning("Lost leader lock, returning to standby")
                scheduler_is_leader.set(0)
                break

            db = SessionLocal()
            try:
                processed = run_scheduler_once(db)

                # Adaptive backoff: busy -> poll fast, idle -> slow down
                if processed > 0:
                    sleep_seconds = MIN_SLEEP
                else:
                    sleep_seconds = min(sleep_seconds * BACKOFF_MULTIPLIER, MAX_SLEEP)

                # Periodic recovery (leader only)
                now = time.monotonic()
                if now - last_recovery >= RECOVERY_INTERVAL:
                    recover_orphaned_executions(db)
                    last_recovery = now

            except Exception as e:
                logger.error("Scheduler error: %s", e, exc_info=True)
                db.rollback()
                sleep_seconds = min(sleep_seconds * BACKOFF_MULTIPLIER, MAX_SLEEP)
            finally:
                db.close()

            time.sleep(sleep_seconds)

    # Shutdown: release lock if we hold it
    _release_lock(r)
    scheduler_is_leader.set(0)
    logger.info("Scheduler shut down cleanly")
