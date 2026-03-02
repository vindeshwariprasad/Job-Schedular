import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  createSchedule,
  getSchedule,
  pauseSchedule,
  resumeSchedule,
  deleteSchedule,
} from "../api/schedules";

export const useSchedule = (jobId) =>
  useQuery({
    queryKey: ["schedule", jobId],
    queryFn: () => getSchedule(jobId),
    enabled: !!jobId,
    retry: false,
  });

export const useCreateSchedule = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, cron_expression, max_runs }) =>
      createSchedule(jobId, { cron_expression, max_runs: max_runs || null }),
    onSuccess: (_data, variables) => {
      toast.success("Schedule created successfully!");
      queryClient.invalidateQueries({ queryKey: ["schedule", variables.jobId] });
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Failed to create schedule");
    },
  });
};

export const usePauseSchedule = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId) => pauseSchedule(jobId),
    onSuccess: (_data, jobId) => {
      toast.success("Schedule paused");
      queryClient.invalidateQueries({ queryKey: ["schedule", jobId] });
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Failed to pause schedule");
    },
  });
};

export const useResumeSchedule = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId) => resumeSchedule(jobId),
    onSuccess: (_data, jobId) => {
      toast.success("Schedule resumed");
      queryClient.invalidateQueries({ queryKey: ["schedule", jobId] });
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Failed to resume schedule");
    },
  });
};

export const useDeleteSchedule = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId) => deleteSchedule(jobId),
    onSuccess: (_data, jobId) => {
      toast.success("Schedule deleted");
      queryClient.setQueryData(["schedule", jobId], null);
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || "Failed to delete schedule");
    },
  });
};
