# Job Scheduler

A distributed, self-hosted job scheduling platform built with FastAPI, PostgreSQL, and Redis.

Supports cron-based scheduling, automatic retries with exponential backoff, dead letter queues, sliding window rate limiting, real-time WebSocket updates, and Prometheus observability — all orchestrated as independent processes via Docker Compose.

## Architecture

```
┌────────────┐      ┌───────────────────┐      ┌───────────┐
│  React UI  │─────▶│  FastAPI API       │─────▶│ PostgreSQL│
│  (Vite)    │ WS   │  (async SQLAlchemy │      │  (state)  │
└────────────┘      │   + asyncpg)       │      └───────────┘
                    └──────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │    Redis     │
                    │  (queues +   │
                    │  rate limit) │
                    └──┬───────┬──┘
                       │       │
              ┌────────▼┐  ┌──▼────────┐
              │Scheduler│  │  Worker   │
              │(cron →  │  │(dequeue → │
              │ enqueue)│  │ execute)  │
              └─────────┘  └──────────┘
```

| Process | Role |
|---------|------|
| **API** | Async REST endpoints + WebSocket. Uses `asyncpg` for non-blocking PostgreSQL access. |
| **Scheduler** | Polls for due cron schedules, creates execution records, enqueues to Redis. Uses `FOR UPDATE SKIP LOCKED` for multi-instance safety. |
| **Worker** | Dequeues jobs via `BRPOPLPUSH`, executes them (HTTP calls, string ops, math), retries with backoff, routes failures to DLQ. |
| **Frontend** | React 19 SPA with TanStack Query, real-time execution updates via WebSocket. |

## Key Features

- **Cron scheduling** — standard expressions, pause/resume, max-runs limit, thundering herd jitter
- **Automatic retries** — exponential backoff (`2^attempt` seconds), per-job retry policies
- **Dead letter queue** — failed jobs preserved with context, one-click idempotent replay
- **Sliding window rate limiting** — Redis sorted sets, per-job configurable requests/minute
- **Visibility timeout & orphan recovery** — detects stuck/crashed workers, re-enqueues automatically
- **Real-time updates** — Redis pub/sub → WebSocket push to React dashboard
- **Prometheus metrics** — execution counts, durations (p50/p95/p99), queue sizes
- **Correlation ID middleware** — auto-generated `X-Request-ID` header on every request for distributed tracing
- **Structured error responses** — machine-readable error codes (`JOB_NOT_FOUND`, `SCHEDULE_EXISTS`, etc.) for frontend error handling
- **Auth security** — password complexity enforcement (uppercase, lowercase, digit, 8-128 chars), per-IP sliding window rate limiting on login/register
- **Multi-tenant isolation** — users see only their own jobs, schedules, and executions
- **Async API layer** — async SQLAlchemy + asyncpg for high-concurrency, non-blocking I/O
- **Graceful shutdown** — worker drains in-flight tasks; scheduler finishes current cycle

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **API** | Python 3.13, FastAPI, async SQLAlchemy 2 + asyncpg, Pydantic 2 |
| **Background** | Scheduler + Worker (sync SQLAlchemy + psycopg2, ThreadPoolExecutor) |
| **Queue** | Redis 7 — custom `BRPOPLPUSH` implementation (at-least-once delivery) |
| **Database** | PostgreSQL 16, Alembic migrations |
| **Frontend** | React 19, Vite 7, TanStack Query v5, TanStack Table v8, Tailwind CSS 4, Recharts |
| **Infra** | Docker Compose (dev + prod), GitHub Actions CI, Nginx |

## Quick Start

### Docker (recommended)

```bash
cp .env.docker.example .env.docker

# Generate a JWT secret:
python -c "import secrets; print(secrets.token_hex(32))"
# Paste it into .env.docker as JWT_SECRET_KEY

docker compose up --build
```

| URL | Description |
|-----|-------------|
| http://localhost:3000 | React dashboard |
| http://localhost:8000/docs | Swagger UI (interactive API docs) |
| http://localhost:8000/redoc | ReDoc (alternative API docs) |
| http://localhost:8000/health | Health check (Postgres + Redis) |
| http://localhost:8000/metrics | Prometheus scrape endpoint |

