import asyncio
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager

from api import auth, jobs, schedules
from api import metrics as worker_metrics_api
from api.admin_dlq import router as admin_dlq_router
from auth import decode_token
from db.session import async_engine
from fastapi import APIRouter, FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from metrics.prometheus import redis_up
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from queues.redis_client import redis_client
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from websocket.connection_manager import manager as ws_manager
from websocket.redis_listener import listen_to_execution_updates

logger = logging.getLogger("uvicorn.error")


# ─── Correlation ID Middleware ────────────────
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Injects a unique X-Request-ID into every request/response for distributed tracing."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch Redis pub/sub listener for WebSocket broadcasts
    task = asyncio.create_task(listen_to_execution_updates())
    logger.info("Started Redis pub/sub listener for WebSocket updates")
    yield
    # Shutdown: cancel the listener and dispose async engine
    task.cancel()
    await async_engine.dispose()


# \app> python -m uvicorn main:app --reload
app = FastAPI(
    lifespan=lifespan,
    title="Job Scheduler API",
    description=(
        "A distributed job scheduling system with cron-based scheduling, "
        "retry policies, dead letter queues, and rate limiting.\n\n"
        "## Features\n"
        "- **Jobs**: Create and manage jobs (API calls or scripts)\n"
        "- **Schedules**: Cron-based scheduling with pause/resume support\n"
        "- **Executions**: Track job runs with automatic retries\n"
        "- **DLQ**: Dead letter queue for failed jobs with replay capability\n"
        "- **Metrics**: Prometheus-compatible observability"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middleware Stack ─────────────────────────
# (added bottom-to-top: last added = outermost = runs first)
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(CorrelationIDMiddleware)


# ─── Global Exception Handler ─────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi.exceptions import HTTPException as FastAPIHTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException

    # Let FastAPI handle its own HTTP exceptions (404, 409, 422, etc.)
    if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
        raise exc

    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled error on %s %s [request_id=%s]: %s",
        request.method, request.url.path, request_id, exc,
    )
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )


# ─── Health Check ──────────────────────────────
@app.get("/health", tags=["monitoring"])
async def health_check():
    checks = {"status": "healthy", "postgres": "up", "redis": "up"}
    is_healthy = True

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        checks["postgres"] = "down"
        is_healthy = False

    try:
        redis_client.ping()
        redis_up.set(1)
    except Exception:
        checks["redis"] = "down"
        redis_up.set(0)
        is_healthy = False

    if not is_healthy:
        checks["status"] = "unhealthy"
        return JSONResponse(content=checks, status_code=503)

    return checks


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ─── WebSocket ────────────────────────────────
@app.websocket("/ws/executions")
async def websocket_executions(websocket: WebSocket, token: str = Query(...)):
    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id, websocket)


# ─── API Versioning ────────────────────────────
v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth.router)
v1.include_router(jobs.router)
v1.include_router(schedules.router)
v1.include_router(worker_metrics_api.router)
v1.include_router(admin_dlq_router)
app.include_router(v1)
