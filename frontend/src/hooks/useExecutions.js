import { useQuery } from "@tanstack/react-query";
import { getExecutions } from "../api/executions";

export const useExecutions = (status) =>
  useQuery({
    queryKey: ["executions", status],
    queryFn: () => getExecutions(status),
  });
