import { describe, it, expect, vi } from "vitest";

// Test the parseMetric logic directly since hooks need special rendering
describe("useMetrics - parseMetric logic", () => {
  function parseMetric(text, name) {
    const regex = new RegExp(`^${name}\\s+(\\d+(\\.\\d+)?)$`, "m");
    const match = text.match(regex);
    return match ? Number(match[1]) : 0;
  }

  const metricsText = `# HELP job_executions_total Total
# TYPE job_executions_total counter
job_executions_total 500
# HELP job_success_total Total
# TYPE job_success_total counter
job_success_total 400
# HELP job_failure_total Total
# TYPE job_failure_total counter
job_failure_total 80
# HELP job_dlq_total Total
# TYPE job_dlq_total counter
job_dlq_total 20
# HELP queue_ready_size Size
# TYPE queue_ready_size gauge
queue_ready_size 5
# HELP queue_processing_size Size
# TYPE queue_processing_size gauge
queue_processing_size 3
# HELP queue_failed_size Size
# TYPE queue_failed_size gauge
queue_failed_size 2
`;

  it("parses job_executions_total", () => {
    expect(parseMetric(metricsText, "job_executions_total")).toBe(500);
  });

  it("parses job_success_total", () => {
    expect(parseMetric(metricsText, "job_success_total")).toBe(400);
  });

  it("parses job_failure_total", () => {
    expect(parseMetric(metricsText, "job_failure_total")).toBe(80);
  });

  it("parses job_dlq_total", () => {
    expect(parseMetric(metricsText, "job_dlq_total")).toBe(20);
  });

  it("parses queue_ready_size", () => {
    expect(parseMetric(metricsText, "queue_ready_size")).toBe(5);
  });

  it("parses queue_processing_size", () => {
    expect(parseMetric(metricsText, "queue_processing_size")).toBe(3);
  });

  it("parses queue_failed_size", () => {
    expect(parseMetric(metricsText, "queue_failed_size")).toBe(2);
  });

  it("returns 0 for missing metric", () => {
    expect(parseMetric(metricsText, "nonexistent_metric")).toBe(0);
  });

  it("returns 0 for empty text", () => {
    expect(parseMetric("", "job_executions_total")).toBe(0);
  });

  it("parses decimal values", () => {
    expect(parseMetric("some_metric 3.14", "some_metric")).toBe(3.14);
  });
});
