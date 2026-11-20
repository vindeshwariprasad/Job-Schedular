import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Example: postgresql+asyncpg://user:pass@localhost:5432/job_schedular"
    )

# ─── Async engine (for FastAPI API routes) ─────────────
# Convert psycopg2 URL to asyncpg if needed
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "postgresql+psycopg2://", "postgresql+asyncpg://"
).replace(
    "postgresql://", "postgresql+asyncpg://"
)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_timeout=30,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ─── Sync engine (for scheduler & worker processes) ────
# These run in separate processes with ThreadPoolExecutor
# where sync DB access is the natural fit.
SYNC_DATABASE_URL = DATABASE_URL
if "asyncpg" in SYNC_DATABASE_URL:
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_timeout=30,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=False,
    autocommit=False,
)
