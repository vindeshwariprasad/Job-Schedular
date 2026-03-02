import { api } from "./auth";

export const getMetricsText = () =>
  api.get("/worker/metrics").then(res => res.data);

export async function fetchMetrics() {
  const res = await api.get("/worker/metrics");
  return res.data;
}

export const fetchUserStats = () =>
  api.get("/admin/dlq/user-stats").then(res => res.data);

export const fetchGlobalStats = () =>
  api.get("/admin/dlq/global-stats").then(res => res.data);

export const fetchExecutionHistory = () =>
  api.get("/admin/dlq/execution-history").then(res => res.data);
