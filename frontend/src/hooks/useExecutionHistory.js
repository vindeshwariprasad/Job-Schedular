import { useQuery } from "@tanstack/react-query";
import { fetchExecutionHistory } from "../api/metrics";

export function useExecutionHistory() {
  return useQuery({
    queryKey: ["execution-history"],
    queryFn: fetchExecutionHistory,
    refetchInterval: 10000,
  });
}
