import { useState } from "react";
import { useJobDependents } from "../hooks/useJobs";

export default function DeleteJobDialog({
  open,
  jobId,
  jobName,
  loading = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  // Render inner component only when open — cascade state resets on each mount
  return (
    <DeleteJobDialogContent
      jobId={jobId}
      jobName={jobName}
      loading={loading}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

function DeleteJobDialogContent({ jobId, jobName, loading, onConfirm, onCancel }) {
  const [cascade, setCascade] = useState(false);
  const { data, isLoading } = useJobDependents(jobId);

  const dependents = data?.dependents || [];
  const hasDependents = dependents.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-gray-900/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      <div className="relative bg-white dark:bg-gray-900 rounded-xl shadow-2xl max-w-md w-full mx-4 p-6 border border-gray-100 dark:border-gray-800 animate-fade-in">
        <div className="flex gap-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Delete Job #{jobId}: {jobName}
            </h3>

            {isLoading ? (
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Checking for dependent jobs...
              </p>
            ) : hasDependents ? (
              <>
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                  This job has dependent jobs:
                </p>
                <ul className="mt-1 ml-4 list-disc text-sm text-gray-600 dark:text-gray-400">
                  {dependents.map((d) => (
                    <li key={d.id}>
                      Job #{d.id}: {d.name}
                    </li>
                  ))}
                </ul>

                <div className="mt-4 space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="radio"
                      name="cascade"
                      checked={!cascade}
                      onChange={() => setCascade(false)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    Remove dependencies only
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      (dependent jobs become independent)
                    </span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="radio"
                      name="cascade"
                      checked={cascade}
                      onChange={() => setCascade(true)}
                      className="text-red-600 focus:ring-red-500"
                    />
                    Delete all dependent jobs
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      (recursive — removes entire chain)
                    </span>
                  </label>
                </div>
              </>
            ) : (
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                This will permanently delete the job, its schedule, and all execution
                history. This action cannot be undone.
              </p>
            )}
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(cascade)}
            disabled={loading || isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 flex items-center gap-2"
          >
            {loading && (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {loading ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
