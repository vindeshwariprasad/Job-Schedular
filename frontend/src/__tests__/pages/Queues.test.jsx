import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Queues from "../../pages/Queues";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    get: vi.fn().mockResolvedValue({ data: { ready: 10, processing: 5, failed: 2 } }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

function renderQueues() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ThemeProvider>
          <AuthProvider>
            <Queues />
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Queues Page", () => {
  it("renders page title", () => {
    renderQueues();
    expect(screen.getByText("Queue Status")).toBeInTheDocument();
  });

  it("renders description", () => {
    renderQueues();
    expect(screen.getByText(/Live Redis queue metrics/)).toBeInTheDocument();
  });

  it("renders queue stats after loading", async () => {
    renderQueues();

    await waitFor(() => {
      expect(screen.getByText("Ready Queue")).toBeInTheDocument();
      expect(screen.getByText("Processing Queue")).toBeInTheDocument();
      expect(screen.getByText("Failed Queue")).toBeInTheDocument();
    });
  });

  it("displays queue values", async () => {
    renderQueues();

    await waitFor(() => {
      expect(screen.getByText("10")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });
});
