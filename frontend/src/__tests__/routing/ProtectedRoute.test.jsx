import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "../../context/ThemeContext";
import { AuthProvider } from "../../context/AuthContext";
import ProtectedRoute from "../../components/ProtectedRoute";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn(),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import * as authApi from "../../api/auth";

function renderProtectedRoute(initialEntries = ["/protected"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            <Route
              path="/protected"
              element={
                <ProtectedRoute>
                  <div>Protected Content</div>
                </ProtectedRoute>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("redirects to login when not authenticated", async () => {
    authApi.getMe.mockRejectedValue(new Error("not auth"));
    renderProtectedRoute();

    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });
  });

  it("renders children when authenticated", async () => {
    localStorage.setItem("token", "valid-token");
    localStorage.setItem("user", JSON.stringify({ username: "testuser" }));
    authApi.getMe.mockResolvedValue({ username: "testuser", email: "test@test.com" });

    renderProtectedRoute();

    await waitFor(() => {
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });
  });

  it("shows loading spinner while checking auth", () => {
    localStorage.setItem("token", "valid-token");
    localStorage.setItem("user", JSON.stringify({ username: "testuser" }));
    authApi.getMe.mockImplementation(() => new Promise(() => {})); // Never resolves

    renderProtectedRoute();

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });
});
