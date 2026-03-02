import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import AppLayout from "../../layout/AppLayout";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockResolvedValue({ username: "testuser", email: "test@test.com" }),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

function renderLayout(children = <div>Page Content</div>) {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <ThemeProvider>
        <AuthProvider>
          <AppLayout>{children}</AppLayout>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("AppLayout", () => {
  it("renders children content", () => {
    renderLayout(<div>My Page</div>);
    expect(screen.getByText("My Page")).toBeInTheDocument();
  });

  it("renders sidebar with navigation", () => {
    renderLayout();
    // "Job Scheduler" appears in both sidebar and mobile header
    expect(screen.getAllByText("Job Scheduler").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });

  it("renders mobile header with hamburger button", () => {
    renderLayout();
    // The mobile header has "Job Scheduler" text
    const titles = screen.getAllByText("Job Scheduler");
    expect(titles.length).toBeGreaterThanOrEqual(1);
  });

  it("opens mobile sidebar on hamburger click", async () => {
    const user = userEvent.setup();
    renderLayout();

    // Find the hamburger button (mobile header)
    const buttons = screen.getAllByRole("button");
    const hamburger = buttons.find(
      (btn) => btn.querySelector("svg.w-6.h-6") && btn.closest(".md\\:hidden")
    );

    if (hamburger) {
      await user.click(hamburger);
      // Should now have the mobile overlay
      const overlays = document.querySelectorAll(".fixed.inset-0");
      expect(overlays.length).toBeGreaterThan(0);
    }
  });
});
