import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import WebSocketStatus from "../../components/WebSocketStatus";

describe("WebSocketStatus", () => {
  it("shows Live when connected", () => {
    render(<WebSocketStatus status="connected" />);
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("shows Connecting when connecting", () => {
    const { container } = render(<WebSocketStatus status="connecting" />);
    expect(screen.getByText("Connecting")).toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows Polling when disconnected", () => {
    render(<WebSocketStatus status="disconnected" />);
    expect(screen.getByText("Polling")).toBeInTheDocument();
  });

  it("defaults to disconnected for unknown status", () => {
    render(<WebSocketStatus status="unknown" />);
    expect(screen.getByText("Polling")).toBeInTheDocument();
  });

  it("renders green dot for connected", () => {
    const { container } = render(<WebSocketStatus status="connected" />);
    expect(container.querySelector(".bg-green-400")).toBeInTheDocument();
  });

  it("renders yellow dot for connecting", () => {
    const { container } = render(<WebSocketStatus status="connecting" />);
    expect(container.querySelector(".bg-yellow-400")).toBeInTheDocument();
  });

  it("renders gray dot for disconnected", () => {
    const { container } = render(<WebSocketStatus status="disconnected" />);
    expect(container.querySelector(".bg-gray-400")).toBeInTheDocument();
  });
});
