import os

MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", 3))
VISIBILITY_TIMEOUT: int = int(os.getenv("VISIBILITY_TIMEOUT", 30))
WORKER_POLL_TIMEOUT: int = int(os.getenv("WORKER_POLL_TIMEOUT", 5))
RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", 60))
BASE_RETRY_DELAY: int = int(os.getenv("BASE_RETRY_DELAY", 2))
JOB_EXECUTION_TIMEOUT: int = int(os.getenv("JOB_EXECUTION_TIMEOUT", 120))
MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", 10))
