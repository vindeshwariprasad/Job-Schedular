import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDLQ } from "../api/dlq";
import DLQTable from "../components/DLQTable";
import Pagination from "../components/Pagination";

const PAGE_SIZE = 20;

function SkeletonStats() {
  return (
    <div className="grid grid-cols-3 gap-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 animate-pulse">
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-20 mb-3" />
          <div className="h-7 bg-gray-200 dark:bg-gray-700 rounded w-12" />
        </div>
      ))}
    </div>
  );
}

function SkeletonTable() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-6 animate-pulse space-y-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-12" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded flex-1" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-16" />
        </div>
      ))}
    </div>
  );
}

export default function DLQ() {
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["dlq", page],
    queryFn: () => getDLQ(page, PAGE_SIZE),
    refetchInterval: 10000,
  });

  const entries = data?.items || [];
  const totalFailed = data?.total ?? 0;
  const uniqueJobs = new Set(entries.map((e) => e.job_id)).size;
  const mostRecent =
    entries.length > 0
      ? new Date(
          entries.reduce((latest, e) =>
            new Date(e.failed_at) > new Date(latest.failed_at) ? e : latest
          ).failed_at
        ).toLocaleString()
      : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dead Letter Queue</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Failed executions that exceeded retry limits. Replay is manual to
          prevent cascading failures.
        </p>
      </div>

      {/* Stats */}
      {isLoading ? (
        <SkeletonStats />
      ) : (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Total Failed
            </p>
            <p className="mt-1 text-2xl font-bold text-red-600">
              {totalFailed}
            </p>
          </div>
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Jobs Affected
            </p>
            <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
              {uniqueJobs}
            </p>
          </div>
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Latest Failure
            </p>
            <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
              {mostRecent || "None"}
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <SkeletonTable />
      ) : (
        <>
          <DLQTable entries={entries} />
          <Pagination
            page={page}
            size={PAGE_SIZE}
            total={totalFailed}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
