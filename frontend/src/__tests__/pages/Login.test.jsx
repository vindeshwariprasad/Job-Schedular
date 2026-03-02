import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../context/AuthContext";
import { ThemeProvider } from "../../context/ThemeContext";
import Login from "../../pages/Login";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockRejectedValue(new Error("not logged in")),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import * as authApi from "../../api/auth";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <ThemeProvider>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("Login Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApi.getMe.mockRejectedValue(new Error("not logged in"));
  });

  it("renders login form", () => {
    renderLogin();
    expect(screen.getByText("Job Scheduler")).toBeInTheDocument();
    expect(screen.getByText("Sign in to your account")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your password")).toBeInTheDocument();
    expect(screen.getByText("Sign In")).toBeInTheDocument();
  });

  it("has link to register page", () => {
    renderLogin();
    expect(screen.getByText("Create one")).toBeInTheDocument();
    expect(screen.getByText("Create one").closest("a")).toHaveAttribute("href", "/register");
  });

  it("renders username and password labels", () => {
    renderLogin();
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Password")).toBeInTheDocument();
  });

  it("allows typing in username and password fields", async () => {
    const user = userEvent.setup();
    renderLogin();

    const usernameInput = screen.getByPlaceholderText("Enter your username");
    const passwordInput = screen.getByPlaceholderText("Enter your password");

    await user.type(usernameInput, "testuser");
    await user.type(passwordInput, "password123");

    expect(usernameInput).toHaveValue("testuser");
    expect(passwordInput).toHaveValue("password123");
  });

  it("submits login on form submit", async () => {
    authApi.login.mockResolvedValue({
      access_token: "token",
      user: { username: "testuser" },
    });

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByPlaceholderText("Enter your username"), "testuser");
    await user.type(screen.getByPlaceholderText("Enter your password"), "pass123");
    await user.click(screen.getByText("Sign In"));

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith("testuser", "pass123");
    });
  });

  it("shows Signing in... while submitting", async () => {
    authApi.login.mockImplementation(() => new Promise(() => {})); // Never resolves

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByPlaceholderText("Enter your username"), "test");
    await user.type(screen.getByPlaceholderText("Enter your password"), "pass");
    await user.click(screen.getByText("Sign In"));

    await waitFor(() => {
      expect(screen.getByText("Signing in...")).toBeInTheDocument();
    });
  });

  it("disables button while submitting", async () => {
    authApi.login.mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByPlaceholderText("Enter your username"), "test");
    await user.type(screen.getByPlaceholderText("Enter your password"), "pass");
    await user.click(screen.getByText("Sign In"));

    await waitFor(() => {
      expect(screen.getByText("Signing in...")).toBeDisabled();
    });
  });

  it("password input has type password", () => {
    renderLogin();
    expect(screen.getByPlaceholderText("Enter your password")).toHaveAttribute("type", "password");
  });
});
