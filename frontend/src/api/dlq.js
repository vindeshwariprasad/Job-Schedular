import { api } from "./auth";

export const getDLQ = (page = 1, size = 20) =>
  api.get("/admin/dlq", { params: { page, size } }).then(res => res.data);

export const replayDLQ = (executionId) =>
  api.post(`/admin/dlq/${executionId}/replay`)
       .then(res => res.data);
