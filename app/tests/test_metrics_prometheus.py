"""Tests for Prometheus metrics definitions."""

from metrics.prometheus import (
    auth_redis_failures_total,
    circuit_breaker_rejections_total,
    circuit_breaker_state,
    circuit_breaker_trips_total,
    job_dlq_total,
    job_execution_duration,
    job_executions_total,
    job_failure_total,
    job_retry_total,
    job_success_total,
    queue_failed_size,
    queue_processing_size,
    queue_ready_priority_size,
    queue_ready_size,
    redis_up,
    running_executions,
    scheduler_backpressure_active,
    scheduler_is_leader,
)
from prometheus_client import Counter, Gauge, Histogram


class TestCounterMetrics:

    def test_job_executions_total_is_counter(self):
        assert isinstance(job_executions_total, Counter)

    def test_job_success_total_is_counter(self):
        assert isinstance(job_success_total, Counter)

    def test_job_failure_total_is_counter(self):
        assert isinstance(job_failure_total, Counter)

    def test_job_retry_total_is_counter(self):
        assert isinstance(job_retry_total, Counter)

    def test_job_dlq_total_is_counter(self):
        assert isinstance(job_dlq_total, Counter)

    def test_counter_names(self):
        # prometheus_client strips _total suffix from Counter._name
        assert "job_executions" in job_executions_total._name
        assert "job_success" in job_success_total._name
        assert "job_failure" in job_failure_total._name
        assert "job_retry" in job_retry_total._name
        assert "job_dlq" in job_dlq_total._name


class TestGaugeMetrics:

    def test_queue_ready_size_is_gauge(self):
        assert isinstance(queue_ready_size, Gauge)

    def test_queue_processing_size_is_gauge(self):
        assert isinstance(queue_processing_size, Gauge)

    def test_queue_failed_size_is_gauge(self):
        assert isinstance(queue_failed_size, Gauge)

    def test_running_executions_is_gauge(self):
        assert isinstance(running_executions, Gauge)

    def test_gauge_names(self):
        assert queue_ready_size._name == "queue_ready_size"
        assert queue_processing_size._name == "queue_processing_size"
        assert queue_failed_size._name == "queue_failed_size"
        assert running_executions._name == "running_executions"


class TestHistogramMetrics:

    def test_duration_is_histogram(self):
        assert isinstance(job_execution_duration, Histogram)

    def test_duration_name(self):
        assert job_execution_duration._name == "job_execution_duration_seconds"

    def test_duration_has_buckets(self):
        # Histogram should have buckets defined
        assert hasattr(job_execution_duration, '_upper_bounds')


class TestMetricsFunctionality:

    def test_counter_increments(self):
        before = job_executions_total._value.get()
        job_executions_total.inc()
        after = job_executions_total._value.get()
        assert after == before + 1

    def test_gauge_set_and_get(self):
        queue_ready_size.set(42)
        assert queue_ready_size._value.get() == 42

    def test_gauge_inc_dec(self):
        running_executions.set(0)
        running_executions.inc()
        assert running_executions._value.get() == 1
        running_executions.dec()
        assert running_executions._value.get() == 0

    def test_histogram_observe(self):
        # Should not raise
        job_execution_duration.observe(1.5)


class TestInfrastructureHealthMetrics:

    def test_redis_up_is_gauge(self):
        assert isinstance(redis_up, Gauge)

    def test_redis_up_name(self):
        assert redis_up._name == "redis_up"

    def test_redis_up_set_values(self):
        redis_up.set(1)
        assert redis_up._value.get() == 1
        redis_up.set(0)
        assert redis_up._value.get() == 0

    def test_auth_redis_failures_total_is_counter(self):
        assert isinstance(auth_redis_failures_total, Counter)

    def test_auth_redis_failures_total_name(self):
        assert "auth_redis_failures" in auth_redis_failures_total._name

    def test_auth_redis_failures_total_increments(self):
        before = auth_redis_failures_total._value.get()
        auth_redis_failures_total.inc()
        after = auth_redis_failures_total._value.get()
        assert after == before + 1


class TestSchedulerLeaderMetrics:

    def test_scheduler_is_leader_is_gauge(self):
        assert isinstance(scheduler_is_leader, Gauge)

    def test_scheduler_is_leader_name(self):
        assert scheduler_is_leader._name == "scheduler_is_leader"

    def test_scheduler_is_leader_set_values(self):
        scheduler_is_leader.set(1)
        assert scheduler_is_leader._value.get() == 1
        scheduler_is_leader.set(0)
        assert scheduler_is_leader._value.get() == 0


class TestCircuitBreakerMetrics:

    def test_circuit_breaker_state_is_gauge(self):
        assert isinstance(circuit_breaker_state, Gauge)

    def test_circuit_breaker_state_name(self):
        assert circuit_breaker_state._name == "circuit_breaker_state"

    def test_circuit_breaker_state_has_endpoint_label(self):
        # Setting a labeled gauge should work without error
        circuit_breaker_state.labels(endpoint="test.com").set(0)

    def test_circuit_breaker_trips_total_is_counter(self):
        assert isinstance(circuit_breaker_trips_total, Counter)

    def test_circuit_breaker_trips_total_name(self):
        assert "circuit_breaker_trips" in circuit_breaker_trips_total._name

    def test_circuit_breaker_trips_total_increments(self):
        before = circuit_breaker_trips_total._value.get()
        circuit_breaker_trips_total.inc()
        after = circuit_breaker_trips_total._value.get()
        assert after == before + 1

    def test_circuit_breaker_rejections_total_is_counter(self):
        assert isinstance(circuit_breaker_rejections_total, Counter)

    def test_circuit_breaker_rejections_total_name(self):
        assert "circuit_breaker_rejections" in circuit_breaker_rejections_total._name

    def test_circuit_breaker_rejections_total_increments(self):
        before = circuit_breaker_rejections_total._value.get()
        circuit_breaker_rejections_total.inc()
        after = circuit_breaker_rejections_total._value.get()
        assert after == before + 1


class TestPriorityQueueMetrics:

    def test_queue_ready_priority_size_is_gauge(self):
        assert isinstance(queue_ready_priority_size, Gauge)

    def test_queue_ready_priority_size_name(self):
        assert queue_ready_priority_size._name == "queue_ready_priority_size"

    def test_queue_ready_priority_size_has_priority_label(self):
        # Setting a labeled gauge should work without error
        queue_ready_priority_size.labels(priority="high").set(5)
        queue_ready_priority_size.labels(priority="medium").set(10)
        queue_ready_priority_size.labels(priority="low").set(3)


class TestBackpressureMetrics:

    def test_scheduler_backpressure_active_is_gauge(self):
        assert isinstance(scheduler_backpressure_active, Gauge)

    def test_scheduler_backpressure_active_name(self):
        assert scheduler_backpressure_active._name == "scheduler_backpressure_active"

    def test_scheduler_backpressure_active_set_values(self):
        scheduler_backpressure_active.set(1)
        assert scheduler_backpressure_active._value.get() == 1
        scheduler_backpressure_active.set(0)
        assert scheduler_backpressure_active._value.get() == 0
