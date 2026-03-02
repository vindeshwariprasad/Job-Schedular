import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/auth", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

describe("Metrics API", () => {
  let fetchMetrics, fetchUserStats, fetchGlobalStats, fetchExecutionHistory, getMetricsText, api;

  beforeEach(async () => {
    vi.resetModules();
    const authMod = await import("../../api/auth");
    api = authMod.api;
    const mod = await import("../../api/metrics");
    fetchMetrics = mod.fetchMetrics;
    fetchUserStats = mod.fetchUserStats;
    fetchGlobalStats = mod.fetchGlobalStats;
    fetchExecutionHistory = mod.fetchExecutionHistory;
    getMetricsText = mod.getMetricsText;
  });

  it("fetchMetrics calls GET /worker/metrics", async () => {
    api.get.mockResolvedValue({ data: "some_metric 42" });

    const result = await fetchMetrics();

    expect(api.get).toHaveBeenCalledWith("/worker/metrics");
    expect(result).toBe("some_metric 42");
  });

  it("getMetricsText calls GET /worker/metrics", async () => {
    api.get.mockResolvedValue({ data: "raw text" });

    const result = await getMetricsText();
    expect(result).toBe("raw text");
  });

  it("fetchUserStats calls GET /admin/dlq/user-stats", async () => {
    api.get.mockResolvedValue({ data: { total_executions: 100 } });

    const result = await fetchUserStats();

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/user-stats");
    expect(result.total_executions).toBe(100);
  });

  it("fetchGlobalStats calls GET /admin/dlq/global-stats", async () => {
    api.get.mockResolvedValue({ data: { total_executions: 5000 } });

    const result = await fetchGlobalStats();

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/global-stats");
    expect(result.total_executions).toBe(5000);
  });

  it("fetchExecutionHistory calls GET /admin/dlq/execution-history", async () => {
    api.get.mockResolvedValue({ data: [{ date: "2024-01-01" }] });

    const result = await fetchExecutionHistory();

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/execution-history");
    expect(result).toHaveLength(1);
  });
});
