"""Tests for the token-bucket rate limiter."""

import time

from queues.rate_limiter import is_rate_limited


class TestRateLimiter:

    def test_not_limited_under_threshold(self, fake_redis):
        """Should allow requests when count is below the limit."""
        result = is_rate_limited(fake_redis, key="job:1", limit=5, window_seconds=60)
        assert result is False

    def test_limited_at_threshold(self, fake_redis):
        """Should block when requests hit the limit within the window."""
        # Pre-fill the bucket with unique timestamps to avoid sorted-set dedup
        now = int(time.time())
        for i in range(5):
            fake_redis.zadd("rate_limit:job:1", {now - i: now - i})

        result = is_rate_limited(fake_redis, key="job:1", limit=5, window_seconds=60)
        assert result is True

    def test_different_keys_independent(self, fake_redis):
        """Rate limits for different jobs should not interfere."""
        for _ in range(5):
            is_rate_limited(fake_redis, key="job:1", limit=5, window_seconds=60)

        # job:2 should still be allowed
        result = is_rate_limited(fake_redis, key="job:2", limit=5, window_seconds=60)
        assert result is False

    def test_expired_entries_cleared(self, fake_redis):
        """Entries outside the window should be cleaned up, allowing new requests."""
        # Simulate old timestamps by directly adding to the sorted set
        old_time = int(time.time()) - 120  # 2 minutes ago
        for i in range(5):
            fake_redis.zadd("rate_limit:job:1", {old_time + i: old_time + i})

        # These are all outside the 60s window, so should not count
        result = is_rate_limited(fake_redis, key="job:1", limit=5, window_seconds=60)
        assert result is False
