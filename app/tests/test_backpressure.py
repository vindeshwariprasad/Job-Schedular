"""Tests for backpressure mechanism in scheduler runner."""

from unittest.mock import patch

from scheduler.runner import _check_backpressure


class TestCheckBackpressure:
    """Tests for the _check_backpressure function."""

    def _fill_queues(self, fake_redis, total_depth):
        """Fill ready queues to reach a specific total depth."""
        # Distribute across queues (put everything in medium for simplicity)
        for _ in range(total_depth):
            fake_redis.lpush("queue:ready:medium", "item")

    def test_no_backpressure_when_below_warn(self, fake_redis):
        self._fill_queues(fake_redis, 500)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active") as gauge:
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is False
        assert sleep_time is None
        gauge.set.assert_called_once_with(0)

    def test_warn_backpressure_active(self, fake_redis):
        self._fill_queues(fake_redis, 1500)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active") as gauge:
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is True
        assert sleep_time == 5
        gauge.set.assert_called_once_with(1)

    def test_critical_backpressure_active(self, fake_redis):
        self._fill_queues(fake_redis, 6000)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active") as gauge:
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is True
        assert sleep_time == 30
        gauge.set.assert_called_once_with(1)

    def test_backpressure_lifted(self, fake_redis):
        """When backpressure was active and queue depth drops, should return False."""
        self._fill_queues(fake_redis, 100)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active") as gauge:
            is_active, sleep_time = _check_backpressure(fake_redis, True)

        assert is_active is False
        assert sleep_time is None
        gauge.set.assert_called_once_with(0)

    def test_exactly_at_warn_threshold(self, fake_redis):
        """At exactly the warn threshold, should NOT trigger (must exceed)."""
        self._fill_queues(fake_redis, 1000)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active"):
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is False
        assert sleep_time is None

    def test_exactly_at_critical_threshold(self, fake_redis):
        """At exactly the critical threshold, should NOT trigger critical (must exceed)."""
        self._fill_queues(fake_redis, 5000)

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active"):
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        # Should be warn-level, not critical
        assert is_active is True
        assert sleep_time == 5

    def test_checks_all_ready_queues(self, fake_redis):
        """Backpressure should consider total depth across all priority queues."""
        # Spread items across all queues: 400 each = 1200 total
        for _ in range(400):
            fake_redis.lpush("queue:ready:high", "h")
            fake_redis.lpush("queue:ready:medium", "m")
            fake_redis.lpush("queue:ready:low", "l")

        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active"):
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is True
        assert sleep_time == 5

    def test_empty_queues_no_backpressure(self, fake_redis):
        with patch("scheduler.runner.BACKPRESSURE_WARN_THRESHOLD", 1000), \
             patch("scheduler.runner.BACKPRESSURE_CRITICAL_THRESHOLD", 5000), \
             patch("scheduler.runner.scheduler_backpressure_active") as gauge:
            is_active, sleep_time = _check_backpressure(fake_redis, False)

        assert is_active is False
        assert sleep_time is None
        gauge.set.assert_called_once_with(0)
