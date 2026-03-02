import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/auth", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

describe("DLQ API", () => {
  let getDLQ, replayDLQ, api;

  beforeEach(async () => {
    vi.resetModules();
    const authMod = await import("../../api/auth");
    api = authMod.api;
    const mod = await import("../../api/dlq");
    getDLQ = mod.getDLQ;
    replayDLQ = mod.replayDLQ;
  });

  it("getDLQ calls with pagination", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0 } });

    await getDLQ(2, 10);

    expect(api.get).toHaveBeenCalledWith("/admin/dlq", { params: { page: 2, size: 10 } });
  });

  it("getDLQ uses default pagination", async () => {
    api.get.mockResolvedValue({ data: { items: [] } });

    await getDLQ();

    expect(api.get).toHaveBeenCalledWith("/admin/dlq", { params: { page: 1, size: 20 } });
  });

  it("replayDLQ calls POST with execution ID", async () => {
    api.post.mockResolvedValue({ data: { status: "replayed" } });

    const result = await replayDLQ("exec-123");

    expect(api.post).toHaveBeenCalledWith("/admin/dlq/exec-123/replay");
    expect(result.status).toBe("replayed");
  });
});
