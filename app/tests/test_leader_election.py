"""Tests for scheduler leader election using Redis-based distributed locking."""

from unittest.mock import MagicMock, patch

import pytest
import scheduler.runner as runner_module
from scheduler.runner import (
    INSTANCE_ID,
    LEADER_KEY,
    LEADER_TTL,
    _release_lock,
    _renew_lock,
    _try_acquire_lock,
    start_scheduler,
)


def _reset_shutdown():
    """Reset the SHUTDOWN flag before each test."""
    runner_module.SHUTDOWN = False


class TestTryAcquireLock:
    """Tests for _try_acquire_lock()."""

    def test_acquires_lock_on_empty_redis(self, fake_redis):
        """Should acquire lock when no leader exists."""
        assert _try_acquire_lock(fake_redis) is True
        assert fake_redis.get(LEADER_KEY) == INSTANCE_ID

    def test_fails_when_another_leader_exists(self, fake_redis):
        """Should fail when another instance already holds the lock."""
        fake_redis.set(LEADER_KEY, "other-host:999", ex=LEADER_TTL)
        assert _try_acquire_lock(fake_redis) is False
        # Original leader's value should be unchanged
        assert fake_redis.get(LEADER_KEY) == "other-host:999"

    def test_sets_ttl_on_lock(self, fake_redis):
        """Lock should have an expiry set."""
        _try_acquire_lock(fake_redis)
        assert fake_redis._expiry.get(LEADER_KEY) == LEADER_TTL

    def test_handles_redis_error(self):
        """Should propagate Redis errors (caller handles them)."""
        broken_redis = MagicMock()
        broken_redis.set.side_effect = ConnectionError("Redis down")
        with pytest.raises(ConnectionError, match="Redis down"):
            _try_acquire_lock(broken_redis)


class TestRenewLock:
    """Tests for _renew_lock()."""

    def test_renews_when_leader(self, fake_redis):
        """Should renew lock when this instance is the leader."""
        fake_redis.set(LEADER_KEY, INSTANCE_ID, ex=LEADER_TTL)
        assert _renew_lock(fake_redis) is True
        assert fake_redis.get(LEADER_KEY) == INSTANCE_ID

    def test_fails_when_lock_expired(self, fake_redis):
        """Should fail when lock doesn't exist (expired)."""
        assert _renew_lock(fake_redis) is False

    def test_renews_even_if_value_differs(self, fake_redis):
        """SET XX checks existence only, not ownership. This is by design."""
        fake_redis.set(LEADER_KEY, "other-host:999", ex=LEADER_TTL)
        result = _renew_lock(fake_redis)
        # SET XX succeeds because key exists (overwrites value)
        assert result is True


class TestReleaseLock:
    """Tests for _release_lock()."""

    def test_releases_own_lock(self, fake_redis):
        """Should delete lock when this instance owns it."""
        fake_redis.set(LEADER_KEY, INSTANCE_ID, ex=LEADER_TTL)
        _release_lock(fake_redis)
        assert fake_redis.get(LEADER_KEY) is None

    def test_does_not_release_other_leaders_lock(self, fake_redis):
        """Should NOT delete lock when another instance owns it."""
        fake_redis.set(LEADER_KEY, "other-host:999", ex=LEADER_TTL)
        _release_lock(fake_redis)
        assert fake_redis.get(LEADER_KEY) == "other-host:999"

    def test_noop_when_no_lock(self, fake_redis):
        """Should not crash when no lock exists."""
        _release_lock(fake_redis)


