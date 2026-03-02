# System Design Document — Job Scheduler

> A self-hosted, distributed job scheduling platform with cron-based scheduling,
> automatic retries, dead letter queues, per-job rate limiting, and full observability.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Architecture Overview](#architecture-overview)
3. [Data Flow](#data-flow)
4. [Technology Choices & Trade-offs](#technology-choices--trade-offs)
5. [Key Design Decisions](#key-design-decisions)
6. [Async Architecture — Dual-Engine Strategy](#async-architecture--dual-engine-strategy)
7. [Deep Dive: Preventing Double-Scheduling with Visibility Timeouts](#deep-dive-preventing-double-scheduling-with-visibility-timeouts)
8. [Database Design](#database-design)
9. [API Design Principles](#api-design-principles)
10. [Observability & Monitoring](#observability--monitoring)
11. [Load Testing & Performance](#load-testing--performance)
12. [Scaling Considerations](#scaling-considerations)
13. [Failure Modes & Recovery](#failure-modes--recovery)
14. [Execution State Machine](#execution-state-machine)
15. [SOLID Principles in Practice](#solid-principles-in-practice)
16. [High-Level Design (HLD)](#high-level-design-hld)
17. [Low-Level Design (LLD)](#low-level-design-lld)
18. [Security Architecture](#security-architecture)
19. [Complete Trade-off Decision Log](#complete-trade-off-decision-log)
20. [Known Limitations](#known-limitations)
21. [Future Improvements](#future-improvements)

---

## Problem Statement

Production systems need reliable, scheduled execution of background tasks — health checks pinging external APIs, data pipeline triggers, periodic report generation, cache invalidation scripts, and more. Off-the-shelf solutions like cron on a single VM offer no retry logic, no visibility into failures, and no horizontal scaling. Managed services (AWS EventBridge, GCP Cloud Scheduler) introduce vendor lock-in and limited customisation.

This project is a **self-hosted, distributed job scheduling platform** that gives teams cron-based scheduling with automatic retries, dead letter queues, per-job rate limiting, and full observability — all running on standard infrastructure (PostgreSQL, Redis, Docker).

---

## Architecture Overview

The system runs as **four independent processes** communicating through PostgreSQL (state) and Redis (queues):

```
                          ┌──────────────────┐
                          │   React Frontend │
                          │   (Nginx / :3000) │
                          └────────┬─────────┘
                                   │ REST / WebSocket
                          ┌────────▼─────────┐
                          │   FastAPI  API    │ ◄─── async SQLAlchemy + asyncpg
                          │   (:8000)         │
                          └──┬──────────┬─────┘
                             │          │
                    ┌────────▼──┐  ┌────▼────────┐
                    │ PostgreSQL │  │    Redis     │
                    │ (state)    │  │  (queues)    │
                    └──┬─────┬──┘  └──┬───────┬──┘
                       │     │        │       │
              ┌────────▼┐  ┌─▼────────▼┐  ┌──▼────────┐
              │Scheduler │  │           │  │  Worker    │ ◄─── sync SQLAlchemy
              │(cron     │  │  Pub/Sub  │  │(dequeue + │      + psycopg2
              │ polling) │  │  channel  │  │ execute)  │
              └──────────┘  └───────────┘  └───────────┘
```

### Why separate processes?

Running the Scheduler, Worker, and API as independent processes provides:

1. **Fault isolation** — A worker crash doesn't bring down the API. The scheduler continues enqueuing even if all workers are restarting.
2. **Independent scaling** — Scale workers horizontally based on queue depth without duplicating the scheduler or API.
3. **Resource separation** — Workers consume CPU (executing HTTP calls). The API is I/O-bound. Different resource profiles benefit from separate containers with tuned resource limits.
4. **Deployment flexibility** — Deploy a worker fix without restarting the API (zero-downtime for users).

**Trade-off:** More Docker containers to manage. Mitigated by Docker Compose for development and the shared codebase (same Python package, different entry points).

---

## Data Flow

**Lifecycle of a single execution:**

```
User creates Job + Schedule via API
           │
           ▼
┌─────────────────────────────┐
│  Scheduler polls PostgreSQL │  (SELECT ... WHERE next_run_at <= now()
│  every 0.5s – 10s (adaptive)│   FOR UPDATE SKIP LOCKED)
└────────────┬────────────────┘
             │ Creates Execution (PENDING), computes next cron time
             │ COMMITS to PostgreSQL first (durability)
             ▼
┌─────────────────────────────┐
│  Redis LPUSH → queue:ready  │  (two-phase: DB commit, then Redis push)
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Worker BRPOPLPUSH          │  (atomic dequeue from ready → processing)
│  queue:ready → processing   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  Rate limit check           │  (sliding window via Redis sorted sets)
│  ├── Allowed → Execute job  │
│  └── Blocked → re-enqueue   │
└────────────┬────────────────┘
             │
     ┌───────┴───────┐
     ▼               ▼
  SUCCESS          FAILURE
     │               │
     │          ┌────┴────┐
     │          ▼         ▼
     │     attempt <    attempt >=
     │     max_retry    max_retry
     │          │         │
     │     RE-ENQUEUE   DEAD LETTER
     │     (backoff)    QUEUE
     │
     ▼
  Pub/Sub → WebSocket → Dashboard
```

---

## Technology Choices & Trade-offs

### Why Redis queues instead of Celery / RabbitMQ?

| Factor | Redis (chosen) | Celery + RabbitMQ |
|--------|---------------|-------------------|
| **Operational overhead** | Zero — Redis already needed for rate limiting | Extra broker + Celery worker processes |
| **Complexity** | ~50 lines of queue logic (BRPOPLPUSH) | Celery adds task decorators, serialisers, result backends |
| **Visibility** | Full control — can inspect queue contents via `LRANGE` | Celery's Flower adds another service |
| **Retry control** | Custom exponential backoff with jitter, per-job policies | Celery has retry, but less granular per-task configuration |
| **Trade-off** | No built-in task routing, priorities, or delivery guarantees beyond at-least-once | Battle-tested for large-scale systems |

**Decision:** For a system processing thousands (not millions) of jobs/day, Redis lists with `BRPOPLPUSH` provide reliable at-least-once delivery with dramatically less complexity. If the system needed priority queues or multi-tenant routing, RabbitMQ would be the right choice.

### Why PostgreSQL instead of MongoDB?

| Factor | PostgreSQL (chosen) | MongoDB |
|--------|--------------------|---------|
| **Data relationships** | Users → Jobs → Schedules → Executions → DLQ form a clear relational graph | Would require denormalisation or `$lookup` aggregations |
| **ACID transactions** | Critical for execution state transitions (PENDING → RUNNING → SUCCESS) — partial updates would corrupt scheduling | Transactions available but less mature |
| **Indexing** | B-tree index on `schedules.next_run_at` for efficient scheduler polling | Would need TTL indexes and compound indexes |
| **Row-level locking** | `SELECT ... FOR UPDATE SKIP LOCKED` enables multiple scheduler instances | No equivalent — would need application-level locking |

**Decision:** The data is inherently relational. A job *has one* schedule, *has many* executions, *has one* retry policy. PostgreSQL's ACID guarantees prevent the scheduler and worker from creating duplicate executions or losing state transitions.

### Why FastAPI instead of Django / Flask?

| Factor | FastAPI (chosen) | Django | Flask |
|--------|-----------------|--------|-------|
| **Async support** | Native `async/await`, async SQLAlchemy + asyncpg | ASGI support added later, less idiomatic | No native async |
| **Auto-documentation** | Swagger UI + ReDoc generated from Pydantic schemas | DRF has browsable API but manual schema config | Requires flask-restx |
| **Validation** | Pydantic models — request validation + response serialisation in one | Serializers are separate from models | No built-in validation |
| **Performance** | Uvicorn ASGI — non-blocking I/O, high concurrency per process | Heavier ORM, middleware stack | Lighter but no async |

**Decision:** FastAPI's native WebSocket support, async SQLAlchemy integration, Pydantic validation, and auto-generated API documentation make it ideal for this API-first system.

---

## Key Design Decisions

### 1. Two-Phase Commit: DB First, Then Redis

When the scheduler creates a new execution:
1. **First:** Insert Execution row into PostgreSQL and COMMIT
2. **Then:** Push execution ID to Redis queue

If the scheduler crashes between steps 1 and 2, the orphan recovery mechanism detects the PENDING execution and re-enqueues it. This ensures **no execution is ever lost**.

The reverse order (Redis first, DB second) would risk enqueuing a job that has no database record, causing the worker to fail with no way to recover.

### 2. Sliding Window Rate Limiting

**Problem:** Prevent a single high-frequency job from overwhelming a target API.

| Approach | Pros | Cons |
|----------|------|------|
| **Token bucket** | Simple counter | Allows bursts at bucket boundaries; race conditions with multiple workers |
| **Sliding window (sorted sets)** | Smooth, no boundary bursts | Slightly more Redis memory per key |

**Implementation:** Each job's rate limit uses a Redis sorted set keyed by `rate_limit:job:{job_id}`. Members are unique request IDs scored by Unix timestamp. Before execution, the worker:
1. Removes entries older than the window (60s default)
2. Counts remaining entries
3. If count >= limit, re-enqueues the job for later

### 3. Exponential Backoff with Jitter

**Retry delay formula:** `base_delay * 2^(attempt - 1)`

With `base_delay = 2s`: attempts retry at 2s, 4s, 8s, 16s...

**Thundering herd prevention:** When the scheduler calculates `next_run_at` for cron schedules, it adds **random jitter of 0-5 seconds**. This prevents hundreds of jobs scheduled at `*/5 * * * *` from all hitting the queue simultaneously.

### 4. Dead Letter Queue with Idempotent Replay

After exhausting all retries, a failed execution is moved to the DLQ with its full context (job ID, execution ID, payload, error message). Users can **replay** DLQ entries from the dashboard.

**Idempotency guard:** Before replaying, the service checks if an in-flight execution already exists for that job. This prevents double-replay from rapid UI clicks.

### 5. Row-Level Locking for Concurrent Safety

The scheduler uses `SELECT ... FOR UPDATE SKIP LOCKED` when querying due schedules:
- **Multiple scheduler instances** can run without double-scheduling
- Locked rows are skipped, not blocked — no contention

The worker uses `SELECT ... FOR UPDATE` on the execution row before processing, preventing race conditions if the same execution is dequeued twice (e.g., after a visibility timeout reset).

---

## Async Architecture — Dual-Engine Strategy

A deliberate architectural choice separates the async and sync database layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI API Server                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  async_engine = create_async_engine("asyncpg://...")      │   │
│  │  AsyncSessionLocal = async_sessionmaker(AsyncSession)     │   │
│  │                                                           │   │
│  │  All route handlers are async def                         │   │
│  │  All DB queries use: await db.execute(select(...))        │   │
│  │  Non-blocking I/O → high concurrency per process          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Scheduler & Worker (separate processes)             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  sync_engine = create_engine("psycopg2://...")            │   │
│  │  SessionLocal = sessionmaker(...)                         │   │
│  │                                                           │   │
│  │  Scheduler: sync loop with time.sleep()                   │   │
│  │  Worker: ThreadPoolExecutor(10) — each thread gets its    │   │
│  │          own sync Session (thread-safe by design)         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Why not async everywhere?**

The worker uses `ThreadPoolExecutor` with 10 concurrent threads, each executing blocking HTTP calls via `httpx.Client`. Mixing async and threaded sync code creates subtle bugs (event loop affinity, session sharing). Keeping the worker fully synchronous with thread-local sessions is simpler and equally performant for CPU-bound job execution.

The API server, by contrast, is I/O-bound — it waits on PostgreSQL and Redis. Async SQLAlchemy + asyncpg lets a single process handle hundreds of concurrent requests without blocking.

**URL auto-detection:** The `db/session.py` module accepts any PostgreSQL URL format and automatically converts between `asyncpg://` and `psycopg2://` for each engine. A single `DATABASE_URL` environment variable drives both engines.

---

## Deep Dive: Preventing Double-Scheduling with Visibility Timeouts

*This section explains the hardest correctness problem in the system and how it's solved.*

### The Problem

In any distributed job scheduler, there's a fundamental tension:

1. **Jobs must run at least once** — if a worker crashes, the job must not be lost.
2. **Jobs should run at most once** — duplicate execution can cause real damage (sending emails twice, double-charging customers, inserting duplicate records).

These two guarantees conflict. Here's a concrete scenario:

```
t=0s    Scheduler creates Execution E1 (PENDING), pushes to Redis
t=1s    Worker A dequeues E1, marks RUNNING, starts HTTP call
t=31s   HTTP call is slow (target server under load)
t=31s   Scheduler scans for stuck executions: E1 is RUNNING for 31s > 30s timeout
t=31s   Scheduler resets E1 to PENDING, re-enqueues to Redis
t=32s   Worker B dequeues E1, marks RUNNING, starts HTTP call
t=33s   Worker A's HTTP call completes — tries to mark E1 as SUCCESS
t=34s   Worker B's HTTP call completes — tries to mark E1 as SUCCESS
```

Now E1 has been executed **twice**, and two workers are racing to update its status.

### The Solution: Three-Layer Defence

**Layer 1: Visibility Timeout (inspired by AWS SQS)**

The scheduler periodically scans for executions that have been in RUNNING state longer than `VISIBILITY_TIMEOUT` (default: 30s). If found, it resets them to PENDING and re-enqueues:

```python
stuck_running = (
    db.query(Execution)
    .filter(
        Execution.status == ExecutionStatus.RUNNING,
        Execution.started_at < now - timedelta(seconds=VISIBILITY_TIMEOUT),
    )
    .all()
)

for execution in stuck_running:
    execution.status = ExecutionStatus.PENDING
    redis_client.lrem(QUEUE_PROCESSING, 0, payload)
    redis_client.lpush(QUEUE_READY, payload)
```

This guarantees **at-least-once delivery**: even if a worker crashes mid-execution, the job eventually runs again.

**Layer 2: Row-Level Locking (prevents the race)**

The worker locks the execution row before processing:

```python
execution = (
    db.query(Execution)
    .filter(Execution.execution_id == execution_id)
    .with_for_update()       # ← exclusive row lock
    .first()
)

if execution.status != ExecutionStatus.PENDING:
    return  # ← another worker already claimed it
```

If Worker B tries to process E1 while Worker A holds the lock, B blocks until A commits. When B's lock succeeds, it sees `status = SUCCESS` (or `RUNNING`), not `PENDING`, and skips the execution. This prevents the double-execution race.

**Layer 3: Status Guard (idempotent state transitions)**

Even without the lock, the worker checks the current status:

```python
if execution.status != ExecutionStatus.PENDING:
    logger.info("Skipping execution, current_state=%s", execution.status)
    return
```

This is a defense-in-depth check. The state machine only allows transitions from PENDING → RUNNING → SUCCESS/FAILED. Any worker that finds a non-PENDING execution exits immediately.

### Why This Works

The three layers interact:

| Scenario | Layer 1 | Layer 2 | Layer 3 | Outcome |
|----------|---------|---------|---------|---------|
| Worker crashes | Timeout → re-enqueue | N/A (worker dead) | New worker starts fresh | Job runs exactly once more |
| Worker slow | Timeout → re-enqueue | Row lock blocks Worker B | B sees RUNNING, skips | Job runs once (A completes) |
| Network partition | Timeout → re-enqueue | Lock may timeout | Status guard prevents dup | At-least-once, no corruption |
| Normal operation | Never triggers | Worker processes normally | Always PENDING | Job runs exactly once |

### The Trade-off

This design provides **at-least-once delivery**, not exactly-once. In the slow-worker scenario, the job *might* execute twice if:
- Worker A's HTTP call succeeds but the DB commit fails
- Worker B has already started a new execution

For this system, at-least-once is the right choice. The jobs are HTTP calls and data transformations — idempotent by nature. If exactly-once were required (financial transactions), we'd need a distributed transaction log or external idempotency keys.

---

## Database Design

### Entity-Relationship Diagram

```
┌──────────────┐        ┌──────────────────┐
│    users     │        │  retry_policies  │
│──────────────│        │──────────────────│
│ id (PK)      │        │ job_id (PK, FK)  │
│ username (UQ)│        │ max_retries      │
│ email (UQ)   │        │ base_delay_secs  │
│ hashed_pass  │        └────────┬─────────┘
│ created_at   │                 │
└──────┬───────┘                 │
       │ 1:N                     │ 1:1
       ▼                         │
┌──────────────┐                 │
│    jobs      │◄────────────────┘
│──────────────│
│ id (PK)      │
│ user_id (FK) │──── INDEX
│ name         │
│ task_type    │
│ payload (JSON)
│ rate_limit   │
│ is_active    │
│ created_at   │
└──┬───────┬───┘
   │       │
   │ 1:1   │ 1:N
   ▼       ▼
┌──────────────┐   ┌──────────────────┐
│  schedules   │   │   executions     │
│──────────────│   │──────────────────│
│ id (PK)      │   │ id (PK)          │
│ job_id (FK)  │   │ job_id (FK)      │──── INDEX
│ cron_expr    │   │ execution_id (UQ)│
│ next_run_at  │──── INDEX (scheduler polling)
│ last_run_at  │   │ status           │
│ status       │   │ attempt          │
│ max_runs     │   │ started_at       │
│ run_count    │   │ finished_at      │
│ created_at   │   │ error            │
└──────────────┘   │ created_at       │
                   └───────┬──────────┘
                           │ 1:1 (on failure)
                           ▼
                   ┌──────────────────┐
                   │ dead_letter_jobs │
                   │──────────────────│
                   │ id (PK)          │
                   │ job_id (FK)      │
                   │ execution_id     │
                   │ payload (JSON)   │
                   │ error            │
                   │ failed_at        │
                   └──────────────────┘
```

### Key Indexing Decisions

| Index | Column | Why |
|-------|--------|-----|
| B-tree | `schedules.next_run_at` | Scheduler polls `WHERE next_run_at <= now()` every 0.5-10s. Without this index, it's a full table scan. |
| B-tree | `executions.job_id` | Worker and DLQ queries filter by job_id. Foreign key index speeds up cascade deletes. |
| Unique | `executions.execution_id` | UUID-based execution lookup from Redis payloads. Uniqueness prevents duplicate entries. |
| B-tree | `jobs.user_id` | Every API query filters by user_id for tenant isolation. |

### Migration Strategy

Alembic manages schema evolution with three migrations:
1. `initial_schema` — Core tables (users, jobs, schedules, executions, DLQ, retry_policies)
2. `add_auth_fields_to_users` — Added `hashed_password` and `email` columns
3. `add_schedule_status_and_limits` — Added `status`, `max_runs`, `run_count` to schedules

All migrations are reversible (`downgrade()` defined) for safe rollbacks.

---

## API Design Principles

### RESTful Resource Hierarchy

```
/api/v1/
├── auth/
│   ├── POST /register          → Create account, return JWT
│   ├── POST /login             → Authenticate, return JWT
│   └── GET  /me                → Current user profile
├── jobs/
│   ├── GET  /                  → List jobs (paginated)
│   ├── POST /                  → Create job
│   ├── GET  /{id}              → Get job details
│   ├── DELETE /{id}            → Delete job (cascades)
│   ├── POST /{id}/schedule     → Attach cron schedule
│   ├── GET  /{id}/schedule     → Get schedule
│   ├── PATCH /{id}/schedule/pause   → Pause schedule
│   ├── PATCH /{id}/schedule/resume  → Resume schedule
│   └── DELETE /{id}/schedule   → Remove schedule
├── admin/dlq/
│   ├── GET  /                  → List DLQ entries (paginated)
│   ├── GET  /user-stats        → Current user's execution stats
│   ├── GET  /global-stats      → Platform-wide stats
│   ├── GET  /execution-history → Daily breakdown
│   ├── GET  /executions        → Execution list (filterable by status)
│   ├── POST /{exec_id}/replay  → Replay failed execution
│   ├── GET  /queues            → Redis queue sizes
│   └── GET  /queues/details    → Queue contents (debug)
└── (monitoring)
    ├── GET  /health            → Postgres + Redis health
    ├── GET  /metrics           → Prometheus scrape endpoint
    └── WS   /ws/executions     → Real-time execution updates
```

### Design Choices

- **URL versioning** (`/api/v1/`) — allows non-breaking evolution
- **Pagination** — all list endpoints return `{items, total, page, size}`
- **Tenant isolation** — every query includes `WHERE user_id = :current_user`
- **Cascade deletes** — deleting a job removes schedules, executions, DLQ entries, retry policies
- **Idempotent replay** — DLQ replay checks for in-flight executions before creating a new one

---

## Observability & Monitoring

### Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `job_executions_total` | Counter | Total executions started |
| `job_success_total` | Counter | Successful completions |
| `job_failure_total` | Counter | Final failures (moved to DLQ) |
| `job_retry_total` | Counter | Retry attempts |
| `job_dlq_total` | Counter | Jobs moved to dead letter queue |
| `queue_ready_size` | Gauge | Jobs waiting in ready queue |
| `queue_processing_size` | Gauge | Jobs currently being processed |
| `queue_failed_size` | Gauge | Jobs in failed queue |
| `running_executions` | Gauge | Currently executing jobs |
| `job_execution_duration_seconds` | Histogram | Execution time distribution (p50, p95, p99) |

### Structured Logging

All logs are emitted as JSON with correlation IDs:

```json
{
  "timestamp": "2025-01-15T10:23:45.123Z",
  "level": "INFO",
  "logger": "worker",
  "message": "Executing job, task_type=api_call",
  "execution_id": "a1b2c3d4-e5f6-...",
  "job_id": 42
}
```

This enables:
- **Log aggregation** — parse JSON in ELK/Loki/CloudWatch
- **Distributed tracing** — follow an execution across scheduler → queue → worker via `execution_id`
- **Alerting** — filter by `level=ERROR` and `logger=worker`

### Real-Time Updates

```
Worker completes execution
    │
    ▼
Redis PUBLISH "execution:updates" {status, user_id, ...}
    │
    ▼
API server's Redis listener (async background task)
    │
    ▼
WebSocket broadcast to user's active connections
    │
    ▼
React dashboard updates execution table in real-time
```

Fallback: If WebSocket connection fails, the frontend polls the execution API.

---

## Load Testing & Performance

### Setup

Load tests use [Locust](https://locust.io/) to simulate realistic user workflows:

```bash
locust -f loadtest/locustfile.py --headless \
    -u 50 -r 10 --run-time 60s \
    --host http://localhost:8000
```

### Results (50 concurrent users, 60s, single API instance)

| Endpoint | Requests | Median | p95 | p99 | Failures | RPS |
|----------|----------|--------|-----|-----|----------|-----|
| POST /auth/register | ~60 | 45ms | 120ms | 180ms | 0% | 1.0 |
| POST /auth/login | ~60 | 40ms | 110ms | 160ms | 0% | 1.0 |
| GET /jobs | ~900 | 12ms | 35ms | 60ms | 0% | 15.0 |
| POST /jobs | ~450 | 18ms | 50ms | 85ms | 0% | 7.5 |
| GET /jobs/{id} | ~450 | 10ms | 30ms | 55ms | 0% | 7.5 |
| POST /jobs/{id}/schedule | ~300 | 22ms | 60ms | 100ms | 0% | 5.0 |
| GET /dlq/user-stats | ~600 | 8ms | 25ms | 45ms | 0% | 10.0 |
| GET /dlq/global-stats | ~600 | 6ms | 20ms | 40ms | 0% | 10.0 |
| GET /health | ~300 | 5ms | 15ms | 30ms | 0% | 5.0 |
| **TOTAL** | **~3720** | **14ms** | **50ms** | **100ms** | **0%** | **62.0** |

**Key takeaways:**
- **62 requests/second** sustained throughput with a single API process
- **p95 < 50ms** for read-heavy endpoints (job listing, stats)
- **Zero failures** under sustained 50-user load
- Auth endpoints are slowest due to bcrypt hashing (by design — security over speed)
- async SQLAlchemy + asyncpg keeps read latencies low even under concurrency

### Bottleneck Analysis

| Bottleneck | Impact | Mitigation |
|------------|--------|------------|
| bcrypt hashing | ~40ms per auth request | Expected — security cost. Cache JWT, minimize re-auth. |
| PostgreSQL writes | ~15-20ms per INSERT | Connection pooling (10 connections, 20 overflow). |
| Single process | ~62 RPS ceiling | Add `--workers 2-4` in production (Uvicorn multiprocess). |

---

## Scaling Considerations

### Current Architecture Limits

| Component | Bottleneck | Current Capacity | Scale Path |
|-----------|-----------|------------------|------------|
| **API** | Single process | ~62 RPS | Uvicorn `--workers N`, load balancer |
| **Scheduler** | Single-threaded poll | ~100 schedules/sec | `SKIP LOCKED` supports multiple instances |
| **Worker** | 10 threads per container | ~10 concurrent jobs | Add worker containers; increase `MAX_WORKERS` |
| **PostgreSQL** | Central state store | ~1000 writes/sec | Read replicas for API; PgBouncer for connection pooling |
| **Redis** | Single-threaded | ~100k ops/sec | Redis Cluster; separate instances for queues vs rate limiting |

### Horizontal Scaling Path

```
Current:     1 API  |  1 Scheduler  |  1 Worker   |  1 PostgreSQL  |  1 Redis
               ↓           ↓              ↓              ↓              ↓
Scale to:    N APIs |  2 Schedulers |  M Workers  |  1 PG + replicas | Redis Cluster
             (LB)    (SKIP LOCKED)  (BRPOPLPUSH)   (read replicas)   (sharded)
```

- **API:** Stateless — add more containers behind a load balancer
- **Scheduler:** Run 2 for HA; `SKIP LOCKED` prevents duplicate scheduling
- **Workers:** Add containers; Redis `BRPOPLPUSH` distributes work automatically
- **Database:** Read replicas for API queries; primary for scheduler/worker writes

---

## Failure Modes & Recovery

| Failure | Detection | Recovery | Data Loss? |
|---------|-----------|----------|------------|
| Worker crash mid-execution | Visibility timeout (30s) | Scheduler re-enqueues | No — execution replayed |
| Scheduler crash | No new executions created | Restart; backlog processed on recovery | No — schedules still in DB |
| Redis crash | Health check fails; workers block on BRPOPLPUSH | Restart Redis; orphan recovery re-enqueues from DB | No — DB is source of truth |
| PostgreSQL crash | Health check fails; all services error | Restart PG; services reconnect (pool_pre_ping) | No — WAL ensures durability |
| Network partition (API ↔ DB) | Connection timeout | pool_pre_ping detects; new connection from pool | No — failed requests return 500 |
| Duplicate execution | Status guard + row lock | Second worker skips (status != PENDING) | No — idempotent |

---

## Execution State Machine

The execution lifecycle follows a strict state machine with guarded transitions. Every state change is validated — no transition can skip a state or move backwards.

```
                    ┌─────────────────────────────────────────────────┐
                    │                                                 │
                    │         EXECUTION STATE MACHINE                 │
                    │                                                 │
                    │   ┌─────────┐                                   │
                    │   │ PENDING │◄─────── Scheduler creates         │
                    │   └────┬────┘         (initial state)           │
                    │        │                                        │
                    │        │ Worker dequeues                        │
                    │        │ + row lock acquired                    │
                    │        │ + rate limit passed                    │
                    │        ▼                                        │
                    │   ┌─────────┐                                   │
                    │   │ RUNNING │◄─────── started_at = now()        │
                    │   └────┬────┘         WebSocket: "RUNNING"      │
                    │        │                                        │
                    │   ┌────┴────────┐                               │
                    │   │             │                                │
                    │   ▼             ▼                                │
                    │ ┌─────────┐  ┌────────┐                         │
                    │ │ SUCCESS │  │ FAILED │                         │
                    │ └─────────┘  └───┬────┘                         │
                    │                  │                               │
                    │          ┌───────┴───────┐                      │
                    │          │               │                      │
                    │          ▼               ▼                      │
                    │   attempt < max    attempt >= max               │
                    │          │               │                      │
                    │          ▼               ▼                      │
                    │   ┌─────────┐    ┌──────────────┐              │
                    │   │ PENDING │    │ DEAD LETTER  │              │
                    │   │ (retry) │    │ QUEUE        │              │
                    │   └─────────┘    └──────┬───────┘              │
                    │                         │                      │
                    │                    User replays                 │
                    │                         │                      │
                    │                    ┌────▼────┐                  │
                    │                    │ PENDING │ (new exec ID)    │
                    │                    └─────────┘                  │
                    └─────────────────────────────────────────────────┘

Allowed transitions:
    PENDING  → RUNNING   (worker claims execution)
    RUNNING  → SUCCESS   (job completed successfully)
    RUNNING  → PENDING   (retry after failure, attempt < max_retries)
    RUNNING  → FAILED    (final failure, attempt >= max_retries → DLQ)
    PENDING  ← recovery  (orphan recovery re-enqueues stuck executions)

Forbidden transitions (enforced by status guard):
    SUCCESS  → anything  (terminal state)
    FAILED   → anything  (terminal state, replay creates NEW execution)
    RUNNING  → RUNNING   (prevented by row lock)
```

**Guard conditions at each transition:**

| Transition | Guard | Implementation |
|------------|-------|----------------|
| PENDING → RUNNING | Row lock (`FOR UPDATE`) + status == PENDING | `worker.py:process_execution()` |
| RUNNING → SUCCESS | Job executor returned without exception | `worker.py:process_execution()` |
| RUNNING → PENDING (retry) | `attempt < max_retries` | `worker.py:handle_failure()` |
| RUNNING → FAILED (DLQ) | `attempt >= max_retries` | `worker.py:handle_failure()` |
| DLQ → PENDING (replay) | No in-flight execution exists for job | `dlq_service.py:replay_dlq_execution()` |

---

## SOLID Principles in Practice

This section maps each SOLID principle to concrete implementation decisions in the codebase.

### S — Single Responsibility Principle

Each module has exactly one reason to change:

| Module | Responsibility | What it does NOT do |
|--------|---------------|---------------------|
| `scheduler/scheduler.py` | Detect due schedules, create executions | Does NOT execute jobs |
| `worker/worker.py` | Dequeue and orchestrate execution | Does NOT compute cron times |
| `worker/executor.py` | Execute job payloads (HTTP, string, math) | Does NOT handle retries or DLQ |
| `api/jobs.py` | CRUD for job resources | Does NOT contain scheduling logic |
| `queues/rate_limiter.py` | Sliding window rate limiting | Does NOT know about jobs or executions |
| `websocket/connection_manager.py` | WebSocket lifecycle management | Does NOT parse messages or query DB |
| `services/dlq_service.py` | DLQ replay business logic | Does NOT expose HTTP endpoints |

**Why this matters:** When the retry algorithm changes, only `handle_failure()` in `worker.py` is modified. When a new job type is added, only `executor.py` changes. No shotgun surgery.

### O — Open/Closed Principle

The job execution system is **open for extension** (new job types) but **closed for modification** (existing dispatch logic):

```python
# executor.py — adding a new job type requires NO changes to existing code
def execute_job(job: Job) -> dict:
    if job.task_type == "api_call":
        return _execute_api_call(job)
    elif job.task_type == "string_manipulation":
        return _execute_string(job)
    elif job.task_type == "math":
        return _execute_math(job)
    # Adding "email" or "webhook" only requires a new elif + function
```

The rate limiter is generic — it accepts any `key` string. Adding rate limiting to a new resource (API endpoints, user actions) requires no changes to `rate_limiter.py`.

### L — Liskov Substitution Principle

The dual-engine database strategy follows LSP: both async and sync sessions expose the same query interface. The `SyncToAsyncSessionWrapper` in tests substitutes a sync session where an async one is expected, enabling integration tests with in-memory SQLite.

### I — Interface Segregation Principle

API endpoints are split into focused routers rather than one monolithic controller:

- `api/auth.py` — Authentication only (3 endpoints)
- `api/jobs.py` — Job CRUD only (4 endpoints)
- `api/schedules.py` — Schedule management only (5 endpoints)
- `api/admin_dlq.py` — DLQ + stats only (8 endpoints)

Each router depends only on the models it needs. The DLQ router doesn't import Schedule; the jobs router doesn't import DeadLetterJob.

### D — Dependency Inversion Principle

High-level modules don't depend on low-level implementations:

- **Worker → Executor:** The worker calls `execute_job(job)` without knowing the implementation details of HTTP calls, string operations, or math evaluation.
- **API → Database:** Route handlers depend on `AsyncSession` (abstraction), not on PostgreSQL-specific code. Tests substitute SQLite sessions seamlessly.
- **Scheduler → Queue:** The scheduler calls `redis_client.lpush()` — a Redis interface. The scheduler doesn't know the queue's internal data structure.
- **FastAPI Depends():** All route handlers receive their dependencies (DB session, current user) via injection, not direct import.

---

## High-Level Design (HLD)

### System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          External World                                  │
│                                                                         │
│   ┌──────────┐    ┌─────────────┐    ┌────────────┐                    │
│   │  Users   │    │ Target APIs │    │ Prometheus │                    │
│   │(browser) │    │(job targets)│    │ + Grafana  │                    │
│   └────┬─────┘    └──────▲──────┘    └──────▲─────┘                    │
│        │                 │                  │                           │
└────────┼─────────────────┼──────────────────┼───────────────────────────┘
         │ HTTPS           │ HTTP             │ /metrics
         ▼                 │                  │
┌────────────────────────────────────────────────────────────────────────┐
│                     Job Scheduler Platform                              │
│                                                                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐             │
│  │ Frontend │  │   API    │  │ Scheduler │  │  Worker  │             │
│  │ (React)  │──│ (FastAPI)│  │  (cron)   │  │ (exec)   │             │
│  └──────────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘             │
│                     │              │              │                    │
│              ┌──────▼──────────────▼──────────────▼──────┐            │
│              │         Infrastructure Layer              │            │
│              │  ┌────────────┐    ┌─────────────┐       │            │
│              │  │ PostgreSQL │    │    Redis     │       │            │
│              │  │  (state)   │    │  (queues +   │       │            │
│              │  │            │    │  rate limit + │       │            │
│              │  │            │    │  pub/sub)     │       │            │
│              │  └────────────┘    └─────────────┘       │            │
│              └──────────────────────────────────────────┘            │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction Matrix

| From ↓ / To → | PostgreSQL | Redis | API | Scheduler | Worker | Frontend |
|----------------|-----------|-------|-----|-----------|--------|----------|
| **API** | Read/Write (async) | Pub/Sub listen, Queue inspect | — | — | — | REST + WS |
| **Scheduler** | Read/Write (sync) | LPUSH to queue | — | — | — | — |
| **Worker** | Read/Write (sync) | BRPOPLPUSH, rate limit, PUBLISH | — | — | — | — |
| **Frontend** | — | — | REST + WS | — | — | — |

### Non-Functional Requirements

| Requirement | Target | How Achieved |
|-------------|--------|--------------|
| **Availability** | Scheduler and worker tolerate single-node failures | Orphan recovery re-enqueues lost jobs |
| **Latency** | API p95 < 50ms | Async I/O, connection pooling, indexed queries |
| **Throughput** | 60+ RPS per API process | Uvicorn ASGI, asyncpg, no blocking calls |
| **Durability** | Zero data loss on component crash | PostgreSQL as source of truth, WAL, two-phase commit |
| **Consistency** | No double-execution under normal operation | Three-layer defence (timeout + lock + guard) |
| **Observability** | Full execution tracing | Structured JSON logs, Prometheus metrics, correlation IDs |

---

## Low-Level Design (LLD)

### Worker Thread Pool Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Worker Process                             │
│                                                              │
│  Main Thread                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  while not SHUTDOWN:                                 │    │
│  │    task = redis.BRPOPLPUSH(ready, processing, 5s)   │    │
│  │    if task:                                          │    │
│  │      executor.submit(handle_task, task)              │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│               ┌───────────┼───────────┐                     │
│               ▼           ▼           ▼                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │  Thread 1    │ │  Thread 2    │ │  Thread N    │ (N=10) │
│  │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │        │
│  │  │Session │  │ │  │Session │  │ │  │Session │  │        │
│  │  │(own DB)│  │ │  │(own DB)│  │ │  │(own DB)│  │        │
│  │  └────────┘  │ │  └────────┘  │ │  └────────┘  │        │
│  │              │ │              │ │              │        │
│  │  1. Lock row │ │  1. Lock row │ │  1. Lock row │        │
│  │  2. Rate chk │ │  2. Rate chk │ │  2. Rate chk │        │
│  │  3. Execute  │ │  3. Execute  │ │  3. Execute  │        │
│  │  4. Update   │ │  4. Update   │ │  4. Update   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘

Key design: Each thread creates its own SQLAlchemy Session.
This avoids session sharing bugs — sessions are NOT thread-safe.
The ThreadPoolExecutor caps concurrency at MAX_WORKERS (configurable).
```

### Scheduler Adaptive Polling Algorithm

```python
# Pseudocode for adaptive backoff:
sleep_seconds = 0.5  # MIN_SLEEP

while not SHUTDOWN:
    processed = run_scheduler_once(db)

    if processed > 0:
        sleep_seconds = 0.5        # Reset to fast polling (jobs are active)
    else:
        sleep_seconds = min(
            sleep_seconds * 1.5,   # Exponential slowdown
            10.0                    # MAX_SLEEP cap
        )

    # Periodic recovery (every 30s)
    if time_since_last_recovery >= 30:
        recover_orphaned_executions(db)

    time.sleep(sleep_seconds)
```

**Why adaptive?** Fixed polling (e.g., every 1s) wastes CPU when no schedules are due. Adaptive backoff polls fast during active periods and slows down when idle — reducing database load by up to 20x during quiet hours.

### Rate Limiter — Sliding Window Implementation

```
Redis sorted set: rate_limit:job:{job_id}

    Score (Unix timestamp)          Member (unique ID)
    ┌──────────────────────────────────────────────────┐
    │  1705312800  →  "1705312800:a3f2b1c4"           │
    │  1705312815  →  "1705312815:9e8d7f6a"           │
    │  1705312830  →  "1705312830:1b2c3d4e"           │
    │  1705312845  →  "1705312845:5f6a7b8c"           │
    └──────────────────────────────────────────────────┘

    Window: [now - 60s ... now]

    Pipeline (atomic):
    1. ZREMRANGEBYSCORE key 0 (now - window)   # Remove expired
    2. ZCARD key                                # Count remaining
    3. ZADD key {unique_member: now}            # Record this request
    4. EXPIRE key window                        # Auto-cleanup

    If ZCARD >= limit → rate limited (re-enqueue job)
```

**Why unique members?** Redis sorted set members must be unique. If two requests arrive in the same second and use the timestamp as the member, the second would overwrite the first (under-counting). Appending a random suffix ensures each request is counted independently.

### WebSocket Connection Lifecycle

```
Client                    API Server                    Redis
  │                           │                           │
  │──── WS upgrade ──────────▶│                           │
  │     ?token=JWT            │                           │
  │                           │── decode_token(JWT)       │
  │                           │── validate user_id        │
  │                           │                           │
  │◄──── WS accept ──────────│                           │
  │                           │── manager.connect(        │
  │                           │     user_id, websocket)   │
  │                           │                           │
  │                           │         ┌─────────────────│
  │                           │         │ SUBSCRIBE       │
  │                           │         │ execution:updates│
  │                           │         │                 │
  │    (Worker completes)     │         │                 │
  │                           │         │◄── PUBLISH ─────│
  │                           │── parse message           │
  │                           │── filter by user_id       │
  │◄──── JSON message ───────│                           │
  │    {type, payload}        │                           │
  │                           │                           │
  │──── disconnect ──────────▶│                           │
  │                           │── manager.disconnect()    │
  │                           │                           │
```

---

## Security Architecture

### Authentication Flow

```
Register:
  Client → POST /auth/register {username, email, password}
                                   │
                           ┌───────▼───────┐
                           │ Rate limit    │ (10 req/min per IP)
                           │ check         │
                           └───────┬───────┘
                                   │
                           ┌───────▼───────┐
                           │ Pydantic      │ (min 8 chars, uppercase,
                           │ validation    │  lowercase, digit required)
                           └───────┬───────┘
                                   │
                           ┌───────▼───────┐
                           │ bcrypt hash   │ (12 rounds, random salt)
                           │ password      │
                           └───────┬───────┘
                                   │
                           ┌───────▼───────┐
                           │ JWT token     │ (HS256, 24h expiry)
                           │ generation    │
                           └───────┬───────┘
                                   │
  Client ◄──── {access_token, user} ┘
```

### Security Measures

| Layer | Measure | Implementation |
|-------|---------|----------------|
| **Transport** | CORS origin whitelist | `CORSMiddleware` with explicit origins, methods, headers |
| **Authentication** | JWT with expiration | HS256 signing, 24-hour TTL, `sub` claim = user ID |
| **Brute force** | Auth rate limiting | 10 attempts/minute per IP, sliding window, `429 Too Many Requests` |
| **Password** | Complexity rules + bcrypt | Min 8 chars, uppercase + lowercase + digit, bcrypt with salt |
| **Authorization** | Tenant isolation | Every query: `WHERE user_id = :current_user_id` |
| **Injection** | ORM parameterization | SQLAlchemy ORM — no raw SQL, no string concatenation |
| **Input validation** | Pydantic schemas | Strict type checking, regex patterns on math expressions, whitelisted methods |
| **Error exposure** | Structured error codes | Internal errors return `error_code` without stack traces |
| **Tracing** | Correlation IDs | `X-Request-ID` header on every request/response |

### Structured Error Responses

All API errors follow a consistent format for frontend parsing:

```json
{
    "detail": {
        "error_code": "JOB_NOT_FOUND",
        "message": "Job not found"
    }
}
```

Error codes: `USERNAME_TAKEN`, `EMAIL_TAKEN`, `INVALID_CREDENTIALS`, `JOB_NOT_FOUND`, `SCHEDULE_EXISTS`, `SCHEDULE_NOT_FOUND`, `INVALID_CRON`, `SCHEDULE_COMPLETED`, `SCHEDULE_NOT_PAUSED`, `INTERNAL_ERROR`

---

## Complete Trade-off Decision Log

Every engineering decision involves trade-offs. This section documents the reasoning behind each choice.

| # | Decision | Chosen | Alternative | Why |
|---|----------|--------|-------------|-----|
| 1 | **Message broker** | Redis lists (BRPOPLPUSH) | Celery + RabbitMQ | Redis already required for rate limiting; ~50 LOC vs framework overhead; at-least-once delivery sufficient |
| 2 | **Database** | PostgreSQL | MongoDB | Data is relational (User→Job→Schedule→Execution); ACID needed for state transitions; `FOR UPDATE SKIP LOCKED` has no MongoDB equivalent |
| 3 | **API framework** | FastAPI | Django REST / Flask | Native async, Pydantic validation, auto-generated OpenAPI docs, WebSocket support |
| 4 | **API async strategy** | Async SQLAlchemy + asyncpg | Sync SQLAlchemy everywhere | API is I/O-bound; async allows hundreds of concurrent requests per process |
| 5 | **Worker async strategy** | Sync SQLAlchemy + ThreadPoolExecutor | Async everywhere | Workers execute blocking HTTP calls; mixing async + threads causes event loop bugs; thread-per-session is simpler |
| 6 | **Commit order** | DB first, then Redis | Redis first, then DB | If crash between steps: orphan recovery re-enqueues from DB; reverse would leave phantom queue entries |
| 7 | **Rate limiter algorithm** | Sliding window (sorted sets) | Token bucket / Fixed window | No boundary burst problem; smooth rate enforcement; slightly more Redis memory (acceptable) |
| 8 | **Delivery guarantee** | At-least-once | Exactly-once | Exactly-once requires distributed transactions or idempotency keys; at-least-once with status guards is simpler and sufficient for HTTP calls |
| 9 | **Process architecture** | Separate processes (API, Scheduler, Worker) | Monolith | Fault isolation, independent scaling, different resource profiles; trade-off: more containers |
| 10 | **Scheduler polling** | Adaptive backoff (0.5s–10s) | Fixed interval | Reduces DB load by up to 20x during idle periods; fast response during active periods |
| 11 | **Double-scheduling prevention** | Three-layer defence (timeout + lock + guard) | Single lock | Defense in depth: each layer covers failure modes the others miss |
| 12 | **Orphan recovery** | Scheduler-driven periodic scan | Worker heartbeats | Simpler: no extra protocol between workers; scheduler already has DB access |
| 13 | **Retry backoff** | Exponential (2^attempt) | Linear / Fixed delay | Prevents overwhelming recovering services; back-pressure grows with failure severity |
| 14 | **Cron jitter** | Random 0-5s offset | No jitter | Prevents thundering herd when many jobs share the same cron expression |
| 15 | **Job execution timeout** | Thread with `join(timeout)` | `asyncio.wait_for` / `signal.alarm` | Works in ThreadPoolExecutor; `signal.alarm` is main-thread only; `asyncio` requires async executor |
| 16 | **Auth tokens** | JWT (stateless) | Session-based (stateful) | Stateless: no server-side session store; horizontal scaling without sticky sessions |
| 17 | **Password hashing** | bcrypt (12 rounds) | argon2 / scrypt | bcrypt is battle-tested, widely supported; 12 rounds = ~40ms (good balance of security vs latency) |
| 18 | **Frontend state** | TanStack Query (server state) + Context (auth) | Redux / Zustand | Most state is server-derived; TanStack Query handles caching, invalidation, refetching; no need for client-side store |
| 19 | **WebSocket transport** | Redis pub/sub → WebSocket | Polling / SSE | Real-time updates without polling overhead; Redis pub/sub scales across API instances |
| 20 | **Database migrations** | Alembic (explicit) | Django auto-migrations | Full control over migration SQL; reversible `downgrade()` for safe rollbacks |
| 21 | **API versioning** | URL prefix (`/api/v1/`) | Header-based / Content negotiation | Explicit, visible in URLs, easy to route at load balancer level |
| 22 | **Cascade deletes** | Application-level (explicit DELETE queries) | Database-level ON DELETE CASCADE | Explicit control over deletion order; can add soft-delete later without schema change |
| 23 | **Connection pooling** | SQLAlchemy pool (10 + 20 overflow) | PgBouncer | Built-in, no extra service; `pool_pre_ping` detects stale connections |
| 24 | **Test database** | In-memory SQLite + FakeRedis | PostgreSQL testcontainers | Fast test execution (21s for 319 tests); no Docker dependency for CI; trade-off: can't test PG-specific features |
| 25 | **Structured logging** | JSON with correlation fields | Plain text / ELK-specific | Machine-parseable; works with any log aggregator; correlation IDs enable distributed tracing |
| 26 | **Frontend build** | Vite | Create React App / Webpack | 10x faster HMR; native ESM; minimal configuration |
| 27 | **CSS framework** | Tailwind CSS 4 | Styled Components / CSS Modules | Utility-first; no context switching between files; tree-shaken to minimal CSS |
| 28 | **Auth rate limiting** | In-memory sliding window per IP | Redis-based / External WAF | Simple for single-process; no Redis dependency for auth path; sufficient for current scale |
| 29 | **Error response format** | Structured `{error_code, message}` | Plain string detail | Frontend can programmatically handle specific errors; i18n-ready |
| 30 | **Correlation IDs** | X-Request-ID middleware (auto-generated UUID) | OpenTelemetry | Lightweight; no external dependency; traces requests across logs and responses |

---

## Known Limitations

| Limitation | Impact | Mitigation Path |
|------------|--------|-----------------|
| **At-least-once delivery** | Jobs may execute twice under extreme failure conditions | Add external idempotency keys for critical workloads |
| **Single Redis instance** | Redis is SPOF for queue operations | Redis Sentinel or Cluster for HA |
| **In-memory auth rate limiter** | Rate limits don't persist across API restarts; not shared across multiple API instances | Move to Redis-based rate limiting when scaling API horizontally |
| **No job prioritisation** | All jobs dequeued FIFO from single queue | Add priority queues (multiple Redis lists with weighted dequeue) |
| **Frontend is JavaScript, not TypeScript** | No compile-time type safety for frontend code | Migrate to TypeScript (planned) |
| **No exactly-once semantics** | Not suitable for financial transactions without external idempotency | Add idempotency key support (tracked in Future Improvements) |

---

## Future Improvements

- **Kubernetes deployment** — Helm chart with HPA based on `queue_ready_size` metric
- **OpenTelemetry tracing** — End-to-end distributed tracing across scheduler → queue → worker
- **Job chaining / DAGs** — Run jobs in sequence (Job A output → Job B input)
- **Webhook notifications** — Notify external systems on job success/failure
- **Multi-tenancy** — Organisation-level isolation with resource quotas
- **Priority queues** — Multiple Redis lists with weighted dequeue
- **Execution log streaming** — Stream stdout/stderr of jobs to the dashboard in real-time
- **Exactly-once semantics** — External idempotency key support for financial workloads
