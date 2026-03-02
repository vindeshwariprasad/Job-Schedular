import sys
import time
import signal

from db.session import SessionLocal
from scheduler.scheduler import run_scheduler_once, recover_orphaned_executions
from logging_config import get_logger

logger = get_logger("scheduler.runner")

MIN_SLEEP = 0.5
MAX_SLEEP = 10.0
BACKOFF_MULTIPLIER = 1.5
RECOVERY_INTERVAL = 30  # seconds

SHUTDOWN = False


def handle_shutdown(signum, frame):
    global SHUTDOWN
    logger.info("Shutdown signal received, finishing current cycle...")
    SHUTDOWN = True


signal.signal(signal.SIGINT, handle_shutdown)
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, handle_shutdown)


def start_scheduler():
    sleep_seconds = MIN_SLEEP
    last_recovery = time.monotonic()

    logger.info(
        "Scheduler started, adaptive polling %0.1fs-%0.1fs",
        MIN_SLEEP, MAX_SLEEP,
    )

    while not SHUTDOWN:
        db = SessionLocal()
        try:
            processed = run_scheduler_once(db)

            # Adaptive backoff: busy -> poll fast, idle -> slow down
            if processed > 0:
                sleep_seconds = MIN_SLEEP
            else:
                sleep_seconds = min(sleep_seconds * BACKOFF_MULTIPLIER, MAX_SLEEP)

            # Periodic recovery
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

    logger.info("Scheduler shut down cleanly")
