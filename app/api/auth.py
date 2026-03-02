import os
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models.user import User
from schemas.auth import UserRegister, UserLogin, UserResponse, Token
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Auth Rate Limiting ──────────────────────
# Sliding window: max AUTH_RATE_LIMIT attempts per AUTH_RATE_WINDOW seconds per IP
AUTH_RATE_LIMIT: int = int(os.getenv("AUTH_RATE_LIMIT", 10))
AUTH_RATE_WINDOW: int = int(os.getenv("AUTH_RATE_WINDOW", 60))
_auth_attempts: dict[str, list[float]] = defaultdict(list)


def _check_auth_rate_limit(request: Request) -> None:
    """Enforce per-IP rate limiting on authentication endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - AUTH_RATE_WINDOW

    # Prune old entries
    _auth_attempts[client_ip] = [
        t for t in _auth_attempts[client_ip] if t > window_start
    ]

    if len(_auth_attempts[client_ip]) >= AUTH_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(AUTH_RATE_WINDOW)},
        )

    _auth_attempts[client_ip].append(now)


@router.post("/register", response_model=Token)
async def register(
    payload: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _check_auth_rate_limit(request)
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
    _check_auth_rate_limit(request)
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
