import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createJob, getJob, deleteJob, getJobDependents } from "../api/jobs";
import toast from "react-hot-toast";

export const useCreateJob = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      toast.success("Job created successfully!");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err) => {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        toast.error(detail[0]?.msg?.replace("Value error, ", "") || "Failed to create job");
      } else if (typeof detail === "object" && detail?.message) {
        toast.error(detail.message);
      } else {
        toast.error(detail || "Failed to create job");
      }
    },
  });
};

export const useDeleteJob = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, cascade = false }) => deleteJob(jobId, cascade),
    onSuccess: () => {
      toast.success("Job deleted");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err) => {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === "object" ? detail.message : detail || "Failed to delete job");
    },
  });
};

export const useJob = (jobId) =>
  useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId),
    enabled: !!jobId,
  });

export const useJobDependents = (jobId) =>
  useQuery({
    queryKey: ["job-dependents", jobId],
    queryFn: () => getJobDependents(jobId),
    enabled: !!jobId,
  });
