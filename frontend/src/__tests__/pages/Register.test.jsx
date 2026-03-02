import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../context/AuthContext";
import { ThemeProvider } from "../../context/ThemeContext";
import Register from "../../pages/Register";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn().mockRejectedValue(new Error("not logged in")),
  api: {
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import * as authApi from "../../api/auth";

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <ThemeProvider>
        <AuthProvider>
          <Register />
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe("Register Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApi.getMe.mockRejectedValue(new Error("not logged in"));
  });

  it("renders registration form", () => {
    renderRegister();
    expect(screen.getByText("Job Scheduler")).toBeInTheDocument();
    expect(screen.getByText("Create your account")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Choose a username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your email")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Create a password")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Confirm your password")).toBeInTheDocument();
    expect(screen.getByText("Create Account")).toBeInTheDocument();
  });

  it("has link to login page", () => {
    renderRegister();
    expect(screen.getByText("Sign in")).toBeInTheDocument();
    expect(screen.getByText("Sign in").closest("a")).toHaveAttribute("href", "/login");
  });

  it("renders all form labels", () => {
    renderRegister();
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Password")).toBeInTheDocument();
    expect(screen.getByText("Confirm Password")).toBeInTheDocument();
  });

  it("allows typing in all fields", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByPlaceholderText("Choose a username"), "newuser");
    await user.type(screen.getByPlaceholderText("Enter your email"), "new@test.com");
    await user.type(screen.getByPlaceholderText("Create a password"), "pass123");
    await user.type(screen.getByPlaceholderText("Confirm your password"), "pass123");

    expect(screen.getByPlaceholderText("Choose a username")).toHaveValue("newuser");
    expect(screen.getByPlaceholderText("Enter your email")).toHaveValue("new@test.com");
    expect(screen.getByPlaceholderText("Create a password")).toHaveValue("pass123");
    expect(screen.getByPlaceholderText("Confirm your password")).toHaveValue("pass123");
  });

  it("submits registration on form submit", async () => {
    authApi.register.mockResolvedValue({
      access_token: "token",
      user: { username: "newuser" },
    });

    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByPlaceholderText("Choose a username"), "newuser");
    await user.type(screen.getByPlaceholderText("Enter your email"), "new@test.com");
    await user.type(screen.getByPlaceholderText("Create a password"), "pass123");
    await user.type(screen.getByPlaceholderText("Confirm your password"), "pass123");
    await user.click(screen.getByText("Create Account"));

    await waitFor(() => {
      expect(authApi.register).toHaveBeenCalledWith("newuser", "new@test.com", "pass123");
    });
  });

  it("shows Creating account... while submitting", async () => {
    authApi.register.mockImplementation(() => new Promise(() => {}));

    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByPlaceholderText("Choose a username"), "newuser");
    await user.type(screen.getByPlaceholderText("Enter your email"), "new@test.com");
    await user.type(screen.getByPlaceholderText("Create a password"), "pass123");
    await user.type(screen.getByPlaceholderText("Confirm your password"), "pass123");
    await user.click(screen.getByText("Create Account"));

    await waitFor(() => {
      expect(screen.getByText("Creating account...")).toBeInTheDocument();
    });
  });

  it("email input has type email", () => {
    renderRegister();
    expect(screen.getByPlaceholderText("Enter your email")).toHaveAttribute("type", "email");
  });

  it("password inputs have type password", () => {
    renderRegister();
    expect(screen.getByPlaceholderText("Create a password")).toHaveAttribute("type", "password");
    expect(screen.getByPlaceholderText("Confirm your password")).toHaveAttribute("type", "password");
  });
});
