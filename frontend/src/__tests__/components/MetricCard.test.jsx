import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import MetricCard from "../../components/MetricCard";

describe("MetricCard", () => {
  it("renders title and value", () => {
    render(<MetricCard title="Total Jobs" value={42} color="text-blue-600" />);
    expect(screen.getByText("Total Jobs")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders string value", () => {
    render(<MetricCard title="Success Rate" value="85%" color="text-green-600" />);
    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  it("does not show hint icon when no hint", () => {
    const { container } = render(
      <MetricCard title="Test" value={0} color="text-blue-600" />
    );
    expect(container.querySelector("span.cursor-pointer")).not.toBeInTheDocument();
  });

  it("shows hint icon and reveals hint on hover", () => {
    render(<MetricCard title="Test" value={0} color="text-blue-600" hint="Help text" />);
    const hintIcon = screen.getByText("i");
    expect(hintIcon).toBeInTheDocument();

    fireEvent.mouseEnter(hintIcon);
    expect(screen.getByText("Help text")).toBeInTheDocument();

    fireEvent.mouseLeave(hintIcon);
    expect(screen.queryByText("Help text")).not.toBeInTheDocument();
  });

  it("toggles hint on click", () => {
    render(<MetricCard title="Test" value={0} color="text-blue-600" hint="Click hint" />);
    const hintIcon = screen.getByText("i");

    fireEvent.click(hintIcon);
    expect(screen.getByText("Click hint")).toBeInTheDocument();

    fireEvent.click(hintIcon);
    expect(screen.queryByText("Click hint")).not.toBeInTheDocument();
  });
});
