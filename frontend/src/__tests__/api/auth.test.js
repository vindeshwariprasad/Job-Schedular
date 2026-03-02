import { describe, it, expect, vi, beforeEach } from "vitest";
import axios from "axios";

// Mock axios before importing the module
vi.mock("axios", () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  };
});

describe("Auth API", () => {
  let api, register, login, getMe;

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import("../../api/auth.js");
    api = mod.api;
    register = mod.register;
    login = mod.login;
    getMe = mod.getMe;
  });

  it("should create axios instance with base URL", () => {
    expect(axios.create).toHaveBeenCalledWith({
      baseURL: expect.any(String),
    });
  });

  it("register calls POST /auth/register with correct data", async () => {
    api.post.mockResolvedValue({
      data: { access_token: "tok123", user: { id: 1, username: "newuser" } },
    });

    const result = await register("newuser", "new@test.com", "password123");

    expect(api.post).toHaveBeenCalledWith("/auth/register", {
      username: "newuser",
      email: "new@test.com",
      password: "password123",
    });
    expect(result).toEqual({ access_token: "tok123", user: { id: 1, username: "newuser" } });
  });

  it("login calls POST /auth/login with correct data", async () => {
    api.post.mockResolvedValue({
      data: { access_token: "tok456", user: { id: 1, username: "testuser" } },
    });

    const result = await login("testuser", "pass");

    expect(api.post).toHaveBeenCalledWith("/auth/login", {
      username: "testuser",
      password: "pass",
    });
    expect(result.access_token).toBe("tok456");
  });

  it("getMe calls GET /auth/me", async () => {
    api.get.mockResolvedValue({
      data: { id: 1, username: "testuser", email: "test@test.com" },
    });

    const result = await getMe();

    expect(api.get).toHaveBeenCalledWith("/auth/me");
    expect(result.username).toBe("testuser");
  });

  it("login rejects on API error", async () => {
    api.post.mockRejectedValue({
      response: { status: 401, data: { detail: "Invalid credentials" } },
    });

    await expect(login("bad", "creds")).rejects.toBeTruthy();
  });

  it("register rejects on duplicate user", async () => {
    api.post.mockRejectedValue({
      response: { status: 409, data: { detail: "Username already taken" } },
    });

    await expect(register("dup", "dup@test.com", "pass")).rejects.toBeTruthy();
  });
});
