import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import JobDetail from "../../pages/JobDetail";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock("../../api/jobs", () => ({
  getJobs: vi.fn(),
  createJob: vi.fn(),
  getJob: vi.fn().mockResolvedValue({
    id: 1,
    name: "Test Job",
    task_type: "api_call",
    payload: { url: "https://example.com", method: "GET" },
    rate_limit_per_min: 60,
    is_active: true,
  }),
  deleteJob: vi.fn().mockResolvedValue({ ok: true }),
}));

vi.mock("../../api/schedules", () => ({
  getSchedule: vi.fn().mockRejectedValue({ response: { status: 404 } }),
  createSchedule: vi.fn(),
  pauseSchedule: vi.fn(),
  resumeSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
}));

function renderJobDetail() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/jobs/1"]}>
        <ThemeProvider>
          <AuthProvider>
            <Routes>
              <Route path="/jobs/:jobId" element={<JobDetail />} />
              <Route path="/jobs" element={<div>Jobs List</div>} />
            </Routes>
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("JobDetail Page", () => {
  it("renders job details after loading", async () => {
    renderJobDetail();

    await waitFor(() => {
      expect(screen.getByText("Job #1")).toBeInTheDocument();
    });

    expect(screen.getByText("Test Job")).toBeInTheDocument();
    expect(screen.getByText("api_call")).toBeInTheDocument();
    expect(screen.getByText("60 / min")).toBeInTheDocument();
  });

  it("shows Active status badge", async () => {
    renderJobDetail();

    await waitFor(() => {
      expect(screen.getByText("Active")).toBeInTheDocument();
    });
  });

  it("renders payload viewer", async () => {
    renderJobDetail();

    await waitFor(() => {
      expect(screen.getByText("Payload")).toBeInTheDocument();
    });
  });

  it("renders delete button", async () => {
    renderJobDetail();

    await waitFor(() => {
      expect(screen.getByText("Delete Job")).toBeInTheDocument();
    });
  });

  it("opens delete confirm modal on delete click", async () => {
    const user = userEvent.setup();
    renderJobDetail();

    await waitFor(() => screen.getByText("Delete Job"));
    await user.click(screen.getByText("Delete Job"));

    expect(screen.getByText("Delete Job", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText(/permanently delete/)).toBeInTheDocument();
  });

  it("renders schedule section", async () => {
    renderJobDetail();

    await waitFor(() => {
      expect(screen.getByText("Schedule Job")).toBeInTheDocument();
    });
  });
});
