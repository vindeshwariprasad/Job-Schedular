import { useState } from "react";

function StatCard({ title, value, color, hint }) {
  const [showHint, setShowHint] = useState(false);

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow hover:shadow-lg transition-shadow p-6 relative border border-gray-100 dark:border-gray-800">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
            {title}
            {hint && (
              <span
                className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-xs cursor-pointer select-none"
                onMouseEnter={() => setShowHint(true)}
                onMouseLeave={() => setShowHint(false)}
                onClick={() => setShowHint(!showHint)}
              >
                i
              </span>
            )}
          </div>
          <div className={`text-3xl font-bold mt-2 ${color}`}>
            {value}
          </div>
        </div>
        {/* <div className={`w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center`}>
          <div className={`w-3 h-3 rounded-full ${color.replace("text-", "bg-")}`} />
        </div> */}
      </div>
      {hint && showHint && (
        <div className="absolute top-1 right-2 bg-gray-800 dark:bg-gray-700 text-white text-xs rounded px-2 py-1 z-10 max-w-48">
          {hint}
        </div>
      )}
    </div>
  );
}

export default function QueueStats({ stats }) {
  if (!stats) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-6 text-gray-500 dark:text-gray-400">
        Loading queue stats...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard
          title="Ready Queue"
          value={stats.ready ?? 0}
          color="text-blue-600"
          hint="Total across all priority levels"
        />
        <StatCard
          title="Processing Queue"
          value={stats.processing ?? 0}
          color="text-yellow-600"
          hint="All users combined"
        />
        <StatCard
          title="Failed Queue"
          value={stats.failed ?? 0}
          color="text-red-600"
          hint="All users combined"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard
          title="Ready — High"
          value={stats.ready_high ?? 0}
          color="text-red-600"
          hint="High-priority jobs waiting"
        />
        <StatCard
          title="Ready — Medium"
          value={stats.ready_medium ?? 0}
          color="text-yellow-600"
          hint="Medium-priority jobs waiting"
        />
        <StatCard
          title="Ready — Low"
          value={stats.ready_low ?? 0}
          color="text-gray-600"
          hint="Low-priority jobs waiting"
        />
      </div>
    </div>
  );
}
