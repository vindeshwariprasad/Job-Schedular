import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ExecutionTable from "../../components/ExecutionTable";
import { mockExecutions } from "../test-utils";

describe("ExecutionTable", () => {
  it("renders all column headers", () => {
    render(<ExecutionTable executions={mockExecutions.items} />);
    expect(screen.getByText("Execution ID")).toBeInTheDocument();
    expect(screen.getByText("Job ID")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Attempt")).toBeInTheDocument();
    expect(screen.getByText("Started At")).toBeInTheDocument();
    expect(screen.getByText("Finished At")).toBeInTheDocument();
  });

  it("renders execution data", () => {
    render(<ExecutionTable executions={mockExecutions.items} />);
    expect(screen.getByText("SUCCESS")).toBeInTheDocument();
    expect(screen.getByText("FAILED")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("shows dashes for null dates", () => {
    render(<ExecutionTable executions={[mockExecutions.items[2]]} />);
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBe(2); // started_at and finished_at
  });

  it("formats dates correctly", () => {
    render(<ExecutionTable executions={[mockExecutions.items[0]]} />);
    // Should show formatted date strings, not raw ISO
    expect(screen.queryByText("2024-01-01T10:00:00Z")).not.toBeInTheDocument();
  });

  it("shows empty state when no executions", () => {
    render(<ExecutionTable executions={[]} />);
    expect(screen.getByText("No executions found")).toBeInTheDocument();
    expect(screen.getByText("Executions will appear here once jobs start running.")).toBeInTheDocument();
  });

  it("handles null executions", () => {
    render(<ExecutionTable executions={null} />);
    expect(screen.getByText("Execution ID")).toBeInTheDocument();
  });

  it("renders status badges with correct colors", () => {
    render(<ExecutionTable executions={mockExecutions.items} />);
    const success = screen.getByText("SUCCESS");
    expect(success.closest("span")).toHaveClass("text-green-700");

    const failed = screen.getByText("FAILED");
    expect(failed.closest("span")).toHaveClass("text-red-700");

    const pending = screen.getByText("PENDING");
    expect(pending.closest("span")).toHaveClass("text-yellow-700");

    const running = screen.getByText("RUNNING");
    expect(running.closest("span")).toHaveClass("text-blue-700");
  });
});
