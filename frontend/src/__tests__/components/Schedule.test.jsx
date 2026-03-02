import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import ScheduleSection from "../../components/Schedule";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

// Default: no schedule exists
const mockGetSchedule = vi.fn().mockRejectedValue({ response: { status: 404 } });
const mockCreateSchedule = vi.fn().mockResolvedValue({ status: "active" });
const mockPauseSchedule = vi.fn().mockResolvedValue({ status: "paused" });
const mockResumeSchedule = vi.fn().mockResolvedValue({ status: "active" });
const mockDeleteSchedule = vi.fn().mockResolvedValue({ ok: true });

vi.mock("../../api/schedules", () => ({
  getSchedule: (...args) => mockGetSchedule(...args),
  createSchedule: (...args) => mockCreateSchedule(...args),
  pauseSchedule: (...args) => mockPauseSchedule(...args),
  resumeSchedule: (...args) => mockResumeSchedule(...args),
  deleteSchedule: (...args) => mockDeleteSchedule(...args),
}));

function renderSchedule(jobId = 1) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <ScheduleSection jobId={jobId} />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ScheduleSection - No Schedule", () => {
  it("renders create schedule form when no schedule", async () => {
    renderSchedule();
    await waitFor(() => {
      expect(screen.getByText("Schedule Job")).toBeInTheDocument();
    });
  });

  it("renders interval input and unit dropdown", async () => {
    renderSchedule();
    await waitFor(() => {
      expect(screen.getByPlaceholderText("5")).toBeInTheDocument();
      expect(screen.getByText("Minutes")).toBeInTheDocument();
      expect(screen.getByText("Hours")).toBeInTheDocument();
      expect(screen.getByText("Days")).toBeInTheDocument();
    });
  });

  it("renders max runs input", async () => {
    renderSchedule();
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Max runs (leave empty for unlimited)")).toBeInTheDocument();
    });
  });

  it("shows cron preview when interval is typed", async () => {
    const user = userEvent.setup();
    renderSchedule();

    await waitFor(() => screen.getByPlaceholderText("5"));
    await user.type(screen.getByPlaceholderText("5"), "10");

    await waitFor(() => {
      expect(screen.getByText("*/10 * * * *")).toBeInTheDocument();
    });
  });

  it("shows cron preview for hours", async () => {
    const user = userEvent.setup();
    renderSchedule();

    await waitFor(() => screen.getByPlaceholderText("5"));
    await user.type(screen.getByPlaceholderText("5"), "2");
    await user.selectOptions(screen.getByRole("combobox"), "hours");

    await waitFor(() => {
      expect(screen.getByText("0 */2 * * *")).toBeInTheDocument();
    });
  });

  it("Schedule button is disabled when no interval", async () => {
    renderSchedule();
    await waitFor(() => {
      expect(screen.getByText("Schedule")).toBeDisabled();
    });
  });
});

describe("ScheduleSection - Schedule Exists", () => {
  it("renders schedule status when schedule exists", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 10,
      max_runs: 100,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("ACTIVE")).toBeInTheDocument();
      expect(screen.getByText("Every 5 minutes")).toBeInTheDocument();
    });
  });

  it("shows Pause button when active", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 10,
      max_runs: 100,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("Pause")).toBeInTheDocument();
    });
  });

  it("shows Resume button when paused", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "paused",
      cron_expression: "*/5 * * * *",
      next_run_at: null,
      run_count: 10,
      max_runs: 100,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("Resume")).toBeInTheDocument();
    });
  });

  it("shows run count with max", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 10,
      max_runs: 100,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("10 / 100")).toBeInTheDocument();
    });
  });

  it("shows unlimited when no max_runs", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 10,
      max_runs: null,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("10 (unlimited)")).toBeInTheDocument();
    });
  });

  it("shows Delete button", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 0,
      max_runs: null,
    });

    renderSchedule();

    await waitFor(() => {
      expect(screen.getByText("Delete")).toBeInTheDocument();
    });
  });

  it("opens delete confirm modal", async () => {
    mockGetSchedule.mockResolvedValueOnce({
      status: "active",
      cron_expression: "*/5 * * * *",
      next_run_at: "2024-01-01T12:05:00Z",
      run_count: 0,
      max_runs: null,
    });

    const user = userEvent.setup();
    renderSchedule();

    await waitFor(() => screen.getByText("Delete"));
    await user.click(screen.getByText("Delete"));

    expect(screen.getByText("Delete Schedule")).toBeInTheDocument();
    expect(screen.getByText(/permanently delete the schedule/)).toBeInTheDocument();
  });
});
