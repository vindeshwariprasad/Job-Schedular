import time
import uuid
from redis import Redis

def is_rate_limited(
    redis: Redis,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """
    Sliding window rate limiter using sorted sets.
    Each request gets a unique member to avoid overwrites within the same second.
    """
    if limit <= 0:
        return False

    current = int(time.time())
    bucket = f"rate_limit:{key}"
    member = f"{current}:{uuid.uuid4().hex[:8]}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(bucket, 0, current - window_seconds)
    pipe.zcard(bucket)
    pipe.zadd(bucket, {member: current})
    pipe.expire(bucket, window_seconds)

    _, count, *_ = pipe.execute()
    return count >= limit
