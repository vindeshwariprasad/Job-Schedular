import { api } from "./auth";

export const createSchedule = (jobId, data) =>
  api.post(`/jobs/${jobId}/schedule`, data)
       .then(res => res.data);

export const getSchedule = (jobId) =>
  api.get(`/jobs/${jobId}/schedule`)
       .then(res => res.data);

export const pauseSchedule = (jobId) =>
  api.patch(`/jobs/${jobId}/schedule/pause`)
       .then(res => res.data);

export const resumeSchedule = (jobId) =>
  api.patch(`/jobs/${jobId}/schedule/resume`)
       .then(res => res.data);

export const deleteSchedule = (jobId) =>
  api.delete(`/jobs/${jobId}/schedule`)
       .then(res => res.data);
