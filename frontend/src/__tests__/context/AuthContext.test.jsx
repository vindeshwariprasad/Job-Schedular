import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "../../context/AuthContext";

// Mock the API
vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn(),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import * as authApi from "../../api/auth";

function AuthConsumer() {
  const { user, loading, login, register, logout } = useAuth();

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <span data-testid="user">{user ? user.username : "none"}</span>
      <button onClick={() => login("testuser", "pass123")}>Login</button>
      <button onClick={() => register("newuser", "new@test.com", "pass123")}>Register</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    authApi.getMe.mockRejectedValue(new Error("not logged in"));
  });

  it("shows no user when not logged in", async () => {
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("none");
    });
  });

  it("restores user from localStorage on mount", async () => {
    localStorage.setItem("token", "test-token");
    localStorage.setItem("user", JSON.stringify({ username: "saveduser" }));
    authApi.getMe.mockResolvedValue({ username: "saveduser", email: "saved@test.com" });

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("saveduser");
    });
  });

  it("clears auth on getMe failure", async () => {
    localStorage.setItem("token", "expired-token");
    localStorage.setItem("user", JSON.stringify({ username: "old" }));
    authApi.getMe.mockRejectedValue({ response: { status: 401 } });

    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("none");
      expect(localStorage.getItem("token")).toBeNull();
    });
  });

  it("login stores token and user", async () => {
    authApi.login.mockResolvedValue({
      access_token: "new-token",
      user: { username: "testuser", email: "test@test.com" },
    });

    const user = userEvent.setup();
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));
    await user.click(screen.getByText("Login"));

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("testuser");
      expect(localStorage.getItem("token")).toBe("new-token");
    });
  });

  it("register stores token and user", async () => {
    authApi.register.mockResolvedValue({
      access_token: "reg-token",
      user: { username: "newuser", email: "new@test.com" },
    });

    const user = userEvent.setup();
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("none"));
    await user.click(screen.getByText("Register"));

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("newuser");
      expect(localStorage.getItem("token")).toBe("reg-token");
    });
  });

  it("logout clears storage and user", async () => {
    localStorage.setItem("token", "test-token");
    localStorage.setItem("user", JSON.stringify({ username: "testuser" }));
    authApi.getMe.mockResolvedValue({ username: "testuser" });

    const user = userEvent.setup();
    renderWithRouter(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("testuser"));
    await user.click(screen.getByText("Logout"));

    await waitFor(() => {
      expect(screen.getByTestId("user")).toHaveTextContent("none");
      expect(localStorage.getItem("token")).toBeNull();
    });
  });

  it("throws when useAuth is used outside AuthProvider", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() =>
      renderWithRouter(<AuthConsumer />)
    ).toThrow("useAuth must be used within an AuthProvider");
    consoleSpy.mockRestore();
  });
});
