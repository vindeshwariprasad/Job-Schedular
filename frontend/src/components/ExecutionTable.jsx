import React from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from "@tanstack/react-table";

const statusConfig = {
  PENDING: {
    dot: "bg-yellow-400",
    text: "text-yellow-700 dark:text-yellow-400",
    bg: "bg-yellow-50 dark:bg-yellow-900/30",
    border: "border-yellow-200 dark:border-yellow-800",
  },
  RUNNING: {
    dot: "bg-blue-400",
    text: "text-blue-700 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/30",
    border: "border-blue-200 dark:border-blue-800",
  },
  SUCCESS: {
    dot: "bg-green-400",
    text: "text-green-700 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/30",
    border: "border-green-200 dark:border-green-800",
  },
  FAILED: {
    dot: "bg-red-400",
    text: "text-red-700 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-900/30",
    border: "border-red-200 dark:border-red-800",
  },
};

function StatusBadge({ status }) {
  const config = statusConfig[status] || statusConfig.PENDING;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${config.bg} ${config.text} ${config.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />
      {status}
    </span>
  );
}

export default function ExecutionTable({ executions }) {
  const columns = React.useMemo(
    () => [
      {
        header: "Execution ID",
        accessorKey: "execution_id",
      },
      {
        header: "Job ID",
        accessorKey: "job_id",
      },
      {
        header: "Status",
        accessorKey: "status",
        cell: ({ getValue }) => <StatusBadge status={getValue()} />,
      },
      {
        header: "Attempt",
        accessorKey: "attempt",
      },
      {
        header: "Started At",
        accessorKey: "started_at",
        cell: ({ getValue }) =>
          getValue()
            ? new Date(getValue()).toLocaleString()
            : "-",
      },
      {
        header: "Finished At",
        accessorKey: "finished_at",
        cell: ({ getValue }) =>
          getValue()
            ? new Date(getValue()).toLocaleString()
            : "-",
      },
    ],
    []
  );

  const table = useReactTable({
    data: executions ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow border border-gray-100 dark:border-gray-800 overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-50 dark:bg-gray-800/50">
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(header => (
                <th
                  key={header.id}
                  className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300"
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext()
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>

        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr key={row.id} className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              {row.getVisibleCells().map(cell => (
                <td key={cell.id} className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                  {flexRender(
                    cell.column.columnDef.cell ??
                      cell.column.columnDef.accessorKey,
                    cell.getContext()
                  )}
                </td>
              ))}
            </tr>
          ))}

          {executions?.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center py-12 text-gray-500 dark:text-gray-400"
              >
                <svg className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600 mb-3" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
                </svg>
                <p className="font-medium">No executions found</p>
                <p className="text-sm mt-1">Executions will appear here once jobs start running.</p>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
