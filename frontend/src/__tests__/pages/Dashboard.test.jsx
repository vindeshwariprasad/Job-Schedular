import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Dashboard from "../../pages/Dashboard";

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
    data: { executions: 500, success: 400, failures: 80, dlq: 20, queueReady: 5, queueProcessing: 3, queueFailed: 2 },
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useUserStats", () => ({
  useUserStats: () => ({
    data: { total_executions: 150, success: 120, failed: 25, dlq: 5 },
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useExecutions", () => ({
  useExecutions: () => ({
    data: { items: [], total: 0 },
    isLoading: false,
  }),
}));

vi.mock("../../hooks/useExecutionWebSocket", () => ({
  useExecutionWebSocket: () => "connected",
}));

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <Dashboard />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Dashboard Page", () => {
  it("renders dashboard header", () => {
    renderDashboard();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Real-time overview of scheduler health")).toBeInTheDocument();
  });

  it("shows WebSocket status", () => {
    renderDashboard();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("renders KPI cards with user stats", () => {
    renderDashboard();
    expect(screen.getByText("Total Executions")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.getByText("Success Rate")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("Failed Jobs")).toBeInTheDocument();
    expect(screen.getByText("DLQ Jobs")).toBeInTheDocument();
  });

  it("renders queue stats section", () => {
    renderDashboard();
    // "Ready Queue" / "Processing Queue" appear in both QueueStats and Worker Load
    expect(screen.getAllByText("Ready Queue").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Processing Queue").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Failed Queue")).toBeInTheDocument();
  });

  it("renders Worker Load section", () => {
    renderDashboard();
    expect(screen.getByText("Worker Load")).toBeInTheDocument();
  });

  it("renders Recent Executions section", () => {
    renderDashboard();
    expect(screen.getByText("Recent Executions")).toBeInTheDocument();
  });

  it("has View all link to executions page", () => {
    renderDashboard();
    const link = screen.getByText(/View all/);
    expect(link.closest("a")).toHaveAttribute("href", "/executions");
  });
});