### Local Development

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example app/.env          # edit with your Postgres & Redis URLs

cd app
alembic upgrade head
uvicorn main:app --reload          # API on :8000
python -m scheduler.main           # terminal 2
python -m worker.main              # terminal 3

# Frontend
cd frontend && npm install && npm run dev   # :5173
```

## API Reference

All endpoints under `/api/v1`. Authenticated endpoints require `Authorization: Bearer <JWT>`.

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | - | Create account, returns JWT |
| POST | `/auth/login` | - | Authenticate, returns JWT |
| GET | `/auth/me` | JWT | Current user profile |

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/jobs` | List jobs (paginated: `?page=1&size=20`) |
| POST | `/jobs` | Create job (api_call, string_manipulation, or math) |
| GET | `/jobs/{id}` | Get job details |
| DELETE | `/jobs/{id}` | Delete job (cascades to schedules, executions, DLQ) |

### Schedules

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/jobs/{id}/schedule` | Attach cron schedule |
| GET | `/jobs/{id}/schedule` | Get schedule details |
| PATCH | `/jobs/{id}/schedule/pause` | Pause schedule |
| PATCH | `/jobs/{id}/schedule/resume` | Resume schedule |
| DELETE | `/jobs/{id}/schedule` | Remove schedule |

### Dead Letter Queue & Stats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/dlq/` | List DLQ entries (paginated) |
| POST | `/admin/dlq/{execution_id}/replay` | Replay failed execution (idempotent) |
| GET | `/admin/dlq/user-stats` | Current user's execution stats |
| GET | `/admin/dlq/global-stats` | Platform-wide execution stats |
| GET | `/admin/dlq/execution-history` | Daily success/failure breakdown |
| GET | `/admin/dlq/executions` | Execution list (filterable: `?status=FAILED`) |
| GET | `/admin/dlq/queues` | Redis queue sizes |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Postgres + Redis health check |
| GET | `/metrics` | Prometheus metrics |
| WS | `/ws/executions?token=JWT` | Real-time execution updates |

## Project Structure

```
├── app/
│   ├── main.py                 # FastAPI entry point (async)
│   ├── auth.py                 # JWT auth (async get_current_user)
│   ├── config.py               # Environment-driven configuration
│   ├── api/                    # Async route handlers
│   │   ├── auth.py             #   Registration, login, rate limiting
│   │   ├── jobs.py             #   CRUD + cascade delete
│   │   ├── schedules.py        #   Cron management
│   │   ├── admin_dlq.py        #   DLQ, stats, queue inspection
│   │   └── metrics.py          #   Worker metrics proxy
│   ├── db/
│   │   ├── session.py          #   Dual-engine: async (API) + sync (worker)
│   │   ├── base.py             #   SQLAlchemy DeclarativeBase
│   │   ├── models/             #   ORM models
│   │   └── migrations/         #   Alembic versions
│   ├── schemas/                # Pydantic request/response models
│   ├── services/               # Business logic (async DLQ replay)
│   ├── scheduler/              # Cron scheduler process (sync)
│   │   ├── runner.py           #   Adaptive polling loop
│   │   └── scheduler.py        #   Due detection + orphan recovery
│   ├── worker/                 # Queue worker process (sync)
│   │   ├── worker.py           #   ThreadPoolExecutor loop
│   │   └── executor.py         #   Job type dispatchers
│   ├── queues/                 # Redis client + sliding window rate limiter
│   ├── websocket/              # Connection manager + Redis pub/sub listener
│   ├── metrics/                # Prometheus counters, gauges, histograms
│   └── tests/                  # 18 test files (unit, integration, scheduler, worker)
├── frontend/                   # React 19 SPA
├── loadtest/
│   └── locustfile.py           # Locust load test (50 users, 62 RPS)
├── docker-compose.yml          # Development
├── docker-compose.prod.yml     # Production (resource limits, restart policies)
├── Dockerfile                  # Python 3.13-slim, multi-service
├── .github/workflows/ci.yml   # Lint, test, build, Docker
├── DESIGN.md                   # System design & trade-off decisions
├── requirements.txt
├── .env.example                # Local dev template
├── .coveragerc                 # Coverage configuration (pytest-cov)
├── pytest.ini                  # Test runner config (coverage enabled)
├── .env.docker.example         # Docker template
└── .env.prod.example           # Production template
```

