import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/auth";
import QueueStats from "../components/QueueStats";

function SkeletonCards() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-6 animate-pulse">
          <div className="flex items-start justify-between">
            <div className="space-y-3 flex-1">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24" />
              <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-16" />
            </div>
            <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Queues() {
  const { data, isLoading } = useQuery({
    queryKey: ["queue-stats"],
    queryFn: () =>
      api
        .get("/admin/dlq/queues")
        .then(res => res.data),
    refetchInterval: 3000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Queue Status
      </h1>

      <p className="text-gray-600 dark:text-gray-400 text-sm max-w-2xl">
        Live Redis queue metrics.
        Use this view to identify backlogs, stuck workers,
        or rising failure rates.
      </p>

      {isLoading ? (
        <SkeletonCards />
      ) : (
        <QueueStats stats={data} />
      )}
    </div>
  );
}
