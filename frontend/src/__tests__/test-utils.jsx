import React from "react";
import { render } from "@testing-library/react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../context/ThemeContext";
import { AuthProvider } from "../context/AuthContext";

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// Full app wrapper with all providers
export function AllProviders({ children, initialEntries = ["/"] }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// Wrapper without auth (for testing auth context itself)
export function ProvidersWithoutAuth({ children }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>{children}</ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

// Wrapper with only QueryClient (for hook testing)
export function QueryWrapper({ children }) {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

export function renderWithProviders(ui, options = {}) {
  const { initialEntries = ["/"], ...renderOptions } = options;
  return render(ui, {
    wrapper: ({ children }) => (
      <AllProviders initialEntries={initialEntries}>{children}</AllProviders>
    ),
    ...renderOptions,
  });
}

// Mock data factories
export const mockUser = {
  id: 1,
  username: "testuser",
  email: "test@example.com",
};

export const mockJobs = {
  items: [
    {
      id: 1,
      name: "API Health Check",
      task_type: "api_call",
      payload: { url: "https://example.com/health", method: "GET" },
      rate_limit_per_min: 60,
      is_active: true,
    },
    {
      id: 2,
      name: "String Job",
      task_type: "string_manipulation",
      payload: { input: "hello" },
      rate_limit_per_min: 30,
      is_active: false,
    },
  ],
  total: 2,
  page: 1,
  size: 20,
};

export const mockExecutions = {
  items: [
    {
      execution_id: "exec-1111-2222-3333-444444444444",
      job_id: 1,
      status: "SUCCESS",
      attempt: 1,
      started_at: "2024-01-01T10:00:00Z",
      finished_at: "2024-01-01T10:00:05Z",
    },
    {
      execution_id: "exec-5555-6666-7777-888888888888",
      job_id: 2,
      status: "FAILED",
      attempt: 3,
      started_at: "2024-01-01T11:00:00Z",
      finished_at: "2024-01-01T11:00:10Z",
    },
    {
      execution_id: "exec-aaaa-bbbb-cccc-dddddddddddd",
      job_id: 1,
      status: "PENDING",
      attempt: 1,
      started_at: null,
      finished_at: null,
    },
    {
      execution_id: "exec-eeee-ffff-0000-111111111111",
      job_id: 1,
      status: "RUNNING",
      attempt: 1,
      started_at: "2024-01-01T12:00:00Z",
      finished_at: null,
    },
  ],
  total: 4,
  page: 1,
  size: 20,
};

export const mockDLQEntries = {
  items: [
    {
      id: 1,
      execution_id: "dlq-1111-2222-3333-444444444444",
      job_id: 1,
      error: "Connection timeout after 30s",
      payload: { job_id: 1, execution_id: "dlq-1111-2222-3333-444444444444" },
      failed_at: "2024-01-01T12:00:00Z",
    },
    {
      id: 2,
      execution_id: "dlq-5555-6666-7777-888888888888",
      job_id: 2,
      error: "HTTP 500 Internal Server Error",
      payload: { job_id: 2, execution_id: "dlq-5555-6666-7777-888888888888" },
      failed_at: "2024-01-02T08:30:00Z",
    },
  ],
  total: 2,
  page: 1,
  size: 20,
};

export const mockSchedule = {
  status: "active",
  cron_expression: "*/5 * * * *",
  next_run_at: "2024-01-01T12:05:00Z",
  run_count: 10,
  max_runs: 100,
};

export const mockUserStats = {
  total_executions: 150,
  success: 120,
  failed: 25,
  dlq: 5,
};

export const mockGlobalStats = {
  total_executions: 5000,
  success: 4200,
  failed: 700,
  dlq: 100,
};

export const mockMetricsText = `# HELP job_executions_total Total job executions
# TYPE job_executions_total counter
job_executions_total 500
# HELP job_success_total Total successful executions
# TYPE job_success_total counter
job_success_total 400
# HELP job_failure_total Total failed executions
# TYPE job_failure_total counter
job_failure_total 80
# HELP job_dlq_total Total DLQ entries
# TYPE job_dlq_total counter
job_dlq_total 20
# HELP queue_ready_size Ready queue size
# TYPE queue_ready_size gauge
queue_ready_size 5
# HELP queue_processing_size Processing queue size
# TYPE queue_processing_size gauge
queue_processing_size 3
# HELP queue_failed_size Failed queue size
# TYPE queue_failed_size gauge
queue_failed_size 2
`;

export const mockExecutionHistory = [
  { date: "2024-01-01", total: 50, success: 40, failed: 10 },
  { date: "2024-01-02", total: 60, success: 55, failed: 5 },
  { date: "2024-01-03", total: 45, success: 42, failed: 3 },
];

export const mockQueueStats = {
  ready: 5,
  processing: 3,
  failed: 2,
};
