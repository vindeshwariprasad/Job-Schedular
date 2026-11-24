import { useState } from "react";
import { useCreateJob } from "../hooks/useJobs";
import JobTable from "../components/JobTable";
import Pagination from "../components/Pagination";
import DependencyPicker from "../components/DependencyPicker";
import { useQuery } from "@tanstack/react-query";
import { getJobs } from "../api/jobs";

const PAGE_SIZE = 20;

const INITIAL_FORM = {
  name: "",
  task_type: "api_call",
  url: "",
  method: "GET",
  input: "",
  expression: "",
  rate_limit_per_min: 60,
  priority: "MEDIUM",
  depends_on_job_ids: [],
};

const inputClass =
  "border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white p-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500";

function SkeletonTable() {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 p-6 animate-pulse space-y-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-12" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded flex-1" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-16" />
        </div>
      ))}
    </div>
  );
}

export default function Jobs() {
  const [page, setPage] = useState(1);
  const [form, setForm] = useState(INITIAL_FORM);

  const createJob = useCreateJob();

  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs", page],
    queryFn: () => getJobs(page, PAGE_SIZE),
  });

  // Also fetch all jobs (unpaginated) for the dependency picker
  const { data: allJobs } = useQuery({
    queryKey: ["jobs", "all"],
    queryFn: () => getJobs(1, 500),
  });

  const buildPayload = () => {
    if (form.task_type === "api_call") {
      return { url: form.url, method: form.method };
    }
    if (form.task_type === "string_manipulation") {
      return { input: form.input };
    }
    return { expression: form.expression };
  };

  const submit = (e) => {
    e.preventDefault();
    const data = {
      name: form.name,
      task_type: form.task_type,
      payload: buildPayload(),
      rate_limit_per_min: form.rate_limit_per_min,
      priority: form.priority,
    };
    if (form.depends_on_job_ids.length > 0) {
      data.depends_on_job_ids = form.depends_on_job_ids;
    }
    createJob.mutate(data);
    setForm(INITIAL_FORM);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Jobs</h1>

      {/* Create Job */}
      <form
        onSubmit={submit}
        className="bg-white dark:bg-gray-900 p-4 rounded-xl shadow border border-gray-100 dark:border-gray-800 space-y-3"
      >
        <div className="grid grid-cols-2 gap-3">
          <input
            className={inputClass}
            placeholder="Job name"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            required
          />

          <select
            className={inputClass}
            value={form.task_type}
            onChange={e =>
              setForm({ ...form, task_type: e.target.value })
            }
          >
            <option value="api_call">API Call</option>
            <option value="string_manipulation">String Manipulation</option>
            <option value="math">Math</option>
          </select>
        </div>

        {/* Dynamic fields based on task type */}
        {form.task_type === "api_call" && (
          <div className="grid grid-cols-4 gap-3">
            <select
              className={inputClass}
              value={form.method}
              onChange={e => setForm({ ...form, method: e.target.value })}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
            </select>
            <input
              className={`${inputClass} col-span-3`}
              placeholder="https://example.com/api/endpoint"
              value={form.url}
              onChange={e => setForm({ ...form, url: e.target.value })}
              required
            />
          </div>
        )}

        {form.task_type === "string_manipulation" && (
          <input
            className={`${inputClass} w-full`}
            placeholder="Enter any text to uppercase"
            value={form.input}
            onChange={e => setForm({ ...form, input: e.target.value })}
            required
          />
        )}

        {form.task_type === "math" && (
          <input
            className={`${inputClass} w-full`}
            placeholder="2 + 3 * (4 - 1)"
            value={form.expression}
            onChange={e => setForm({ ...form, expression: e.target.value })}
            required
          />
        )}

        {/* Dependency picker */}
        <DependencyPicker
          jobs={allJobs?.items || []}
          selectedIds={form.depends_on_job_ids}
          onChange={(ids) => setForm({ ...form, depends_on_job_ids: ids })}
        />

        <div className="flex gap-3">
          <input
            type="number"
            min="1"
            className={`${inputClass} w-40`}
            placeholder="Rate limit / min"
            value={form.rate_limit_per_min}
            onChange={e =>
              setForm({
                ...form,
                rate_limit_per_min: Number(e.target.value),
              })
            }
          />

          <select
            className={inputClass}
            value={form.priority}
            onChange={e => setForm({ ...form, priority: e.target.value })}
          >
            <option value="HIGH">High Priority</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>

          <button
            className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-6 py-2 font-medium transition-colors disabled:opacity-50"
            disabled={createJob.isPending}
          >
            {createJob.isPending ? "Creating..." : "Create Job"}
          </button>
        </div>
      </form>

      {/* Jobs Table */}
      {isLoading ? (
        <SkeletonTable />
      ) : (
        <>
          <JobTable jobs={jobs?.items} />
          <Pagination
            page={page}
            size={PAGE_SIZE}
            total={jobs?.total ?? 0}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
