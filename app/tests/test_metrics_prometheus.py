"""Tests for Prometheus metrics definitions."""

from prometheus_client import Counter, Gauge, Histogram

from metrics.prometheus import (
    job_executions_total,
    job_success_total,
    job_failure_total,
    job_retry_total,
    job_dlq_total,
    queue_ready_size,
    queue_processing_size,
    queue_failed_size,
    running_executions,
    job_execution_duration,
)


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
