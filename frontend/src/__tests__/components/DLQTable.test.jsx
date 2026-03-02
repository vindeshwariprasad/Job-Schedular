import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DLQTable from "../../components/DLQTable";
import { mockDLQEntries } from "../test-utils";

// Mock the auth api
vi.mock("../../api/auth", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import { api } from "../../api/auth";

function renderDLQTable(entries = mockDLQEntries.items) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DLQTable entries={entries} />
    </QueryClientProvider>
  );
}

describe("DLQTable", () => {
  it("renders all column headers", () => {
    renderDLQTable();
    expect(screen.getByText("Execution ID")).toBeInTheDocument();
    expect(screen.getByText("Job")).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("Payload")).toBeInTheDocument();
    expect(screen.getByText("Failed At")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();
  });

  it("shows empty state when no entries", () => {
    renderDLQTable([]);
    expect(screen.getByText("No failed executions")).toBeInTheDocument();
    expect(screen.getByText(/All jobs are executing successfully/)).toBeInTheDocument();
  });

  it("renders DLQ entries", () => {
    renderDLQTable();
    expect(screen.getByText("Connection timeout after 30s")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500 Internal Server Error")).toBeInTheDocument();
  });

  it("shows truncated execution IDs", () => {
    renderDLQTable();
    expect(screen.getByText("dlq-1111...")).toBeInTheDocument();
  });

  it("shows job ID badges", () => {
    renderDLQTable();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
  });

  it("renders Replay buttons for each entry", () => {
    renderDLQTable();
    const replayButtons = screen.getAllByText("Replay");
    expect(replayButtons.length).toBe(2);
  });

  it("opens confirm modal on Replay click", async () => {
    const user = userEvent.setup();
    renderDLQTable();

    await user.click(screen.getAllByText("Replay")[0]);

    expect(screen.getByText("Replay Execution")).toBeInTheDocument();
    expect(screen.getByText(/This will create a new execution/)).toBeInTheDocument();
  });

  it("replays execution on confirm", async () => {
    api.post.mockResolvedValue({ data: { status: "replayed" } });
    const user = userEvent.setup();
    renderDLQTable();

    // Open confirm modal
    await user.click(screen.getAllByText("Replay")[0]);
    // The modal confirm button is the last "Replay" text on screen
    const allReplayBtns = screen.getAllByText("Replay");
    await user.click(allReplayBtns[allReplayBtns.length - 1]);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith("/admin/dlq/dlq-1111-2222-3333-444444444444/replay");
    });
  });

  it("shows Replayed badge after successful replay", async () => {
    api.post.mockResolvedValue({ data: { status: "replayed" } });
    const user = userEvent.setup();
    renderDLQTable();

    await user.click(screen.getAllByText("Replay")[0]);
    // Click the confirm button in the modal (not the initial Replay button)
    const confirmButtons = screen.getAllByText("Replay");
    await user.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(screen.getByText("Replayed")).toBeInTheDocument();
    });
  });

  it("closes modal on cancel", async () => {
    const user = userEvent.setup();
    renderDLQTable();

    await user.click(screen.getAllByText("Replay")[0]);
    expect(screen.getByText("Replay Execution")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Replay Execution")).not.toBeInTheDocument();
  });
});
