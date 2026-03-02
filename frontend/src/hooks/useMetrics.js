// import { useQuery } from "@tanstack/react-query";
// import { getMetricsText } from "../api/metrics";

// export const useMetrics = () =>
//   useQuery({
//     queryKey: ["metrics"],
//     queryFn: getMetricsText,
//     refetchInterval: 5000,
//   });


import { useQuery } from "@tanstack/react-query";
import { fetchMetrics } from "../api/metrics";

function parseMetric(text, name) {
  const regex = new RegExp(`^${name}\\s+(\\d+(\\.\\d+)?)$`, "m");
  const match = text.match(regex);
  return match ? Number(match[1]) : 0;
}

export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: fetchMetrics,
    refetchInterval: 5000,
    select: raw => ({
      executions: parseMetric(raw, "job_executions_total"),
      success: parseMetric(raw, "job_success_total"),
      failures: parseMetric(raw, "job_failure_total"),
      dlq: parseMetric(raw, "job_dlq_total"),
      queueReady: parseMetric(raw, "queue_ready_size"),
      queueProcessing: parseMetric(raw, "queue_processing_size"),
      queueFailed: parseMetric(raw, "queue_failed_size"),
    }),
  });
}
