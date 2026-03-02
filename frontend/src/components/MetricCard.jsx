import { useState } from "react";

export default function MetricCard({ title, value, color, hint }) {
  const [showHint, setShowHint] = useState(false);

  return (
    <div className="bg-white dark:bg-gray-900 p-6 rounded-xl shadow hover:shadow-lg transition-shadow relative border border-gray-100 dark:border-gray-800">
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
          <div className={`text-3xl font-bold mt-2 ${color} dark:opacity-90`}>
            {value}
          </div>
        </div>
        {/* {icon ? (
          <div className={`p-2.5 rounded-lg ${iconBg}`}>
            {icon}
          </div>
        ) : (
          <div className={`w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center`}>
            <div className={`w-3 h-3 rounded-full ${color.replace("text-", "bg-")}`} />
          </div>
        )} */}
      </div>
      {hint && showHint && (
        <div className="absolute top-1 right-2 bg-gray-800 dark:bg-gray-700 text-white text-xs rounded px-2 py-1 z-10 max-w-48">
          {hint}
        </div>
      )}
    </div>
  );
}
