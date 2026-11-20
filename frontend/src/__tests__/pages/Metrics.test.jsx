import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Metrics from "../../pages/Metrics";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock("../../hooks/useMetrics", () => ({
  useMetrics: () => ({
    data: {
      executions: 500,
      success: 400,
      failures: 80,
      dlq: 20,
      queueReady: 5,
      queueProcessing: 3,
      queueFailed: 2,
    },
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useGlobalStats", () => ({
  useGlobalStats: () => ({
    data: { total_executions: 5000, success: 4200, failed: 700, dlq: 100 },
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useExecutionHistory", () => ({
  useExecutionHistory: () => ({
    data: [
      { date: "2024-01-01", total: 50, success: 40, failed: 10 },
      { date: "2024-01-02", total: 60, success: 55, failed: 5 },
    ],
    isLoading: false,
  }),
}));

// Mock recharts to avoid ResizeObserver issues
vi.mock("recharts", () => ({
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
}));

function renderMetrics() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <Metrics />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Metrics Page", () => {
  it("renders page title and description", () => {
    renderMetrics();
    expect(screen.getByText("System Metrics")).toBeInTheDocument();
    expect(screen.getByText("Aggregated data across all users")).toBeInTheDocument();
  });

  it("renders KPI cards with global stats", () => {
    renderMetrics();
    expect(screen.getByText("Total Executions")).toBeInTheDocument();
    expect(screen.getByText("5000")).toBeInTheDocument();
    expect(screen.getByText("Successful Jobs")).toBeInTheDocument();
    expect(screen.getByText("4200")).toBeInTheDocument();
    expect(screen.getByText("Failed Jobs")).toBeInTheDocument();
    expect(screen.getByText("700")).toBeInTheDocument();
    expect(screen.getByText("DLQ Jobs")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("renders queue metric cards", () => {
    renderMetrics();
    expect(screen.getByText("Ready Queue")).toBeInTheDocument();
    expect(screen.getByText("Processing Queue")).toBeInTheDocument();
  });

  it("renders execution trend chart", () => {
    renderMetrics();
    expect(screen.getByText("Execution Trend")).toBeInTheDocument();
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });
});
