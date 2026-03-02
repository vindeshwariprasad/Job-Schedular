import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import AppRoutes from "../../routes";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn(),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

// Mock heavy pages to keep tests fast
vi.mock("../../pages/Dashboard", () => ({
  default: () => <div>Dashboard Page</div>,
}));
vi.mock("../../pages/Jobs", () => ({
  default: () => <div>Jobs Page</div>,
}));
vi.mock("../../pages/JobDetail", () => ({
  default: () => <div>JobDetail Page</div>,
}));
vi.mock("../../pages/Executions", () => ({
  default: () => <div>Executions Page</div>,
}));
vi.mock("../../pages/DLQ", () => ({
  default: () => <div>DLQ Page</div>,
}));
vi.mock("../../pages/Queues", () => ({
  default: () => <div>Queues Page</div>,
}));
vi.mock("../../pages/Metrics", () => ({
  default: () => <div>Metrics Page</div>,
}));

import * as authApi from "../../api/auth";

function renderRoute(path) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ThemeProvider>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("App Routes", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  describe("Public routes", () => {
    beforeEach(() => {
      authApi.getMe.mockRejectedValue(new Error("not auth"));
    });

    it("renders login page at /login", () => {
      renderRoute("/login");
      expect(screen.getByText("Sign in to your account")).toBeInTheDocument();
    });

    it("renders register page at /register", () => {
      renderRoute("/register");
      expect(screen.getByText("Create your account")).toBeInTheDocument();
    });
  });

  describe("Protected routes (authenticated)", () => {
    beforeEach(() => {
      localStorage.setItem("token", "valid-token");
      localStorage.setItem("user", JSON.stringify({ username: "testuser", email: "test@test.com" }));
      authApi.getMe.mockResolvedValue({ username: "testuser", email: "test@test.com" });
    });

    it("renders dashboard at /dashboard", async () => {
      renderRoute("/dashboard");
      await waitFor(() => expect(screen.getByText("Dashboard Page")).toBeInTheDocument());
    });

    it("renders jobs at /jobs", async () => {
      renderRoute("/jobs");
      await waitFor(() => expect(screen.getByText("Jobs Page")).toBeInTheDocument());
    });

    it("renders job detail at /jobs/1", async () => {
      renderRoute("/jobs/1");
      await waitFor(() => expect(screen.getByText("JobDetail Page")).toBeInTheDocument());
    });

    it("renders executions at /executions", async () => {
      renderRoute("/executions");
      await waitFor(() => expect(screen.getByText("Executions Page")).toBeInTheDocument());
    });

    it("renders DLQ at /dlq", async () => {
      renderRoute("/dlq");
      await waitFor(() => expect(screen.getByText("DLQ Page")).toBeInTheDocument());
    });

    it("renders queues at /queues", async () => {
      renderRoute("/queues");
      await waitFor(() => expect(screen.getByText("Queues Page")).toBeInTheDocument());
    });

    it("renders metrics at /metrics", async () => {
      renderRoute("/metrics");
      await waitFor(() => expect(screen.getByText("Metrics Page")).toBeInTheDocument());
    });

    it("redirects / to /dashboard", async () => {
      renderRoute("/");
      await waitFor(() => expect(screen.getByText("Dashboard Page")).toBeInTheDocument());
    });
  });

  describe("Protected routes (unauthenticated)", () => {
    beforeEach(() => {
      authApi.getMe.mockRejectedValue(new Error("not auth"));
    });

    it("redirects /dashboard to /login when not authenticated", async () => {
      renderRoute("/dashboard");
      await waitFor(() => expect(screen.getByText("Sign in to your account")).toBeInTheDocument());
    });

    it("redirects /jobs to /login when not authenticated", async () => {
      renderRoute("/jobs");
      await waitFor(() => expect(screen.getByText("Sign in to your account")).toBeInTheDocument());
    });
  });
});
