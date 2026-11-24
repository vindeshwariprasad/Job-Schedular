import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DeleteJobDialog from "../../components/DeleteJobDialog";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  getMe: vi.fn(),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock("../../api/jobs", () => ({
  getJobDependents: vi.fn().mockResolvedValue({ dependents: [] }),
}));

function renderDialog(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const defaults = {
    open: true,
    jobId: 1,
    jobName: "Test Job",
    loading: false,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <DeleteJobDialog {...defaults} {...props} />
    </QueryClientProvider>
  );
}

describe("DeleteJobDialog", () => {
  it("renders nothing when not open", () => {
    const { container } = renderDialog({ open: false });
    expect(container.firstChild).toBeNull();
  });

  it("renders job name and id in title", () => {
    renderDialog();
    expect(screen.getByText(/Delete Job #1: Test Job/)).toBeInTheDocument();
  });

  it("shows permanent delete message when no dependents", async () => {
    renderDialog();
    expect(await screen.findByText(/permanently delete/)).toBeInTheDocument();
  });

  it("renders Cancel and Delete buttons", () => {
    renderDialog();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    renderDialog({ onCancel });

    await user.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("calls onConfirm with cascade=false by default", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    renderDialog({ onConfirm });

    await user.click(screen.getByText("Delete"));
    expect(onConfirm).toHaveBeenCalledWith(false);
  });

  it("shows Deleting... text when loading", () => {
    renderDialog({ loading: true });
    expect(screen.getByText("Deleting...")).toBeInTheDocument();
  });

  it("disables buttons when loading", () => {
    renderDialog({ loading: true });
    expect(screen.getByText("Cancel")).toBeDisabled();
    expect(screen.getByText("Deleting...")).toBeDisabled();
  });
});
