import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../api/auth", () => {
  const api = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return { api };
});

describe("Jobs API", () => {
  let getJobs, createJob, getJob, deleteJob, getJobDependents, api;

  beforeEach(async () => {
    vi.resetModules();
    const authMod = await import("../../api/auth");
    api = authMod.api;
    const mod = await import("../../api/jobs");
    getJobs = mod.getJobs;
    createJob = mod.createJob;
    getJob = mod.getJob;
    deleteJob = mod.deleteJob;
    getJobDependents = mod.getJobDependents;
  });

  it("getJobs calls GET /jobs with pagination", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0 } });

    const result = await getJobs(2, 10);

    expect(api.get).toHaveBeenCalledWith("/jobs", { params: { page: 2, size: 10 } });
    expect(result).toEqual({ items: [], total: 0 });
  });

  it("getJobs uses default pagination", async () => {
    api.get.mockResolvedValue({ data: { items: [] } });

    await getJobs();

    expect(api.get).toHaveBeenCalledWith("/jobs", { params: { page: 1, size: 20 } });
  });

  it("createJob calls POST /jobs", async () => {
    const jobData = {
      name: "Test",
      task_type: "api_call",
      payload: { url: "https://test.com", method: "GET" },
      rate_limit_per_min: 60,
    };
    api.post.mockResolvedValue({ data: { id: 1, ...jobData } });

    const result = await createJob(jobData);

    expect(api.post).toHaveBeenCalledWith("/jobs", jobData);
    expect(result.id).toBe(1);
  });

  it("getJob calls GET /jobs/:id", async () => {
    api.get.mockResolvedValue({ data: { id: 5, name: "Job 5" } });

    const result = await getJob(5);

    expect(api.get).toHaveBeenCalledWith("/jobs/5");
    expect(result.name).toBe("Job 5");
  });

  it("deleteJob calls DELETE /jobs/:id with default cascade=false", async () => {
    api.delete.mockResolvedValue({ data: { ok: true } });

    const result = await deleteJob(3);

    expect(api.delete).toHaveBeenCalledWith("/jobs/3", { params: { cascade: false } });
    expect(result.ok).toBe(true);
  });

  it("deleteJob passes cascade=true when specified", async () => {
    api.delete.mockResolvedValue({ data: { ok: true } });

    await deleteJob(3, true);

    expect(api.delete).toHaveBeenCalledWith("/jobs/3", { params: { cascade: true } });
  });

  it("getJobDependents calls GET /jobs/:id/dependents", async () => {
    api.get.mockResolvedValue({ data: { dependents: [{ id: 5, name: "Child" }] } });

    const result = await getJobDependents(2);

    expect(api.get).toHaveBeenCalledWith("/jobs/2/dependents");
    expect(result.dependents).toHaveLength(1);
    expect(result.dependents[0].name).toBe("Child");
  });
});
