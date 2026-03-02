import { Link } from "react-router-dom";
import { useMetrics } from "../hooks/useMetrics";
import { useUserStats } from "../hooks/useUserStats";
import { useExecutions } from "../hooks/useExecutions";
import { useExecutionWebSocket } from "../hooks/useExecutionWebSocket";
import MetricCard from "../components/MetricCard";
import ExecutionTable from "../components/ExecutionTable";
import QueueStats from "../components/QueueStats";
import WebSocketStatus from "../components/WebSocketStatus";

function SkeletonCard() {
  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="space-y-3 flex-1">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24" />
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-16" />
        </div>
        <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
      </div>
    </div>
  );
}

function SkeletonTable() {
  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800 animate-pulse space-y-4">
      <div className="flex justify-between">
        <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-40" />
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
      </div>
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded flex-1" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32" />
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const wsStatus = useExecutionWebSocket();
  const { data: metrics, isLoading: metricsLoading } = useMetrics();
  const { data: userStats, isLoading: statsLoading } = useUserStats();
  const { data: executions, isLoading: execLoading } =
    useExecutions();

  const isLoading = metricsLoading || execLoading || statsLoading;

  const safeStats = userStats ?? { total_executions: 0, success: 0, failed: 0, dlq: 0 };
  const safeMetrics = metrics ?? { queueReady: 0, queueProcessing: 0, queueFailed: 0 };

  const successRate =
    safeStats.total_executions > 0
      ? Math.round((safeStats.success / safeStats.total_executions) * 100)
      : 0;

  return (
    <div className="space-y-10">
      {/* HEADER */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-gray-500 dark:text-gray-400">
            Real-time overview of scheduler health
          </p>
        </div>
        <WebSocketStatus status={wsStatus} />
      </div>

      {/* KPI ROW */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <MetricCard
            title="Total Executions"
            value={safeStats.total_executions}
            color="text-blue-600"
            hint="Your executions only"
          />
          <MetricCard
            title="Success Rate"
            value={`${successRate}%`}
            color="text-green-600"
            hint="Your executions only"
          />
          <MetricCard
            title="Failed Jobs"
            value={safeStats.failed}
            color="text-red-600"
            hint="Your executions only"
          />
          <MetricCard
            title="DLQ Jobs"
            value={safeStats.dlq}
            color="text-purple-600"
            hint="Your executions only"
          />
        </div>
      )}

      {/* QUEUE PRESSURE */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="grid grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <QueueStats
            stats={{
              ready: safeMetrics.queueReady,
              processing: safeMetrics.queueProcessing,
              failed: safeMetrics.queueFailed ?? 0,
            }}
          />

          <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800">
            <h2 className="font-semibold text-gray-900 dark:text-white mb-4">
              Worker Load
            </h2>

            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Ready Queue</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  {safeMetrics.queueReady}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Processing Queue</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  {safeMetrics.queueProcessing}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* RECENT EXECUTIONS */}
      {isLoading ? (
        <SkeletonTable />
      ) : (
        <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800">
          <div className="flex justify-between mb-4">
            <h2 className="font-semibold text-gray-900 dark:text-white">
              Recent Executions
            </h2>
            <Link
              to="/executions"
              className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
            >
              View all &rarr;
            </Link>
          </div>

          <ExecutionTable executions={executions?.items} />
        </div>
      )}
    </div>
  );
}
