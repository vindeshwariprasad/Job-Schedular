import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Executions from "../../pages/Executions";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock("../../api/executions", () => ({
  getExecutions: vi.fn().mockResolvedValue({
    items: [
      {
        execution_id: "exec-1111",
        job_id: 1,
        status: "SUCCESS",
        attempt: 1,
        started_at: "2024-01-01T10:00:00Z",
        finished_at: "2024-01-01T10:00:05Z",
      },
    ],
    total: 1,
  }),
}));

vi.mock("../../hooks/useExecutionWebSocket", () => ({
  useExecutionWebSocket: () => "connected",
}));

function renderExecutions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <Executions />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Executions Page", () => {
  it("renders page title", () => {
    renderExecutions();
    expect(screen.getByText("Executions")).toBeInTheDocument();
  });

  it("shows WebSocket status", () => {
    renderExecutions();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("renders status filter dropdown", () => {
    renderExecutions();
    expect(screen.getByText("ALL")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
    expect(screen.getByText("SUCCESS")).toBeInTheDocument();
    expect(screen.getByText("FAILED")).toBeInTheDocument();
  });

  it("renders execution data after loading", async () => {
    renderExecutions();

    await waitFor(() => {
      expect(screen.getByText("exec-1111")).toBeInTheDocument();
    });
  });

  it("changes filter and refetches", async () => {
    const { getExecutions } = await import("../../api/executions");
    const user = userEvent.setup();
    renderExecutions();

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "FAILED");

    await waitFor(() => {
      expect(getExecutions).toHaveBeenCalledWith("FAILED", 1, 20);
    });
  });
});
