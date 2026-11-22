
import pytest
import pytest_asyncio
from db.base import Base
from db.models.job import Job
from db.models.user import User
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ------------------------------------
# Sync in-memory SQLite for unit tests
# (scheduler, worker, models — sync code)
# ------------------------------------
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def db_with_for_update():
    """DB fixture that strips FOR UPDATE (unsupported in SQLite) for scheduler/worker tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    @event.listens_for(engine, "before_cursor_execute")
    def _strip_for_update(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            statement = statement.replace(" FOR UPDATE", "")
            return statement, parameters

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ------------------------------------
# Async in-memory SQLite for API tests
# (FastAPI endpoints use async SQLAlchemy)
# ------------------------------------
@pytest_asyncio.fixture
async def async_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


# ------------------------------------
# Fake Redis using a dict-backed mock
# ------------------------------------
class FakeRedis:
    """Minimal Redis mock that supports the operations our code uses."""

    def __init__(self):
        self._lists: dict[str, list] = {}
        self._strings: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._sorted_sets: dict[str, dict] = {}
        self._expiry: dict[str, int] = {}
        self._pubsub_messages: list = []

    # --- List operations ---
    def lpush(self, key, *values):
        lst = self._lists.setdefault(key, [])
        for v in values:
            lst.insert(0, v)
        return len(lst)

    def llen(self, key):
        return len(self._lists.get(key, []))

    def lrange(self, key, start, stop):
        lst = self._lists.get(key, [])
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]

    def lrem(self, key, count, value):
        lst = self._lists.get(key, [])
        removed = 0
        if count > 0:
            for _ in range(count):
                if value in lst:
                    lst.remove(value)
                    removed += 1
        elif count == 0:
            while value in lst:
                lst.remove(value)
                removed += 1
        return removed

    def brpoplpush(self, src, dst, timeout=0):
        src_list = self._lists.get(src, [])
        if not src_list:
            return None
        item = src_list.pop()
        dst_list = self._lists.setdefault(dst, [])
        dst_list.insert(0, item)
        return item

    # --- String operations (for leader election / circuit breaker) ---
    def set(self, key, value, nx=False, xx=False, ex=None):
        if nx and key in self._strings:
            return None
        if xx and key not in self._strings:
            return None
        self._strings[key] = value
        if ex is not None:
            self._expiry[key] = ex
        return True

    def get(self, key):
        return self._strings.get(key)

    def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self._strings:
                del self._strings[key]
                count += 1
            if key in self._hashes:
                del self._hashes[key]
                count += 1
        return count

    # --- Hash operations (for circuit breaker) ---
    def hset(self, key, field=None, value=None, mapping=None):
        h = self._hashes.setdefault(key, {})
        if mapping:
            h.update({str(k): str(v) for k, v in mapping.items()})
            return len(mapping)
        h[str(field)] = str(value)
        return 1

    def hget(self, key, field):
        h = self._hashes.get(key, {})
        return h.get(str(field))

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hincrby(self, key, field, amount=1):
        h = self._hashes.setdefault(key, {})
        field = str(field)
        current = int(h.get(field, "0"))
        h[field] = str(current + amount)
        return current + amount

    def hdel(self, key, *fields):
        h = self._hashes.get(key, {})
        count = 0
        for f in fields:
            if str(f) in h:
                del h[str(f)]
                count += 1
        return count

    # --- Sorted set operations (for rate limiter) ---
    def pipeline(self):
        return FakePipeline(self)

    def zadd(self, key, mapping):
        ss = self._sorted_sets.setdefault(key, {})
        ss.update(mapping)
        return len(mapping)

    def zremrangebyscore(self, key, min_score, max_score):
        ss = self._sorted_sets.get(key, {})
        to_remove = [m for m, s in ss.items() if min_score <= s <= max_score]
        for m in to_remove:
            del ss[m]
        return len(to_remove)

    def zcard(self, key):
        return len(self._sorted_sets.get(key, {}))

    def expire(self, key, seconds):
        self._expiry[key] = seconds
        return True

    # --- Pub/Sub operations ---
    def publish(self, channel, message):
        self._pubsub_messages.append({"channel": channel, "message": message})
        return 1

    # --- Health check ---
    def ping(self):
        return True


class FakePipeline:
    """Collects commands and executes them in order."""

    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._commands: list = []

    def zremrangebyscore(self, key, min_s, max_s):
        self._commands.append(("zremrangebyscore", key, min_s, max_s))
        return self

    def zcard(self, key):
        self._commands.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self._commands.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self._commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for cmd in self._commands:
            method = getattr(self._redis, cmd[0])
            results.append(method(*cmd[1:]))
        return results


@pytest.fixture
def fake_redis():
    return FakeRedis()


# ------------------------------------
# Helper: create a sample User row (sync)
# ------------------------------------
@pytest.fixture
def sample_user(db):
    from auth import hash_password
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("TestPass123"),
    )
    db.add(user)
    db.commit()
    return user


# ------------------------------------
# Helper: create a sample Job row (sync)
# ------------------------------------
@pytest.fixture
def sample_job(db):
    job = Job(
        id=1,
        user_id=1,
        name="Test Job",
        task_type="api_call",
        payload={"url": "https://httpbin.org/get"},
        rate_limit_per_min=60,
        is_active=True,
    )
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def sample_job_string(db):
    job = Job(
        id=2,
        user_id=1,
        name="String Job",
        task_type="string_manipulation",
        payload={"input": "hello world"},
        rate_limit_per_min=60,
        is_active=True,
    )
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def sample_job_math(db):
    job = Job(
        id=3,
        user_id=1,
        name="Math Job",
        task_type="math",
        payload={"expression": "2 + 3"},
        rate_limit_per_min=60,
        is_active=True,
    )
    db.add(job)
    db.commit()
    return job
