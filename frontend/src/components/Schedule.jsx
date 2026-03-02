import { useState } from "react";
import {
  useSchedule,
  useCreateSchedule,
  usePauseSchedule,
  useResumeSchedule,
  useDeleteSchedule,
} from "../hooks/useSchedules";
import ConfirmModal from "./ConfirmModal";

function buildCron(interval, unit) {
  const n = parseInt(interval, 10);
  if (!n || n < 1) return null;

  switch (unit) {
    case "minutes":
      return `*/${n} * * * *`;
    case "hours":
      return `0 */${n} * * *`;
    case "days":
      return `0 0 */${n} * *`;
    default:
      return null;
  }
}

function describeCron(cron) {
  const minMatch = cron.match(/^\*\/(\d+) \* \* \* \*$/);
  if (minMatch) return `Every ${minMatch[1]} minute${minMatch[1] === "1" ? "" : "s"}`;

  const hrMatch = cron.match(/^0 \*\/(\d+) \* \* \*$/);
  if (hrMatch) return `Every ${hrMatch[1]} hour${hrMatch[1] === "1" ? "" : "s"}`;

  const dayMatch = cron.match(/^0 0 \*\/(\d+) \* \*$/);
  if (dayMatch) return `Every ${dayMatch[1]} day${dayMatch[1] === "1" ? "" : "s"}`;

  return cron;
}

export default function ScheduleSection({ jobId }) {
  const [repeatInterval, setRepeatInterval] = useState("");
  const [unit, setUnit] = useState("minutes");
  const [maxRuns, setMaxRuns] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: schedule } = useSchedule(jobId);
  const createMutation = useCreateSchedule();
  const pauseMutation = usePauseSchedule();
  const resumeMutation = useResumeSchedule();
  const deleteMutation = useDeleteSchedule();

  const handleSchedule = () => {
    const cron = buildCron(repeatInterval, unit);
    if (!cron) return;

    createMutation.mutate({
      jobId,
      cron_expression: cron,
      max_runs: maxRuns ? parseInt(maxRuns, 10) : null,
    });
  };

  const handlePause = () => pauseMutation.mutate(jobId);
  const handleResume = () => resumeMutation.mutate(jobId);
  const handleDelete = () => {
    deleteMutation.mutate(jobId, {
      onSuccess: () => setShowDeleteConfirm(false),
    });
  };

  // Schedule exists — show status and controls
  if (schedule) {
    const statusColors = {
      active: "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800",
      paused: "bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-800",
      completed: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700",
    };

    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-white">Schedule</h2>
          <span
            className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
              statusColors[schedule.status] || "bg-gray-100 dark:bg-gray-800"
            }`}
          >
            {schedule.status.toUpperCase()}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-500 dark:text-gray-400">Repeat:</span>{" "}
            <span className="font-medium text-gray-900 dark:text-white">
              {describeCron(schedule.cron_expression)}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Next Run:</span>{" "}
            <span className="text-gray-900 dark:text-white">
              {schedule.next_run_at
                ? new Date(schedule.next_run_at).toLocaleString()
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Runs:</span>{" "}
            <span className="text-gray-900 dark:text-white">
              {schedule.run_count}
              {schedule.max_runs ? ` / ${schedule.max_runs}` : " (unlimited)"}
            </span>
          </div>
        </div>

        <div className="flex gap-2">
          {schedule.status === "active" && (
            <button
              onClick={handlePause}
              disabled={pauseMutation.isPending}
              className="bg-yellow-500 hover:bg-yellow-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {pauseMutation.isPending ? "Pausing..." : "Pause"}
            </button>
          )}

          {schedule.status === "paused" && (
            <button
              onClick={handleResume}
              disabled={resumeMutation.isPending}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {resumeMutation.isPending ? "Resuming..." : "Resume"}
            </button>
          )}

          <button
            onClick={() => setShowDeleteConfirm(true)}
            disabled={deleteMutation.isPending}
            className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {deleteMutation.isPending ? "Deleting..." : "Delete"}
          </button>
        </div>

        <ConfirmModal
          open={showDeleteConfirm}
          title="Delete Schedule"
          message="This will permanently delete the schedule. The job itself will not be affected."
          confirmLabel={deleteMutation.isPending ? "Deleting..." : "Delete"}
          variant="danger"
          loading={deleteMutation.isPending}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      </div>
    );
  }

  // No schedule — show creation form
  const preview = buildCron(repeatInterval, unit);

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-4 space-y-3">
      <h2 className="font-semibold text-gray-900 dark:text-white">Schedule Job</h2>

      <div className="flex gap-2">
        <span className="text-sm text-gray-600 dark:text-gray-400 self-center whitespace-nowrap">
          Run every
        </span>
        <input
          type="number"
          placeholder="5"
          min="1"
          value={repeatInterval}
          onChange={(e) => setRepeatInterval(e.target.value)}
          className="border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-24 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="minutes">Minutes</option>
          <option value="hours">Hours</option>
          <option value="days">Days</option>
        </select>
      </div>

      {preview && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Cron: <span className="font-mono">{preview}</span>
        </p>
      )}

      <input
        type="number"
        placeholder="Max runs (leave empty for unlimited)"
        min="1"
        value={maxRuns}
        onChange={(e) => setMaxRuns(e.target.value)}
        className="border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <button
        onClick={handleSchedule}
        disabled={createMutation.isPending || !preview}
        className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium disabled:opacity-50 transition-colors"
      >
        {createMutation.isPending ? "Scheduling..." : "Schedule"}
      </button>
    </div>
  );
}
