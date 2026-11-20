import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Jobs from "../../pages/Jobs";

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

vi.mock("../../api/jobs", () => ({
  getJobs: vi.fn().mockResolvedValue({
    items: [
      { id: 1, name: "Test Job", task_type: "api_call", rate_limit_per_min: 60, is_active: true },
    ],
    total: 1,
  }),
  createJob: vi.fn().mockResolvedValue({ id: 2, name: "New Job" }),
  getJob: vi.fn(),
  deleteJob: vi.fn(),
}));

function renderJobs() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <Jobs />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Jobs Page", () => {
  it("renders page title", async () => {
    renderJobs();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
  });

  it("renders create job form", () => {
    renderJobs();
    expect(screen.getByPlaceholderText("Job name")).toBeInTheDocument();
    expect(screen.getByText("Create Job")).toBeInTheDocument();
  });

  it("renders task type dropdown with all options", () => {
    renderJobs();
    expect(screen.getByText("API Call")).toBeInTheDocument();
    expect(screen.getByText("String Manipulation")).toBeInTheDocument();
    expect(screen.getByText("Math")).toBeInTheDocument();
  });

  it("shows API call fields by default", () => {
    renderJobs();
    expect(screen.getByText("GET")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("https://example.com/api/endpoint")).toBeInTheDocument();
  });

  it("shows string manipulation field when selected", async () => {
    const user = userEvent.setup();
    renderJobs();

    const taskSelect = screen.getAllByRole("combobox")[0];
    await user.selectOptions(taskSelect, "string_manipulation");

    expect(screen.getByPlaceholderText("Enter any text to uppercase")).toBeInTheDocument();
  });

  it("shows math field when selected", async () => {
    const user = userEvent.setup();
    renderJobs();

    const taskSelect = screen.getAllByRole("combobox")[0];
    await user.selectOptions(taskSelect, "math");

    expect(screen.getByPlaceholderText("2 + 3 * (4 - 1)")).toBeInTheDocument();
  });

  it("renders rate limit input with default value 60", () => {
    renderJobs();
    expect(screen.getByPlaceholderText("Rate limit / min")).toHaveValue(60);
  });

  it("renders HTTP method dropdown for API Call", () => {
    renderJobs();
    expect(screen.getByText("GET")).toBeInTheDocument();
    expect(screen.getByText("POST")).toBeInTheDocument();
    expect(screen.getByText("PUT")).toBeInTheDocument();
    expect(screen.getByText("DELETE")).toBeInTheDocument();
  });

  it("renders jobs table after loading", async () => {
    renderJobs();

    await waitFor(() => {
      expect(screen.getByText("Test Job")).toBeInTheDocument();
    });
  });

  it("allows filling and submitting the create form", async () => {
    const { createJob } = await import("../../api/jobs");
    const user = userEvent.setup();
    renderJobs();

    await user.type(screen.getByPlaceholderText("Job name"), "New API Job");
    await user.type(screen.getByPlaceholderText("https://example.com/api/endpoint"), "https://test.com/api");
    await user.click(screen.getByText("Create Job"));

    await waitFor(() => {
      expect(createJob).toHaveBeenCalled();
    });
  });
});