class TestStartSchedulerLeaderElection:
    """Tests for start_scheduler() with leader election integration."""

    def test_leader_runs_scheduler(self, fake_redis):
        """Leader instance should call run_scheduler_once."""
        _reset_shutdown()
        call_count = 0

        def fake_run_once(db):
            nonlocal call_count
            call_count += 1
            runner_module.SHUTDOWN = True
            return 0

        with patch.object(runner_module, "run_scheduler_once", side_effect=fake_run_once), \
             patch.object(runner_module, "recover_orphaned_executions"), \
             patch.object(runner_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(runner_module, "time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_time.sleep = MagicMock()
            start_scheduler(redis=fake_redis)

        assert call_count >= 1

    def test_standby_does_not_run_scheduler(self, fake_redis):
        """Non-leader instance should NOT call run_scheduler_once."""
        _reset_shutdown()
        fake_redis.set(LEADER_KEY, "other-host:999", ex=LEADER_TTL)

        sleep_calls = 0

        def counting_sleep(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                runner_module.SHUTDOWN = True

        with patch.object(runner_module, "run_scheduler_once") as mock_run, \
             patch.object(runner_module, "time") as mock_time:
            mock_time.sleep = counting_sleep
            mock_time.monotonic.return_value = 0
            start_scheduler(redis=fake_redis)

        mock_run.assert_not_called()

    def test_lock_released_on_shutdown(self, fake_redis):
        """Lock should be released when scheduler shuts down gracefully."""
        _reset_shutdown()

        def immediate_shutdown(db):
            runner_module.SHUTDOWN = True
            return 0

        with patch.object(runner_module, "run_scheduler_once", side_effect=immediate_shutdown), \
             patch.object(runner_module, "recover_orphaned_executions"), \
             patch.object(runner_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(runner_module, "time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_time.sleep = MagicMock()
            start_scheduler(redis=fake_redis)

        assert fake_redis.get(LEADER_KEY) is None

    def test_returns_to_standby_when_lock_lost(self, fake_redis):
        """If lock renewal fails, scheduler should exit leader loop."""
        _reset_shutdown()
        renew_results = iter([True, False])  # succeed once, then fail
        acquire_results = iter([True, False, False])

        run_count = 0
        sleep_count = 0

        def fake_run_once(db):
            nonlocal run_count
            run_count += 1
            return 0

        def counting_sleep(seconds):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 4:
                runner_module.SHUTDOWN = True

        with patch.object(runner_module, "_renew_lock", side_effect=lambda r=None: next(renew_results, False)), \
             patch.object(runner_module, "_try_acquire_lock", side_effect=lambda r=None: next(acquire_results, False)), \
             patch.object(runner_module, "run_scheduler_once", side_effect=fake_run_once), \
             patch.object(runner_module, "recover_orphaned_executions"), \
             patch.object(runner_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(runner_module, "time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_time.sleep = counting_sleep
            start_scheduler(redis=fake_redis)

        assert run_count >= 1

    def test_redis_error_during_acquire_retries(self, fake_redis):
        """Redis connection error on acquire should not crash, should retry."""
        _reset_shutdown()
        attempt = 0

        def flaky_acquire(r=None):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise ConnectionError("Redis temporarily down")
            return True  # Second attempt succeeds

        def immediate_shutdown(db):
            runner_module.SHUTDOWN = True
            return 0

        with patch.object(runner_module, "_try_acquire_lock", side_effect=flaky_acquire), \
             patch.object(runner_module, "_renew_lock", return_value=True), \
             patch.object(runner_module, "run_scheduler_once", side_effect=immediate_shutdown), \
             patch.object(runner_module, "recover_orphaned_executions"), \
             patch.object(runner_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(runner_module, "time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_time.sleep = MagicMock()
            start_scheduler(redis=fake_redis)

        assert attempt >= 2

    def test_scheduler_is_leader_metric_set(self, fake_redis):
        """scheduler_is_leader gauge should be set to 1 when leading, 0 on shutdown."""
        _reset_shutdown()

        def immediate_shutdown(db):
            runner_module.SHUTDOWN = True
            return 0

        with patch.object(runner_module, "run_scheduler_once", side_effect=immediate_shutdown), \
             patch.object(runner_module, "_renew_lock", return_value=True), \
             patch.object(runner_module, "recover_orphaned_executions"), \
             patch.object(runner_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(runner_module, "scheduler_is_leader") as mock_gauge, \
             patch.object(runner_module, "time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_time.sleep = MagicMock()
            start_scheduler(redis=fake_redis)

        set_calls = [c[0][0] for c in mock_gauge.set.call_args_list]
        assert 1 in set_calls
        assert set_calls[-1] == 0
