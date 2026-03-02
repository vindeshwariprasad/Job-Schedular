import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExecutions } from "../api/executions";
import { useExecutionWebSocket } from "../hooks/useExecutionWebSocket";
import ExecutionTable from "../components/ExecutionTable";
import WebSocketStatus from "../components/WebSocketStatus";
import Pagination from "../components/Pagination";

const STATUSES = ["ALL", "PENDING", "RUNNING", "SUCCESS", "FAILED"];
const PAGE_SIZE = 20;

function SkeletonTable() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-6 animate-pulse space-y-4">
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-full" />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded flex-1" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-16" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-12" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
        </div>
      ))}
    </div>
  );
}

export default function Executions() {
  const wsStatus = useExecutionWebSocket();
  const [status, setStatus] = useState("ALL");
  const [page, setPage] = useState(1);

  const statusParam = status === "ALL" ? null : status;

  // When WebSocket is connected, rely on push updates (query invalidation).
  // Fall back to 30s polling when disconnected.
  const refetchInterval = wsStatus === "connected" ? false : 30000;

  const { data: executions, isLoading } = useQuery({
    queryKey: ["executions", status, page],
    queryFn: () => getExecutions(statusParam, page, PAGE_SIZE),
    refetchInterval,
  });

  // Reset to page 1 when filter changes
  const handleStatusChange = (e) => {
    setStatus(e.target.value);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Executions</h1>
          <WebSocketStatus status={wsStatus} />
        </div>

        <select
          className="border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={status}
          onChange={handleStatusChange}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <SkeletonTable />
      ) : (
        <>
          <ExecutionTable executions={executions?.items} />
          <Pagination
            page={page}
            size={PAGE_SIZE}
            total={executions?.total ?? 0}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
