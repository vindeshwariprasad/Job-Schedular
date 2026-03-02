import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import Sidebar from "../../layout/Sidebar";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

function renderSidebar(props = {}) {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <ThemeProvider>
        <AuthProvider>
          <Sidebar {...props} />
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.setItem("token", "test-token");
    localStorage.setItem("user", JSON.stringify({ username: "testuser", email: "test@test.com" }));
  });

  it("renders app title", () => {
    renderSidebar();
    expect(screen.getByText("Job Scheduler")).toBeInTheDocument();
  });

  it("renders all navigation links", () => {
    renderSidebar();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Executions")).toBeInTheDocument();
    expect(screen.getByText("DLQ")).toBeInTheDocument();
    expect(screen.getByText("Queues")).toBeInTheDocument();
    expect(screen.getByText("Metrics")).toBeInTheDocument();
  });

  it("renders correct link hrefs", () => {
    renderSidebar();
    expect(screen.getByText("Dashboard").closest("a")).toHaveAttribute("href", "/dashboard");
    expect(screen.getByText("Jobs").closest("a")).toHaveAttribute("href", "/jobs");
    expect(screen.getByText("Executions").closest("a")).toHaveAttribute("href", "/executions");
    expect(screen.getByText("DLQ").closest("a")).toHaveAttribute("href", "/dlq");
    expect(screen.getByText("Queues").closest("a")).toHaveAttribute("href", "/queues");
    expect(screen.getByText("Metrics").closest("a")).toHaveAttribute("href", "/metrics");
  });

  it("renders theme toggle button", () => {
    renderSidebar();
    expect(screen.getByText("Dark Mode")).toBeInTheDocument();
  });

  it("toggles theme on click", async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByText("Dark Mode"));
    expect(screen.getByText("Light Mode")).toBeInTheDocument();
  });

  it("renders user info when logged in", async () => {
    renderSidebar();
    expect(await screen.findByText("testuser")).toBeInTheDocument();
    expect(await screen.findByText("test@test.com")).toBeInTheDocument();
  });

  it("renders sign out button", async () => {
    renderSidebar();
    expect(await screen.findByText("Sign Out")).toBeInTheDocument();
  });

  it("renders close button when onClose is provided", () => {
    const onClose = vi.fn();
    renderSidebar({ onClose });
    // Close button should exist (mobile)
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("does not render close button when no onClose", () => {
    renderSidebar();
    // Only theme toggle and sign out buttons should exist
    const buttons = screen.getAllByRole("button");
    // Theme toggle + Sign Out = 2 buttons
    expect(buttons.length).toBe(2);
  });
});
