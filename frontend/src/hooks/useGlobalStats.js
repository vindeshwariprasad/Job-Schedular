import { useQuery } from "@tanstack/react-query";
import { fetchGlobalStats } from "../api/metrics";

export function useGlobalStats() {
  return useQuery({
    queryKey: ["global-stats"],
    queryFn: fetchGlobalStats,
    refetchInterval: 10000,
  });
}
