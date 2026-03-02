import { api } from "./auth";

export const getExecutions = (status, page = 1, size = 20) => {
  const params = { page, size };
  if (status) params.status = status;
  return api
    .get("/admin/dlq/executions", { params })
    .then(res => res.data);
};
