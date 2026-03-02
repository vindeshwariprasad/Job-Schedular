import os

import httpx
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST

WORKER_METRICS_URL = os.getenv("WORKER_METRICS_URL", "http://localhost:9101")

router = APIRouter(prefix="/worker", tags=["worker-metrics"])

@router.get("/metrics")
async def worker_metrics():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{WORKER_METRICS_URL}/metrics")

    return Response(
        content=resp.text,
        media_type=CONTENT_TYPE_LATEST,
    )
