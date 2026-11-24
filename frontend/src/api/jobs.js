import { api } from "./auth";

export const getJobs = (page = 1, size = 20) =>
  api.get("/jobs", { params: { page, size } }).then(res => res.data);

export const createJob = (data) =>
  api.post("/jobs", data).then(res => res.data);

export const getJob = (id) =>
  api.get(`/jobs/${id}`).then(res => res.data);

export const getJobDependents = (id) =>
  api.get(`/jobs/${id}/dependents`).then(res => res.data);

export const deleteJob = (id, cascade = false) =>
  api.delete(`/jobs/${id}`, { params: { cascade } }).then(res => res.data);
