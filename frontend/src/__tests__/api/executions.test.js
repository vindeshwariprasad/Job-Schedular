import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/auth", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

describe("Executions API", () => {
  let getExecutions, api;

  beforeEach(async () => {
    vi.resetModules();
    const authMod = await import("../../api/auth");
    api = authMod.api;
    const mod = await import("../../api/executions");
    getExecutions = mod.getExecutions;
  });

  it("getExecutions calls with status filter", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0 } });

    await getExecutions("FAILED", 1, 20);

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/executions", {
      params: { page: 1, size: 20, status: "FAILED" },
    });
  });

  it("getExecutions omits status when null", async () => {
    api.get.mockResolvedValue({ data: { items: [] } });

    await getExecutions(null);

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/executions", {
      params: { page: 1, size: 20 },
    });
  });

  it("getExecutions uses default pagination", async () => {
    api.get.mockResolvedValue({ data: { items: [] } });

    await getExecutions("PENDING");

    expect(api.get).toHaveBeenCalledWith("/admin/dlq/executions", {
      params: { page: 1, size: 20, status: "PENDING" },
    });
  });
});
