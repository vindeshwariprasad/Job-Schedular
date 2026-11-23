import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useJob, useDeleteJob } from "../hooks/useJobs";
import JsonViewer from "../components/JsonViewer";
import ScheduleSection from "../components/Schedule";
import ConfirmModal from "../components/ConfirmModal";

function SkeletonDetail() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-32" />
        <div className="h-9 bg-gray-200 dark:bg-gray-700 rounded w-24" />
      </div>
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-48" />
        ))}
      </div>
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 space-y-3">
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-20" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    </div>
  );
}

export default function JobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { data: job, isLoading } = useJob(jobId);
  const deleteJobMutation = useDeleteJob();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleDeleteJob = () => {
    deleteJobMutation.mutate(job.id, {
      onSuccess: () => {
        setShowDeleteConfirm(false);
        navigate("/jobs");
      },
    });
  };

  if (isLoading) return <SkeletonDetail />;
  if (!job) return (
    <div className="text-center py-16">
      <svg className="mx-auto h-12 w-12 text-gray-300 dark:text-gray-600 mb-3" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
      <p className="font-medium text-gray-900 dark:text-white">Job not found</p>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">This job may have been deleted.</p>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Job #{job.id}</h1>
        <button
          onClick={() => setShowDeleteConfirm(true)}
          disabled={deleteJobMutation.isPending}
          className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {deleteJobMutation.isPending ? "Deleting..." : "Delete Job"}
        </button>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 space-y-2">
        <p className="text-gray-700 dark:text-gray-300"><strong className="text-gray-900 dark:text-white">Name:</strong> {job.name}</p>
        <p className="text-gray-700 dark:text-gray-300"><strong className="text-gray-900 dark:text-white">Type:</strong> {job.task_type}</p>
        <p className="text-gray-700 dark:text-gray-300"><strong className="text-gray-900 dark:text-white">Rate limit:</strong> {job.rate_limit_per_min} / min</p>
        <p className="text-gray-700 dark:text-gray-300">
          <strong className="text-gray-900 dark:text-white">Priority:</strong>{" "}
          {(() => {
            const p = job.priority ?? "MEDIUM";
            const styles = {
              HIGH: "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800",
              MEDIUM: "bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800",
              LOW: "bg-gray-50 dark:bg-gray-800/50 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700",
            };
            return (
              <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold border ${styles[p] || styles.MEDIUM}`}>
                {p}
              </span>
            );
          })()}
        </p>
        <p className="text-gray-700 dark:text-gray-300">
          <strong className="text-gray-900 dark:text-white">Status:</strong>{" "}
          {job.is_active ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Active
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
              Inactive
            </span>
          )}
        </p>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4">
        <h2 className="font-semibold mb-2 text-gray-900 dark:text-white">Payload</h2>
        <JsonViewer data={job.payload} />
      </div>

      <ScheduleSection jobId={job.id} />

      <ConfirmModal
        open={showDeleteConfirm}
        title="Delete Job"
        message="This will permanently delete the job, its schedule, and all execution history. This action cannot be undone."
        confirmLabel={deleteJobMutation.isPending ? "Deleting..." : "Delete"}
        variant="danger"
        loading={deleteJobMutation.isPending}
        onConfirm={handleDeleteJob}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
}
