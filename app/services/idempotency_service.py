"""Idempotency key management for POST /jobs.

Two-phase approach:
1. Claim key with short-TTL placeholder (60s) using SET NX
2. After job creation, upgrade to real response with 24h TTL using SET XX

If app crashes between phases, placeholder expires in 60s — not locked for 24h.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from constants import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    IDEMPOTENCY_PLACEHOLDER_TTL,
    IDEMPOTENCY_TTL,
)
from logging_config import get_logger

logger = get_logger("idempotency")

PLACEHOLDER = "__IN_PROGRESS__"


class IdempotencyResult(StrEnum):
    NEW = "new"
    CACHED = "cached"
    MISMATCH = "mismatch"
    IN_PROGRESS = "in_progress"


@dataclass
class IdempotencyCheck:
    result: IdempotencyResult
    cached_response: dict | None = None


def _redis_key(user_id: int, key: str) -> str:
    return f"idempotency:{user_id}:{key}"


def compute_payload_hash(payload: dict) -> str:
    """SHA-256 hash of canonical JSON representation."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_idempotency_key(key: str) -> None:
    """Validate key format/length. Raises ValueError on failure."""
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValueError(
            f"Idempotency-Key must be {IDEMPOTENCY_KEY_MAX_LENGTH} characters or fewer"
        )


def claim_idempotency_key(redis, user_id: int, key: str, payload_hash: str) -> IdempotencyCheck:
    """Attempt to claim an idempotency key. Returns the check result.

    - NEW: key was claimed, caller should proceed to create the job
    - CACHED: key exists with a valid response, return it
    - MISMATCH: key exists but payload hash differs
    - IN_PROGRESS: another request is in-flight (placeholder)
    """
    rkey = _redis_key(user_id, key)

    # Try to claim with short-TTL placeholder
    claimed = redis.set(
        rkey,
        json.dumps({"status": PLACEHOLDER, "hash": payload_hash}),
        nx=True,
        ex=IDEMPOTENCY_PLACEHOLDER_TTL,
    )

    if claimed:
        return IdempotencyCheck(result=IdempotencyResult.NEW)

    # Key exists — check what's stored
    raw = redis.get(rkey)
    if raw is None:
        # Key expired between SET NX and GET — race, treat as new
        # Try to claim again
        reclaimed = redis.set(
            rkey,
            json.dumps({"status": PLACEHOLDER, "hash": payload_hash}),
            nx=True,
            ex=IDEMPOTENCY_PLACEHOLDER_TTL,
        )
        if reclaimed:
            return IdempotencyCheck(result=IdempotencyResult.NEW)
        # Another request got it — treat as in-progress
        return IdempotencyCheck(result=IdempotencyResult.IN_PROGRESS)

    stored = json.loads(raw)

    if stored.get("status") == PLACEHOLDER:
        # Another request is in-flight
        return IdempotencyCheck(result=IdempotencyResult.IN_PROGRESS)

    # Real response cached — check payload hash
    if stored.get("hash") != payload_hash:
        return IdempotencyCheck(result=IdempotencyResult.MISMATCH)

    return IdempotencyCheck(
        result=IdempotencyResult.CACHED,
        cached_response=stored.get("response"),
    )


def store_idempotency_response(
    redis,
    user_id: int,
    key: str,
    payload_hash: str,
    response: dict,
) -> None:
    """Upgrade placeholder to real response with 24h TTL."""
    rkey = _redis_key(user_id, key)
    redis.set(
        rkey,
        json.dumps({
            "hash": payload_hash,
            "response": response,
        }),
        ex=IDEMPOTENCY_TTL,
    )
    logger.debug("Stored idempotency response for key %s (user %d)", key, user_id)