## Testing

```bash
cd app && pytest -v              # 319 tests, 92% line coverage
cd frontend && npm test          # 219 tests (Vitest + React Testing Library)
```

Tests run against in-memory SQLite (sync for scheduler/worker, async via aiosqlite for API) and a dict-backed FakeRedis — no external services required. Coverage is reported automatically via `pytest-cov`.

| Category | Tests | Coverage |
|----------|-------|----------|
| **Unit** | Auth, models, schemas, logging, rate limiter, config, executor | Password complexity, validation rules, structured error codes |
| **Integration** | Full lifecycle: register → create job → schedule → execute → DLQ | Auth rate limiting, correlation IDs |
| **Scheduler** | Due detection, orphan recovery, max_runs, adaptive backoff | Adaptive polling, jitter |
| **Worker** | Execution, retries, DLQ routing, rate limiting, timeout | ThreadPoolExecutor, graceful shutdown |
| **DLQ** | Replay with idempotency guard | Double-replay prevention |
| **WebSocket** | Connection management, broadcast | Token validation, pub/sub |
| **Metrics** | Prometheus counter/gauge/histogram | Registry isolation |
| **Frontend** | 219 tests across dashboard, jobs, schedules, DLQ, auth | Component rendering, API integration |

## Load Testing

```bash
pip install locust
locust -f loadtest/locustfile.py --headless -u 50 -r 10 --run-time 60s --host http://localhost:8000
```

Results with 50 concurrent users on a single API process:

| Metric | Value |
|--------|-------|
| Throughput | **62 requests/sec** |
| p50 latency | 14ms |
| p95 latency | 50ms |
| p99 latency | 100ms |
| Error rate | **0%** |

See [DESIGN.md](DESIGN.md#load-testing--performance) for full per-endpoint breakdown and bottleneck analysis.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | `redis://localhost:6379/1` | Redis connection string |
| `JWT_SECRET_KEY` | Yes | — | Secret for signing JWT tokens |
| `MAX_RETRIES` | No | `3` | Default max retry attempts per job |
| `VISIBILITY_TIMEOUT` | No | `30` | Seconds before stuck execution recovery |
| `WORKER_POLL_TIMEOUT` | No | `5` | Worker Redis poll interval (s) |
| `RATE_LIMIT_WINDOW` | No | `60` | Sliding window duration (s) |
| `BASE_RETRY_DELAY` | No | `2` | Initial retry backoff delay (s) |
| `JOB_EXECUTION_TIMEOUT` | No | `120` | Hard timeout per job execution (s) |
| `MAX_WORKERS` | No | `10` | Concurrent worker threads (ThreadPoolExecutor) |
| `AUTH_RATE_LIMIT` | No | `10` | Max auth attempts per IP per window |
| `AUTH_RATE_WINDOW` | No | `60` | Auth rate limit window duration (s) |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated allowed origins |

## Design Decisions

See [DESIGN.md](DESIGN.md) for detailed documentation on:

- Why Redis queues over Celery/RabbitMQ
- Why PostgreSQL over MongoDB
- Dual async/sync SQLAlchemy engine strategy
- Three-layer defence against double-scheduling (visibility timeout + row locking + status guard)
- Sliding window rate limiter implementation
- Two-phase commit (DB first, Redis second)
- Failure modes and recovery strategies
- Execution state machine with guard conditions
- SOLID principles applied across the codebase
- High-Level Design (HLD) — system context, component interactions, NFRs
- Low-Level Design (LLD) — worker thread pool, adaptive polling, rate limiter internals, WebSocket lifecycle
- Security architecture — auth flow, 9-layer defense, structured error format
- 30 trade-off decisions with rationale and alternatives considered
- Known limitations and migration paths

## License

MIT
