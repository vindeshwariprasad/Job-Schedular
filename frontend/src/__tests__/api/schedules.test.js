import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/auth", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

describe("Schedules API", () => {
  let createSchedule, getSchedule, pauseSchedule, resumeSchedule, deleteSchedule, api;

  beforeEach(async () => {
    vi.resetModules();
    const authMod = await import("../../api/auth");
    api = authMod.api;
    const mod = await import("../../api/schedules");
    createSchedule = mod.createSchedule;
    getSchedule = mod.getSchedule;
    pauseSchedule = mod.pauseSchedule;
    resumeSchedule = mod.resumeSchedule;
    deleteSchedule = mod.deleteSchedule;
  });

  it("createSchedule calls POST /jobs/:id/schedule", async () => {
    api.post.mockResolvedValue({ data: { status: "active" } });

    const result = await createSchedule(5, { cron_expression: "*/5 * * * *", max_runs: 10 });

    expect(api.post).toHaveBeenCalledWith("/jobs/5/schedule", {
      cron_expression: "*/5 * * * *",
      max_runs: 10,
    });
    expect(result.status).toBe("active");
  });

  it("getSchedule calls GET /jobs/:id/schedule", async () => {
    api.get.mockResolvedValue({ data: { cron_expression: "*/5 * * * *" } });

    const result = await getSchedule(3);

    expect(api.get).toHaveBeenCalledWith("/jobs/3/schedule");
    expect(result.cron_expression).toBe("*/5 * * * *");
  });

  it("pauseSchedule calls PATCH /jobs/:id/schedule/pause", async () => {
    api.patch.mockResolvedValue({ data: { status: "paused" } });

    const result = await pauseSchedule(7);

    expect(api.patch).toHaveBeenCalledWith("/jobs/7/schedule/pause");
    expect(result.status).toBe("paused");
  });

  it("resumeSchedule calls PATCH /jobs/:id/schedule/resume", async () => {
    api.patch.mockResolvedValue({ data: { status: "active" } });

    const result = await resumeSchedule(7);

    expect(api.patch).toHaveBeenCalledWith("/jobs/7/schedule/resume");
    expect(result.status).toBe("active");
  });

  it("deleteSchedule calls DELETE /jobs/:id/schedule", async () => {
    api.delete.mockResolvedValue({ data: { ok: true } });

    const result = await deleteSchedule(7);

    expect(api.delete).toHaveBeenCalledWith("/jobs/7/schedule");
    expect(result.ok).toBe(true);
  });
});
