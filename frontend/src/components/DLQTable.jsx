import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/auth";
import toast from "react-hot-toast";
import JsonView from "@uiw/react-json-view";
import ConfirmModal from "./ConfirmModal";

export default function DLQTable({ entries }) {
  const queryClient = useQueryClient();

  const [replayed, setReplayed] = useState(new Set());
  const [confirmTarget, setConfirmTarget] = useState(null);

  const replayMutation = useMutation({
    mutationFn: (executionId) =>
      api.post(`/admin/dlq/${executionId}/replay`).then((r) => r.data),
    onSuccess: (data, executionId) => {
      queryClient.invalidateQueries({ queryKey: ["dlq"] });
      queryClient.invalidateQueries({ queryKey: ["executions"] });

      setReplayed((prev) => new Set(prev).add(executionId));
      setConfirmTarget(null);

      if (data.status === "already_in_flight") {
        toast("Already in flight — a pending execution exists for this job.", {
          icon: "⏳",
        });
      } else {
        toast.success("Execution replayed successfully.");
      }
    },
    onError: (err) => {
      setConfirmTarget(null);
      toast.error(
        err.response?.data?.detail || "Replay failed. Please try again."
      );
    },
  });

  const openConfirm = (executionId) => setConfirmTarget(executionId);
  const closeConfirm = () => {
    if (!replayMutation.isPending) setConfirmTarget(null);
  };

  // Empty state
  if (entries.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-16 text-center">
        <svg
          className="mx-auto h-12 w-12 text-green-400"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth="1.5"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
          />
        </svg>
        <h3 className="mt-3 text-sm font-semibold text-gray-900 dark:text-white">
          No failed executions
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          All jobs are executing successfully. The DLQ is empty.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Execution ID
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Job
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Error
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Payload
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Failed At
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Action
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {entries.map((row) => {
              const isReplayed = replayed.has(row.execution_id);
              return (
                <tr
                  key={row.id}
                  className={`align-top transition-colors ${
                    isReplayed
                      ? "bg-green-50/50 dark:bg-green-900/10"
                      : "hover:bg-gray-50 dark:hover:bg-gray-800/50"
                  }`}
                >
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono text-gray-600 dark:text-gray-400">
                      {row.execution_id.slice(0, 8)}...
                    </span>
                  </td>

                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-md bg-gray-100 dark:bg-gray-800 px-2 py-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                      #{row.job_id}
                    </span>
                  </td>

                  <td className="px-4 py-3 max-w-xs">
                    <p className="text-sm text-red-600 dark:text-red-400 truncate" title={row.error}>
                      {row.error}
                    </p>
                  </td>

                  <td className="px-4 py-3 text-sm max-w-sm">
                    <JsonView
                      value={row.payload}
                      collapsed={1}
                      enableClipboard={false}
                      displayDataTypes={false}
                      style={{ fontSize: 12 }}
                    />
                  </td>

                  <td className="px-4 py-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {new Date(row.failed_at).toLocaleString()}
                    </span>
                  </td>

                  <td className="px-4 py-3 text-right">
                    {isReplayed ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-900/30 px-2.5 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                        </svg>
                        Replayed
                      </span>
                    ) : (
                      <button
                        onClick={() => openConfirm(row.execution_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-blue-700 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/50 hover:border-blue-300 transition-colors"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                        </svg>
                        Replay
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmModal
        open={!!confirmTarget}
        title="Replay Execution"
        message="This will create a new execution and re-enqueue the job. If a pending execution already exists for this job, it will be skipped."
        confirmLabel={replayMutation.isPending ? "Replaying..." : "Replay"}
        variant="info"
        loading={replayMutation.isPending}
        onConfirm={() => replayMutation.mutate(confirmTarget)}
        onCancel={closeConfirm}
      />
    </>
  );
}
