from prometheus_client import Counter, Gauge, Histogram

# -----------------------------
# Counters
# -----------------------------
job_executions_total = Counter(
    "job_executions_total",
    "Total number of job executions started",
)

job_success_total = Counter(
    "job_success_total",
    "Total number of successful job executions",
)

job_failure_total = Counter(
    "job_failure_total",
    "Total number of failed job executions",
)

job_retry_total = Counter(
    "job_retry_total",
    "Total number of job retries",
)

job_dlq_total = Counter(
    "job_dlq_total",
    "Total number of jobs sent to DLQ",
)

# -----------------------------
# Gauges
# -----------------------------
queue_ready_size = Gauge(
    "queue_ready_size",
    "Total number of jobs across all ready queues (backward compat)",
)

queue_ready_priority_size = Gauge(
    "queue_ready_priority_size",
    "Number of jobs in ready queue per priority level",
    ["priority"],
)

queue_processing_size = Gauge(
    "queue_processing_size",
    "Number of jobs in processing queue",
)

queue_failed_size = Gauge(
    "queue_failed_size",
    "Number of jobs in failed queue",
)

running_executions = Gauge(
    "running_executions",
    "Currently running job executions",
)

# -----------------------------
# Histogram
# -----------------------------
job_execution_duration = Histogram(
    "job_execution_duration_seconds",
    "Job execution duration in seconds",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

# -----------------------------
# Infrastructure Health
# -----------------------------
redis_up = Gauge(
    "redis_up",
    "Whether Redis is reachable (1 = up, 0 = down)",
)

auth_redis_failures_total = Counter(
    "auth_redis_failures_total",
    "Auth rate-limit checks that failed due to Redis unavailability",
)

# -----------------------------
# Scheduler Leader Election
# -----------------------------
scheduler_is_leader = Gauge(
    "scheduler_is_leader",
    "Whether this scheduler instance is the active leader (1 = leader, 0 = standby)",
)

# -----------------------------
# Circuit Breaker
# -----------------------------
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state per endpoint (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["endpoint"],
)

circuit_breaker_trips_total = Counter(
    "circuit_breaker_trips_total",
    "Total number of times a circuit breaker has tripped open",
)

circuit_breaker_rejections_total = Counter(
    "circuit_breaker_rejections_total",
    "Total number of requests rejected by an open circuit breaker",
)

# -----------------------------
# Backpressure
# -----------------------------
scheduler_backpressure_active = Gauge(
    "scheduler_backpressure_active",
    "Whether scheduler backpressure is active (1 = throttled, 0 = normal)",
)
