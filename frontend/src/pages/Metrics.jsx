import React from "react";
import { useMetrics } from "../hooks/useMetrics";
import { useGlobalStats } from "../hooks/useGlobalStats";
import { useExecutionHistory } from "../hooks/useExecutionHistory";
import MetricCard from "../components/MetricCard";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useTheme } from "../context/ThemeContext";

function SkeletonCards() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div key={i} className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800 animate-pulse">
          <div className="flex items-start justify-between">
            <div className="space-y-3 flex-1">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-28" />
              <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-16" />
            </div>
            <div className="w-10 h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

function SkeletonChart() {
  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800 animate-pulse">
      <div className="h-5 bg-gray-200 dark:bg-gray-700 rounded w-36 mb-6" />
      <div className="h-[250px] bg-gray-200 dark:bg-gray-700 rounded" />
    </div>
  );
}

export default function Metrics() {
  const { data: metrics, isLoading: metricsLoading } = useMetrics();
  const { data: globalStats, isLoading: statsLoading } = useGlobalStats();
  const { data: history, isLoading: historyLoading } = useExecutionHistory();
  const { theme } = useTheme();

  const isLoading = metricsLoading || statsLoading || historyLoading;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">System Metrics</h1>
        <p className="text-gray-500 dark:text-gray-400">Aggregated data across all users</p>
      </div>

      {/* KPI CARDS */}
      {isLoading ? (
        <SkeletonCards />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <MetricCard
            title="Total Executions"
            value={globalStats.total_executions}
            color="text-blue-600"
            hint="All users combined"
          />
          <MetricCard
            title="Successful Jobs"
            value={globalStats.success}
            color="text-green-600"
            hint="All users combined"
          />
          <MetricCard
            title="Failed Jobs"
            value={globalStats.failed}
            color="text-red-600"
            hint="All users combined"
          />
          <MetricCard
            title="DLQ Jobs"
            value={globalStats.dlq}
            color="text-purple-600"
            hint="All users combined"
          />
          <MetricCard
            title="Ready Queue"
            value={metrics.queueReady}
            color="text-indigo-600"
            hint="All users combined"
          />
          <MetricCard
            title="Processing Queue"
            value={metrics.queueProcessing}
            color="text-yellow-600"
            hint="All users combined"
          />
        </div>
      )}

      {/* EXECUTION TREND */}
      {isLoading ? (
        <SkeletonChart />
      ) : (
        <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow border border-gray-100 dark:border-gray-800">
          <h2 className="font-semibold mb-4 text-gray-900 dark:text-white">
            Execution Trend
          </h2>

          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={history}>
              <XAxis
                dataKey="date"
                stroke={theme === "dark" ? "#9ca3af" : "#6b7280"}
                tick={{ fill: theme === "dark" ? "#9ca3af" : "#6b7280" }}
              />
              <YAxis
                stroke={theme === "dark" ? "#9ca3af" : "#6b7280"}
                tick={{ fill: theme === "dark" ? "#9ca3af" : "#6b7280" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: theme === "dark" ? "#1f2937" : "#fff",
                  border: `1px solid ${theme === "dark" ? "#374151" : "#e5e7eb"}`,
                  borderRadius: "8px",
                  color: theme === "dark" ? "#f9fafb" : "#111827",
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="total"
                name="Total"
                stroke="#2563eb"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="success"
                name="Success"
                stroke="#16a34a"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="failed"
                name="Failed"
                stroke="#dc2626"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
