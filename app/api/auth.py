import asyncio
import os

from auth import create_access_token, get_current_user, hash_password, verify_password
from db.models.user import User
from db.session import get_db
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_config import get_logger
from metrics.prometheus import auth_redis_failures_total
from queues.rate_limiter import is_rate_limited
from queues.redis_client import redis_client
from redis.exceptions import RedisError
from schemas.auth import Token, UserLogin, UserRegister, UserResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Auth Rate Limiting (Redis-backed) ───────────
# Sliding window: max AUTH_RATE_LIMIT attempts per AUTH_RATE_WINDOW seconds per IP.
# Enforced via Redis sorted sets — works correctly across multiple API processes.
AUTH_RATE_LIMIT: int = int(os.getenv("AUTH_RATE_LIMIT", 20))
AUTH_RATE_WINDOW: int = int(os.getenv("AUTH_RATE_WINDOW", 120))


async def _check_auth_rate_limit(request: Request) -> None:
    """Enforce per-IP rate limiting on authentication endpoints using Redis."""
    client_ip = request.client.host if request.client else "unknown"

    try:
        limited = await asyncio.to_thread(
            is_rate_limited,
            redis_client,
            key=f"auth:{client_ip}",
            limit=AUTH_RATE_LIMIT,
            window_seconds=AUTH_RATE_WINDOW,
        )
    except (ConnectionError, TimeoutError, RedisError) as e:
        auth_redis_failures_total.inc()
        logger.error(
            "Redis unavailable for auth rate limiting: %s",
            e,
            exc_info=True,
            extra={"client_ip": client_ip},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SERVICE_UNAVAILABLE",
                "message": "Authentication service temporarily unavailable. Please try again later.",
            },
            headers={"Retry-After": "30"},
        ) from None

    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(AUTH_RATE_WINDOW)},
        )


@router.post("/register", response_model=Token)
async def register(
    payload: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _check_auth_rate_limit(request)
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "USERNAME_TAKEN", "message": "Username already taken"},
        )

    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "EMAIL_TAKEN", "message": "Email already registered"},
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _check_auth_rate_limit(request)
    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
