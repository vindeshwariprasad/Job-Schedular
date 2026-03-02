import { useQuery } from "@tanstack/react-query";
import { fetchUserStats } from "../api/metrics";

export function useUserStats() {
  return useQuery({
    queryKey: ["user-stats"],
    queryFn: fetchUserStats,
    refetchInterval: 10000,
  });
}
