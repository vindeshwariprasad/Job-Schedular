import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import QueueStats from "../../components/QueueStats";

describe("QueueStats", () => {
  it("shows loading state when stats is null", () => {
    render(<QueueStats stats={null} />);
    expect(screen.getByText("Loading queue stats...")).toBeInTheDocument();
  });

  it("shows loading state when stats is undefined", () => {
    render(<QueueStats stats={undefined} />);
    expect(screen.getByText("Loading queue stats...")).toBeInTheDocument();
  });

  it("renders all stat cards including per-priority", () => {
    render(<QueueStats stats={{ ready: 5, processing: 3, failed: 2, ready_high: 2, ready_medium: 2, ready_low: 1 }} />);
    expect(screen.getByText("Ready Queue")).toBeInTheDocument();
    expect(screen.getByText("Processing Queue")).toBeInTheDocument();
    expect(screen.getByText("Failed Queue")).toBeInTheDocument();
    expect(screen.getByText(/Ready — High/)).toBeInTheDocument();
    expect(screen.getByText(/Ready — Medium/)).toBeInTheDocument();
    expect(screen.getByText(/Ready — Low/)).toBeInTheDocument();
  });

  it("displays correct values", () => {
    render(<QueueStats stats={{ ready: 10, processing: 7, failed: 1, ready_high: 4, ready_medium: 3, ready_low: 3 }} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("defaults to 0 for missing values", () => {
    render(<QueueStats stats={{}} />);
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBe(6);
  });

  it("shows hint icons for all cards", () => {
    render(<QueueStats stats={{ ready: 0, processing: 0, failed: 0, ready_high: 0, ready_medium: 0, ready_low: 0 }} />);
    const hints = screen.getAllByText("i");
    expect(hints.length).toBe(6);
  });
});
