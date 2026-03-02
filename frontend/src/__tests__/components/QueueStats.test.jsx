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

  it("renders all three stat cards", () => {
    render(<QueueStats stats={{ ready: 5, processing: 3, failed: 2 }} />);
    expect(screen.getByText("Ready Queue")).toBeInTheDocument();
    expect(screen.getByText("Processing Queue")).toBeInTheDocument();
    expect(screen.getByText("Failed Queue")).toBeInTheDocument();
  });

  it("displays correct values", () => {
    render(<QueueStats stats={{ ready: 10, processing: 7, failed: 1 }} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("defaults to 0 for missing values", () => {
    render(<QueueStats stats={{}} />);
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBe(3);
  });

  it("shows hint icons for all cards", () => {
    render(<QueueStats stats={{ ready: 0, processing: 0, failed: 0 }} />);
    const hints = screen.getAllByText("i");
    expect(hints.length).toBe(3);
  });
});
