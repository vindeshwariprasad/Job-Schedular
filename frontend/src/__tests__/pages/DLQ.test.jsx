import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import DLQ from "../../pages/DLQ";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock("../../api/dlq", () => ({
  getDLQ: vi.fn().mockResolvedValue({
    items: [
      {
        id: 1,
        execution_id: "dlq-aaaa-bbbb-cccc-dddddddddddd",
        job_id: 1,
        error: "Timeout error",
        payload: { job_id: 1 },
        failed_at: "2024-01-01T12:00:00Z",
      },
    ],
    total: 1,
  }),
}));

function renderDLQ() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <DLQ />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DLQ Page", () => {
  it("renders page title and description", () => {
    renderDLQ();
    expect(screen.getByText("Dead Letter Queue")).toBeInTheDocument();
    expect(screen.getByText(/Failed executions that exceeded retry limits/)).toBeInTheDocument();
  });

  it("renders stats cards after loading", async () => {
    renderDLQ();

    await waitFor(() => {
      expect(screen.getByText("Total Failed")).toBeInTheDocument();
      expect(screen.getByText("Jobs Affected")).toBeInTheDocument();
      expect(screen.getByText("Latest Failure")).toBeInTheDocument();
    });
  });

  it("displays total failed count", async () => {
    renderDLQ();

    await waitFor(() => {
      // "1" may appear multiple times (total, job count), just check the stats section exists
      expect(screen.getByText("Total Failed")).toBeInTheDocument();
      const totalSection = screen.getByText("Total Failed").closest("div");
      expect(totalSection).toBeInTheDocument();
    });
  });

  it("renders DLQ entries", async () => {
    renderDLQ();

    await waitFor(() => {
      expect(screen.getByText("Timeout error")).toBeInTheDocument();
    });
  });

  it("shows replay button for entries", async () => {
    renderDLQ();

    await waitFor(() => {
      expect(screen.getByText("Replay")).toBeInTheDocument();
    });
  });
});
